"""Bounded data planning, verified finance execution, and model dashboard composition."""

from __future__ import annotations

import json
import logging
import math
import os
import re
import socket
import time
from urllib import error, request

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import Field, ValidationError

from .api import PERIODS, _database_url
from .dashboard_data import DataBuilder, DEFINITIONS
from .dashboard_schema import CHART_CATALOG, ClosedModel, Composition, DataPlan, SpecViolation, validate_dashboard
from .seed import DATASET_ID

router = APIRouter(prefix="/api/demo-finance", tags=["synthetic-finance"])
logger = logging.getLogger(__name__)
MAX_MODEL_BYTES = 65_536
MAX_CONTEXT_BYTES = 58_000
MODEL_TIMEOUT = 40
CATALOG = {"dataset": DATASET_ID, "metrics": DEFINITIONS, "periods": list(PERIODS),
           "dimensions": ["period", "category", "cost_center", "bridge", "normalized"],
           "filters": {"category": ["shipping", "payroll", "admin"]}, "chart_types": CHART_CATALOG,
           "limits": "فقط دادهٔ مالی ساختگی آوریل تا سپتامبر ۲۰۲۶. جریان حمل، مقصد، تعداد سفارش و علت تجاری ثبت نشده است."}


class Question(ClosedModel):
    question: str = Field(min_length=2, max_length=500)


def fail(status: int, code: str, message: str, *, retryable: bool = False, validation: list[dict] | None = None):
    detail = {"code": code, "message": message, "retryable": retryable}
    if validation:
        detail["validation"] = validation
    raise HTTPException(status, detail)


def configured() -> bool:
    return all(os.getenv(key) for key in ("FINANCE_LLM_BASE_URL", "FINANCE_LLM_MODEL", "FINANCE_LLM_API_KEY"))


@router.get("/question-capability")
def capability() -> dict:
    return {"enabled": configured(), "contract_version": "2.0", "catalog": CATALOG,
            "limits": {"model_calls": 3, "supplementary_requests": 1, "rows": 100, "timeout_seconds_per_call": MODEL_TIMEOUT}}


def strict_json(raw: str | bytes) -> dict:
    """One JSON object; tolerate fences, reject duplicate keys and nonfinite constants."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if not isinstance(raw, str):
        raise TypeError("JSON text required")
    raw = raw.strip()
    if raw.startswith("```") and raw.endswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, count=1, flags=re.I)[:-3].strip()

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def nonfinite(_):
        raise ValueError("nonfinite JSON number")

    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("nonfinite JSON number")
        return parsed

    result = json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite, parse_float=finite_float)
    if not isinstance(result, dict):
        raise ValueError("JSON object required")
    return result


def model_json(system: str, content: dict | str, *, stage: str, deadline: float | None = None) -> dict:
    if not configured():
        fail(503, "model_unconfigured", "مدل پرسش مالی تنظیم نشده است؛ گزارش نمونه فعال است.")
    base = os.environ["FINANCE_LLM_BASE_URL"].rstrip("/")
    if not base.startswith(("https://", "http://127.0.0.1:", "http://localhost:")):
        fail(503, "model_unconfigured", "نشانی سرویس مدل باید HTTPS یا localhost باشد.")
    user = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, separators=(",", ":"))
    if len(user.encode("utf-8")) > MAX_CONTEXT_BYTES:
        fail(422, "data_limit", "حجم داده برای تحلیل بیش از سقف مجاز است؛ سؤال را محدودتر کنید.")
    payload = {"model": os.environ["FINANCE_LLM_MODEL"], "temperature": 0,
               "max_tokens": 1400 if stage == "plan" else 5200, "response_format": {"type": "json_object"},
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = request.Request(base + "/chat/completions", data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                          headers={"Authorization": "Bearer " + os.environ["FINANCE_LLM_API_KEY"], "Content-Type": "application/json"})
    try:
        remaining = min(MODEL_TIMEOUT, deadline - time.monotonic()) if deadline else MODEL_TIMEOUT
        if remaining <= 0:
            fail(504, "model_timeout", "زمان کل تحلیل مدل تمام شد؛ دوباره تلاش کنید.", retryable=True)
        with request.urlopen(req, timeout=remaining) as response:
            raw = response.read(MAX_MODEL_BYTES + 1)
        if len(raw) > MAX_MODEL_BYTES:
            fail(502, "invalid_json", "پاسخ سرویس مدل بیش از حد مجاز است.")
        wrapper = strict_json(raw)
        choice = wrapper["choices"][0]
        if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
            raise TypeError("model message object required")
        if choice.get("finish_reason") == "length":
            fail(502, "model_truncated", "پاسخ مدل به سقف طول رسید؛ سؤال را محدودتر کنید.", retryable=True)
        return strict_json(choice["message"]["content"])
    except error.HTTPError as exc:
        logger.warning("finance model HTTP failure stage=%s status=%s", stage, exc.code)
        if exc.code in {401, 403}:
            fail(503, "model_auth_error", "اعتبار اتصال سرویس مدل پذیرفته نشد؛ تنظیمات اتصال باید بررسی شود.")
        if exc.code == 429 or exc.code >= 500:
            fail(503, "model_unavailable", "سرویس مدل موقتاً در دسترس نیست؛ دوباره تلاش کنید.", retryable=True)
        fail(502, "model_request_rejected", "سرویس مدل قالب درخواست را نپذیرفت؛ تنظیمات مدل باید بررسی شود.")
    except (socket.timeout, TimeoutError):
        fail(504, "model_timeout", "زمان پاسخ‌گویی سرویس مدل تمام شد؛ دوباره تلاش کنید.", retryable=True)
    except error.URLError as exc:
        code = "model_timeout" if isinstance(exc.reason, (socket.timeout, TimeoutError)) or "timed out" in str(exc.reason).lower() else "model_unavailable"
        fail(504 if code == "model_timeout" else 503, code, "سرویس مدل پاسخ نداد؛ دوباره تلاش کنید.", retryable=True)
    except OSError:
        fail(503, "model_unavailable", "اتصال به سرویس مدل برقرار نشد.", retryable=True)
    except (ValueError, KeyError, IndexError, TypeError, UnicodeError) as exc:
        logger.warning("finance model JSON invalid stage=%s type=%s", stage, type(exc).__name__)
        fail(502, "invalid_json", "سرویس مدل JSON معتبر برنگرداند؛ دوباره تلاش کنید.", retryable=True)


PLAN_PROMPT = """You are a Persian finance data planner. Return ONLY JSON matching schema.
Choose required bounded data queries, not a dashboard intent/view. No SQL, code, arbitrary fields or invented metrics.
scope out_of_scope for unrelated questions; unavailable for missing dates/metrics/operational facts. Preserve scope; never substitute dates.
Default available quarter comparison q2,q3. Temporal trends use six monthly periods sorted.
Revenue trend requests revenue only and quarterly change if useful.
General overview requests quarter KPIs, selected monthly series, expense breakdown. Managerial REPORT additionally needs prioritized changes, bridge and a source table.
Strengths/weaknesses needs comparative financial metrics and changes, not generic overview.
Shipping dashboard requests shipping AND opex for q2,q3 AND six months; optional cost_center opex category shipping. Shipping is a metric.
Shipping example TWO SEPARATE queries: {"id":"quarters","metrics":["shipping","opex"],"periods":["q2","q3"],"dimension":"period","category":null}, {"id":"months","metrics":["shipping","opex"],"periods":["2026-04","2026-05","2026-06","2026-07","2026-08","2026-09"],"dimension":"period","category":null}.
NEVER combine quarter and monthly periods in one query. With shipping metric category MUST be null. Category filter shipping applies ONLY metrics [opex].
shipping+opex automatically provides shipping_share percentages. One shipping cost center need not get a breakdown chart.
dimension period: rows periods, columns metrics. category/cost_center: opex only, max two periods; one period label/value, two label/q2/q3.
category filter only with metrics [opex]. Prefer metric shipping for its own temporal series.
bridge: q2,q3 plus revenue,cogs,opex,operating_profit; reconciled label/value signed effects.
normalized: q2,q3 plus >=3 metrics; label/q2/q3 indices base q2=100; only if radar analytically useful.
No flow dataset exists: Sankey unavailable. No causes recorded. At most six compact queries.
Schema: """ + json.dumps(DataPlan.model_json_schema(), ensure_ascii=False)


DESIGN_PROMPT = """Design a Persian RTL analytical dashboard from PROVIDED REAL BACKEND DATA. Return ONLY schema JSON.
Return {kind:"dashboard",spec:{...}} or essential missing data request {kind:"data_request",queries:[...]}. One supplementary request allowed.
Choose direct answer, title, component count/order, suitable charts, cards, tables, prioritized insights for THIS QUESTION. No fixed template.
No HTML, JSX, SQL, JavaScript, raw chart options, calculated/invented numbers. Data rows, units, series immutable.
Every number/date numeral/percent/ratio/magnitude in prose MUST be {{fact_id}} from facts. No digits or percent symbols in prose fields.
This includes the year: NEVER type 2026 in a title, answer, baseline or scope. Say «سال دادهٔ نمونه» or omit the year.
Example with dataset quarters: «حمل فصل سوم {{quarters:q3:shipping}} و تغییر آن {{quarters:change_pct:shipping}} است.» Use actual provided fact IDs.
Do not write numbers as words to bypass references. Period names may be Persian words (فصل دوم, فصل سوم).
Facts display includes unit: use provided display without recalculation. Cards use fact_id, charts dataset/fields, tables fields.
Every insight MUST bind an actual COMPARISON fact placeholder in text, list matching fact_ids, explain explicit baseline and scope.
favorable true means favorable change, false unfavorable; expense increase is negative. Split positive and negative observations.
No definitive business cause/recommendation without evidence. Accounting bridge is reconciliation, not commercial cause proof.
Scope mentions synthetic data/observed period/lack of causal evidence. No long-term trend claims from two quarters.
Managerial report: explicit answer, prioritized changes, complementary charts, source table. Strengths/weaknesses: ranked favorable/unfavorable changes.
Shipping dashboard: focus shipping, valid period comparison, monthly change, opex share. One cost center isn't meaningful breakdown chart.
Revenue trend answer includes verified change. Use charts for analytical purpose; table/card better when chart unsuitable.
Only chart catalog types. line/area >=3 ordered monthly points. grouped_bar >=2 same-unit series; q2/q3 rows with ONE metric use bar.
Horizontal bar for category ranks. stacked_bar only payroll/shipping/admin additive parts. pie/donut/radial only breakdown positive total, 2..6 parts.
composed only revenue+operating_profit, shipping+opex, shipping+shipping_share; different unit percentage on right axis.
composed MUST contain EXACTLY TWO series. NEVER put shipping, opex AND shipping_share together: choose shipping+shipping_share or shipping+opex only.
waterfall only bridge series value. radar only normalized dataset series q2,q3. No fake flows/raw incompatible radar.
Chart x=label; series [{field,axis:left|right}], width half|full. layout lists ALL component IDs exactly once. Unique IDs. version="2.0".
Keep <=6 cards, <=4 charts, <=1 table, <=5 concise insights unless question needs more. No missing-value cards.
Schema: """ + json.dumps(Composition.model_json_schema(), ensure_ascii=False)


def validate_model(model, payload: dict, stage: str):
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        fields = [".".join(str(p) for p in e["loc"]) for e in exc.errors()][:5]
        issues = [{"field": ".".join(str(p) for p in e["loc"]), "type": e["type"], "message": e["msg"]} for e in exc.errors()][:5]
        logger.warning("finance model schema invalid stage=%s fields=%s types=%s", stage, fields, [e["type"] for e in exc.errors()][:5])
        unsupported = stage == "compose" and any(e["loc"][-1:] == ("type",) for e in exc.errors())
        fail(502, "unsupported_chart" if unsupported else "invalid_spec", "مدل نمودار پشتیبانی‌نشده انتخاب کرد." if unsupported else "ساختار پاسخ مدل با قرارداد داده سازگار نیست؛ دوباره تلاش کنید.", retryable=True, validation=issues)


def unavailable(message: str, *, status: str = "data_unavailable", calls: int = 0) -> dict:
    return {"status": status, "message": message, "spec": None, "datasets": [], "facts": [],
            "dataset_id": DATASET_ID, "dataset_version": None, "limitations": [message],
            "meta": {"model_calls": calls, "supplementary_requests": 0}}


def compact_context(builder: DataBuilder) -> dict:
    datasets = []
    for dataset in builder.datasets:
        rows = [{k: v for k, v in row.items() if k not in {"drilldowns", "source_ids"}} | {"source_ids": row["source_ids"][:4], "source_count": len(row["source_ids"])} for row in dataset["rows"]]
        datasets.append({**dataset, "rows": rows})
    facts = [{k: fact[k] for k in ("id", "label", "value", "display", "unit", "comparison", "favorable")} for fact in builder.facts]
    return {"datasets": datasets, "facts": facts}


def execute(question: str, plan: DataPlan, builder: DataBuilder, *, deadline: float | None = None, model_calls: int = 1) -> dict:
    builder.add(plan.queries)
    if not any(fact["value"] is not None for fact in builder.facts):
        return unavailable("پوشش داده برای شاخص‌های درخواستی ناقص است؛ مقدار ناموجود صفر نیست.", calls=model_calls)
    supplemental = 0
    repair = None
    for _ in range(3 - model_calls):
        context = {"question": question, "catalog": CATALOG, **compact_context(builder), "supplementary_request_allowed": model_calls < 2}
        if repair:
            context["repair"] = repair
        draft = model_json(DESIGN_PROMPT, context, stage="compose", deadline=deadline)
        model_calls += 1
        try:
            composition = validate_model(Composition, draft, "compose")
        except HTTPException as exc:
            if model_calls < 3 and isinstance(exc.detail, dict) and exc.detail["code"] in {"invalid_spec", "unsupported_chart"}:
                repair = {"instruction": "Previous draft failed schema validation. Return a corrected dashboard spec, no new data request.",
                          "code": exc.detail["code"], "validation": exc.detail.get("validation", []), "previous_draft": draft}
                continue
            raise
        if composition.kind == "data_request":
            if model_calls >= 3 or supplemental:
                raise SpecViolation("data_limit", "سقف چرخهٔ تکمیل داده یا تعداد فراخوانی مدل تمام شده است.")
            builder.add(composition.queries)
            supplemental = 1
            continue
        try:
            spec = validate_dashboard(composition.spec, builder.datasets, builder.facts)
        except SpecViolation as exc:
            logger.warning("finance dashboard validation code=%s field=%s", exc.code, exc.field or "structure")
            if model_calls < 3:
                repair = {"instruction": "Previous draft failed semantic validation. Correct this field and return dashboard spec only. Preserve real data; every prose number uses a valid fact placeholder.",
                          "code": exc.code, "field": exc.field or "structure", "message": str(exc), "details": exc.details,
                          "previous_draft": draft}
                continue
            raise
        limitations = ["دادهٔ مالی ساختگی؛ بازهٔ آوریل تا سپتامبر ۲۰۲۶ و فقط سطرهای ثبت‌شده.",
                       "تجزیهٔ حسابداری تغییر علت تجاری را اثبات نمی‌کند؛ جریان حمل، مقصد و تعداد سفارش موجود نیست."]
        for dataset in builder.datasets:
            limitations.extend(dataset["limitations"])
        return {"status": "answered", "message": spec["answer"], "spec": spec, "datasets": builder.datasets,
                "facts": builder.facts, "dataset_id": DATASET_ID, "dataset_version": builder.version,
                "limitations": list(dict.fromkeys(limitations)), "meta": {"model_calls": model_calls, "supplementary_requests": supplemental}}
    raise SpecViolation("invalid_spec", "مدل داشبورد نهایی تولید نکرد.")


@router.post("/question")
def ask(payload: Question) -> dict:
    deadline = time.monotonic() + 110
    if not configured():
        fail(503, "model_unconfigured", "مدل پرسش مالی تنظیم نشده است؛ گزارش نمونه فعال است.")
    normalized = payload.question.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    years = re.findall(r"(?<!\d)20\d{2}(?!\d)", normalized)
    unsupported_quarter = re.search(r"فصل\s*(?:اول|یکم|چهارم|1|4)(?!\d)", normalized)
    if any(year != "2026" for year in years) or unsupported_quarter:
        return unavailable("دورهٔ درخواستی موجود نیست؛ داده فقط فصل دوم و سوم سال ۲۰۲۶ را پوشش می‌دهد.")
    plan_context = {"question": payload.question, "catalog": CATALOG}
    draft = model_json(PLAN_PROMPT, plan_context, stage="plan", deadline=deadline)
    model_calls = 1
    try:
        plan = validate_model(DataPlan, draft, "plan")
    except HTTPException as exc:
        if not isinstance(exc.detail, dict) or exc.detail["code"] != "invalid_spec":
            raise
        plan_context["repair"] = {"instruction": "Correct invalid bounded data plan using validation messages. Return schema only; do not invent missing data.",
                                  "validation": exc.detail.get("validation", []), "previous_draft": draft}
        plan = validate_model(DataPlan, model_json(PLAN_PROMPT, plan_context, stage="plan", deadline=deadline), "plan")
        model_calls = 2
    if plan.scope != "finance":
        message = ("این ابزار فقط دربارهٔ دادهٔ مالی نمایشی پاسخ می‌دهد؛ مانند روند درآمد یا هزینهٔ حمل." if plan.scope == "out_of_scope" else
                   "دادهٔ لازم برای سؤال موجود نیست. فقط شاخص‌های مالی فصل دوم و سوم ۲۰۲۶ و شش ماه آن موجود است؛ مقصد، سفارش و علت تجاری ثبت نشده‌اند.")
        return unavailable(message, status="out_of_scope" if plan.scope == "out_of_scope" else "data_unavailable", calls=model_calls)
    try:
        with psycopg.connect(_database_url(), connect_timeout=3) as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            return execute(payload.question, plan, DataBuilder(conn), deadline=deadline, model_calls=model_calls)
    except SpecViolation as exc:
        logger.warning("finance dashboard rejected code=%s", exc.code)
        fail(422 if exc.code in {"insufficient_data", "data_limit"} else 502, exc.code, str(exc), retryable=exc.code not in {"insufficient_data", "data_limit"})
    except psycopg.Error:
        fail(503, "database_unavailable", "پایگاه دادهٔ مالی در دسترس نیست.", retryable=True)
