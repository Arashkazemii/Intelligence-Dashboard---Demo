"""Bounded question planning and source-linked execution for the finance demo."""

from __future__ import annotations

import json
import os
import re
from decimal import Decimal
from urllib import error, request

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .api import PERIODS, _database_url, _report
from .metrics import IncompleteCoverage, detail_rows
from .seed import DATASET_ID

router = APIRouter(prefix="/api/demo-finance", tags=["synthetic-finance"])

CATALOG = {
    "dataset": DATASET_ID,
    "metrics": {
        "revenue": "جمع خالص سطرهای REVENUE ثبت‌شده",
        "cogs": "جمع خالص سطرهای COGS ثبت‌شده",
        "opex": "جمع خالص سطرهای OPEX ثبت‌شده",
        "operating_profit": "revenue - cogs - opex؛ فقط با پوشش کامل",
    },
    "periods": list(PERIODS),
    "filters": {"opex_category": ["payroll", "shipping", "admin"]},
    "views": ["card", "trend", "comparison", "bridge"],
    "limits": "فقط دادهٔ مالی ساختگی آوریل تا سپتامبر ۲۰۲۶؛ علت تجاری مستقل ثبت نشده است.",
}
LABELS = {"revenue": "درآمد", "cogs": "بهای کالا", "opex": "هزینهٔ عملیاتی",
          "operating_profit": "سود عملیاتی"}
BUCKETS = {"revenue": "REVENUE", "cogs": "COGS", "opex": "OPEX"}
CATEGORIES = {"shipping": "حمل", "payroll": "حقوق", "admin": "اداری"}
SCOPE_MESSAGE = ("این ابزار برای ساخت و تحلیل داشبورد بر اساس داده‌های ViraData است. "
                 "مثلاً بپرسید: «روند درآمد را نشان بده». ")


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=2, max_length=500)


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: str
    metrics: list[str] = Field(max_length=4)
    periods: list[str] = Field(max_length=6)
    category: str | None = None
    view: str


def configured() -> bool:
    return all(os.getenv(key) for key in ("FINANCE_LLM_BASE_URL", "FINANCE_LLM_MODEL",
                                           "FINANCE_LLM_API_KEY"))


@router.get("/question-capability")
def capability() -> dict:
    return {"enabled": configured(), "catalog": CATALOG}


def plan_question(question: str) -> Plan:
    """Use an OpenAI-compatible chat endpoint only to choose catalog identifiers."""
    if not configured():
        raise HTTPException(503, "مدل پرسش مالی تنظیم نشده است؛ گزارش نمونه فعال است.")
    base = os.environ["FINANCE_LLM_BASE_URL"].rstrip("/")
    if not base.startswith(("https://", "http://127.0.0.1:", "http://localhost:")):
        raise HTTPException(503, "نشانی سرویس مدل باید HTTPS یا localhost باشد.")
    prompt = (
        "You classify Persian questions about this synthetic finance dataset. Return ONLY a JSON object "
        "with keys intent, metrics, periods, category, view. No numbers, explanation, SQL or extra keys. "
        "intent: metric|trend|compare|bridge|out_of_scope|unavailable. "
        "Use out_of_scope for greetings, general research, unrelated opinions. "
        "Use unavailable for related questions asking absent fields or dates; preserve the requested "
        "unknown field in metrics or unknown date in periods so the application can explain it. "
        "For why operating profit fell, use bridge, q2 and q3, revenue/cogs/opex/operating_profit. "
        "Default unspecified quarter to q3 for a single amount, both quarters for compare, "
        "and six months for trend. Category shipping/payroll/admin applies only to opex. "
        "Never infer a business cause. Catalog: " + json.dumps(CATALOG, ensure_ascii=False)
    )
    payload = {"model": os.environ["FINANCE_LLM_MODEL"], "temperature": 0,
               "response_format": {"type": "json_object"},
               "messages": [{"role": "system", "content": prompt},
                            {"role": "user", "content": question}]}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(base + "/chat/completions", data=body,
                          headers={"Authorization": "Bearer " + os.environ["FINANCE_LLM_API_KEY"],
                                   "Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=12) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError("model response too large")
        content = json.loads(raw)["choices"][0]["message"]["content"]
        return Plan.model_validate_json(content)
    except (error.URLError, TimeoutError, OSError) as exc:
        raise HTTPException(503, "سرویس مدل در دسترس نیست یا پاسخ‌گویی آن زمان‌بر شد.") from exc
    except (ValueError, KeyError, IndexError, TypeError, ValidationError) as exc:
        raise HTTPException(502, "پاسخ ساختاریافتهٔ مدل نامعتبر است.") from exc


def _unavailable(field: str) -> dict:
    return {"status": "data_unavailable", "message": f"فیلد یا دورهٔ «{field}» در دادهٔ نمایشی موجود نیست. بازهٔ معتبر: فصل دوم و سوم ۲۰۲۶ و ماه‌های آوریل تا سپتامبر.",
            "view": "none", "values": [], "drilldowns": []}


def execute(plan: Plan, conn: psycopg.Connection) -> dict:
    """Ignore all model prose; read only approved report and parameterized detail rows."""
    if plan.intent == "out_of_scope":
        return {"status": "out_of_scope", "message": SCOPE_MESSAGE, "view": "none", "values": [], "drilldowns": []}
    if plan.intent not in {"metric", "trend", "compare", "bridge", "unavailable"}:
        raise HTTPException(502, "نیت مدل مجاز نیست.")
    for metric in plan.metrics:
        if metric not in LABELS:
            return _unavailable(metric)
    for period in plan.periods:
        if period not in PERIODS:
            return _unavailable(period)
    if plan.category is not None and plan.category not in CATEGORIES:
        return _unavailable(plan.category)
    if plan.intent == "unavailable":
        return _unavailable((plan.metrics + plan.periods + [plan.category or "فیلد درخواستی"])[0])
    views = {"metric": "card", "trend": "trend", "compare": "comparison", "bridge": "bridge"}
    if plan.view != views[plan.intent] or not plan.metrics or not plan.periods:
        raise HTTPException(502, "ترکیب نیت و نمایش مدل نامعتبر است.")
    if plan.category and (plan.metrics != ["opex"] or plan.intent != "metric"):
        raise HTTPException(502, "فیلتر دسته برای این شاخص مجاز نیست.")
    if plan.intent == "bridge" and (plan.periods != ["q2", "q3"] or set(plan.metrics) != set(LABELS)):
        raise HTTPException(502, "پل سود فقط برای مقایسهٔ دو فصل معتبر است.")
    if plan.intent == "compare" and plan.periods != ["q2", "q3"]:
        raise HTTPException(502, "مقایسه فقط برای دو فصل موجود است.")
    if plan.intent == "trend" and (plan.periods != [f"2026-{m:02d}" for m in range(4, 10)] or plan.category):
        raise HTTPException(502, "روند فقط برای شش ماه موجود است.")
    if plan.intent == "metric" and len(plan.periods) != 1:
        raise HTTPException(502, "کارت فقط یک دوره می‌پذیرد.")

    report = _report(conn)
    snapshots = {**report["quarters"], **{item["month"]: item for item in report["monthly_trend"]}}
    values = []
    drilldowns = []
    for period in plan.periods:
        for metric in plan.metrics:
            data = snapshots[period]["values"][metric]
            amount, line_ids = data["amount_toman"], data.get("line_ids")
            if metric == "operating_profit" and amount is not None:
                line_ids = [line_id for component in BUCKETS
                            for line_id in snapshots[period]["values"][component]["line_ids"]]
            if plan.category:
                start, end = PERIODS[period]
                try:
                    rows = detail_rows(conn, start, end, "OPEX", category_id=plan.category)
                except IncompleteCoverage:
                    rows = None
                amount = str(sum((row["amount_toman"] for row in rows), Decimal(0))) if rows is not None else None
                line_ids = [row["line_id"] for row in rows] if rows is not None else None
            value = {"metric": metric, "label": (CATEGORIES[plan.category] if plan.category else LABELS[metric]),
                     "period": period, "amount_toman": amount,
                     "coverage": "complete" if amount is not None else "missing",
                     "line_ids": line_ids, "unit": report["unit"]["code"],
                     "formula": "revenue - cogs - opex" if metric == "operating_profit" else None}
            values.append(value)
            if line_ids is not None and metric in BUCKETS:
                drilldowns.append({"period": period, "bucket": BUCKETS[metric],
                                   "category_id": plan.category, "line_ids": line_ids})
    if any(value["coverage"] == "missing" for value in values):
        message = "پوشش داده برای یکی از شاخص‌ها یا دوره‌های درخواستی ناقص است؛ مقدار ناموجود صفر نیست."
        return {"status": "data_unavailable", "message": message, "view": "none",
                "values": values, "drilldowns": drilldowns, "dataset_id": report["dataset_id"]}
    if plan.intent == "bridge":
        bridge = report["profit_bridge"]
        if bridge["coverage"] != "complete":
            return {"status": "data_unavailable", "message": "پوشش داده برای پل سود ناقص است.",
                    "view": "none", "values": values, "drilldowns": drilldowns}
        def billion(value: str) -> str:
            amount = Decimal(value) / Decimal(1_000_000_000)
            return ("+" if amount > 0 else "") + format(amount, "f")
        message = ("تجزیهٔ حسابداری تغییر سود عملیاتی: تغییر درآمد "
                   f"{billion(report['quarter_changes']['revenue']['amount_toman'])}، "
                   f"بهای کالا {billion(report['quarter_changes']['cogs']['amount_toman'])} و "
                   f"هزینهٔ عملیاتی {billion(report['quarter_changes']['opex']['amount_toman'])}؛ "
                   f"تغییر سود {billion(bridge['profit_delta_toman'])} میلیارد تومان. "
                   "این داده علت تجاری واقعی را مشخص نمی‌کند.")
    elif plan.intent == "trend":
        message = "روند ماهانهٔ شاخص‌های درخواستی از آوریل تا سپتامبر ۲۰۲۶."
    elif plan.intent == "compare":
        message = "مقایسهٔ شاخص‌های درخواستی میان فصل دوم و سوم ۲۰۲۶."
    else:
        message = f"{values[0]['label']} در {plan.periods[0]} سال ۲۰۲۶: {values[0]['amount_toman']} تومان ساختگی."
    result = {"status": "answered", "message": message, "view": plan.view,
              "values": values, "drilldowns": drilldowns, "dataset_id": report["dataset_id"],
              "dataset_version": report["dataset_version"]}
    if plan.intent == "bridge":
        result["bridge"] = bridge
    return result


@router.post("/question")
def ask(payload: Question) -> dict:
    if not configured():
        raise HTTPException(503, "مدل پرسش مالی تنظیم نشده است؛ گزارش نمونه فعال است.")
    plan = plan_question(payload.question)
    if plan.intent == "out_of_scope":
        return execute(plan, None)
    # Reject explicit unsupported years even if a model attempts to silently remap them.
    years = re.findall(r"(?<!\d)(?:20\d{2}|۲[۰-۹]{3})(?!\d)", payload.question)
    if any(year.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")) != "2026" for year in years):
        return _unavailable(years[0])
    try:
        with psycopg.connect(_database_url(), connect_timeout=3) as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            return execute(plan, conn)
    except psycopg.Error:
        raise HTTPException(503, "پایگاه دادهٔ مالی در دسترس نیست.") from None
