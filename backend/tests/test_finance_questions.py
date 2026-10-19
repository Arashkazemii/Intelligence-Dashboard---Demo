"""End-to-end bounded planning, exact fixture arithmetic and safe dynamic composition."""

import json
from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from urllib import error

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.demo_finance import dashboard_data as data_module
from app.demo_finance import questions
from app.demo_finance.dashboard_data import DataBuilder
from app.demo_finance.dashboard_schema import DataPlan, DataQuery, ChartSpec, SpecViolation, validate_chart
from app.demo_finance.seed import build_seed_payload
from app.main import app

MONTHS = [f"2026-{m:02d}" for m in range(4, 10)]
FINANCE = ["revenue", "cogs", "opex", "operating_profit"]


class Cursor:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def execute(self, sql, params):
        assert sql.startswith("SELECT version FROM demo_finance.dataset")

    def fetchone(self):
        return ("1.0.0",)


class Connection:
    def execute(self, sql):
        assert sql == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"

    def cursor(self):
        return Cursor()


@pytest.fixture
def data(monkeypatch):
    seed = build_seed_payload()
    documents = {d["document_id"]: d for d in seed["documents"]}

    def rows(conn, start, end, bucket):
        return [{**row, "amount_toman": Decimal(row["amount_toman"])} for row in seed["lines"]
                if row["bucket"] == bucket and start <= documents[row["document_id"]]["posted_at"].date() < end]

    def snapshot(conn, start, end):
        values = {key: sum((r["amount_toman"] for r in rows(conn, start, end, bucket)), Decimal(0))
                  for key, bucket in {"revenue": "REVENUE", "cogs": "COGS", "opex": "OPEX"}.items()}
        return SimpleNamespace(**values, operating_profit=values["revenue"] - values["cogs"] - values["opex"])

    @contextmanager
    def connect(*_args, **_kwargs):
        yield Connection()

    monkeypatch.setattr(data_module, "detail_rows", rows)
    monkeypatch.setattr(data_module, "period_metrics", snapshot)
    monkeypatch.setattr(questions.psycopg, "connect", connect)
    monkeypatch.setattr(questions, "_database_url", lambda: "test-only")
    return DataBuilder(Connection())


class Response:
    def __init__(self, payload):
        self.payload = json.dumps({"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}, "finish_reason": "stop"}]}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def read(self, *_):
        return self.payload


@pytest.fixture
def model(monkeypatch):
    for key, value in {"FINANCE_LLM_BASE_URL": "http://127.0.0.1:9999/v1", "FINANCE_LLM_MODEL": "test", "FINANCE_LLM_API_KEY": "secret-test-placeholder"}.items():
        monkeypatch.setenv(key, value)
    queue, requests = [], []

    def urlopen(req, timeout):
        assert 0 < timeout <= 40
        body = json.loads(req.data)
        requests.append(body)
        assert body["max_tokens"] <= 5200
        return Response(queue.pop(0))

    monkeypatch.setattr(questions.request, "urlopen", urlopen)
    return queue, requests


def query(id="q", metrics=None, periods=None, dimension="period", category=None):
    return {"id": id, "metrics": metrics or FINANCE, "periods": periods or ["q2", "q3"], "dimension": dimension, "category": category}


def plan(*queries):
    return {"scope": "finance", "queries": list(queries), "reason": "دادهٔ مرتبط با سؤال"}


def chart(id, type, dataset, fields, axis=None):
    return {"id": id, "type": type, "title": "مقایسهٔ مقادیر", "dataset_id": dataset, "x": "label",
            "series": [{"field": f, "axis": (axis or {}).get(f, "left")} for f in fields], "width": "full"}


def insight(metric="revenue", kind="positive", id="finding", dataset="q"):
    ref = f"{dataset}:change:{metric}"
    return {"id": id, "title": "تغییر قابل بررسی", "text": "تغییر ثبت‌شده برابر {{" + ref + "}} است.",
            "kind": kind, "priority": 1, "fact_ids": [ref], "baseline": "آخرین دوره در مقایسه با اولین دورهٔ موجود",
            "scope": "فقط دادهٔ مالی ساختگی و دوره‌های مشاهده‌شده؛ علت تجاری اثبات نمی‌شود."}


def compose(answer="درآمد فصل سوم {{q:q3:revenue}} است.", cards=None, charts=None, tables=None, insights=None):
    parts = {"cards": cards or [], "charts": charts or [], "tables": tables or [], "insights": insights or []}
    if not any(parts.values()):
        parts["cards"] = [{"id": "amount", "title": "درآمد فصل سوم", "fact_id": "q:q3:revenue"}]
    return {"kind": "dashboard", "spec": {"version": "2.0", "title": "پاسخ مالی", "answer": answer,
            "layout": [part["id"] for values in parts.values() for part in values], **parts}}


def post():
    return TestClient(app).post("/api/demo-finance/question", json={"question": "داشبورد بده"})


def test_model_receives_real_data_then_composes_dynamic_spec(model, data):
    queue, calls = model
    queue.extend([plan(query()), compose(insights=[insight()])])
    response = post()
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "answered" and result["spec"]["version"] == "2.0"
    assert "135 میلیارد تومان" in result["message"]
    assert "15 میلیارد تومان" in result["spec"]["insights"][0]["text"]
    assert len(calls) == 2
    planner_context = json.loads(calls[0]["messages"][1]["content"])
    assert "datasets" not in planner_context
    composition_context = json.loads(calls[1]["messages"][1]["content"])
    assert composition_context["datasets"][0]["rows"][1]["revenue"] == 135
    assert composition_context["datasets"][0]["rows"][1]["source_ids"]
    assert all("drilldowns" not in r for d in composition_context["datasets"] for r in d["rows"])
    assert result["meta"] == {"model_calls": 2, "supplementary_requests": 0}


def test_exact_posted_arithmetic_shipping_share_bridge_and_zero_denominator(data):
    data.add([DataQuery.model_validate(query("q", ["shipping", "opex"])),
              DataQuery.model_validate(query("b", dimension="bridge"))])
    facts = {f["id"]: f for f in data.facts}
    assert facts["q:q2:shipping"]["raw_value"] == "5000000000"
    assert facts["q:q3:shipping"]["value"] == 9
    assert facts["q:change:shipping"]["value"] == 4
    assert facts["q:change_pct:shipping"]["value"] == 80
    assert facts["q:q3:shipping_share"]["value"] == 37.5
    assert facts["q:change:shipping"]["favorable"] is False
    bridge = data.datasets[1]["rows"]
    assert [r["value"] for r in bridge] == [18, 15, -17, -6, 10]
    assert sum(r["value"] for r in bridge[:-1]) == bridge[-1]["value"]
    assert all(f["source_ids"] and f["definition"] for f in data.facts)
    # Zero and negative baselines never produce a manufactured percent change.
    original = data.metric
    data.metric = lambda period, metric, category=None: (Decimal(0), [], []) if period == "q2" else original(period, metric, category)
    data.add([DataQuery.model_validate(query("zero", ["shipping"]))])
    assert next(f for f in data.facts if f["id"] == "zero:change_pct:shipping")["value"] is None


def test_filtered_expense_changes_preserve_category_meaning_and_sources(data):
    data.add([DataQuery.model_validate(query("filtered", ["opex"], category="shipping"))])
    facts = {fact["id"]: fact for fact in data.facts}
    change = facts["filtered:change:opex"]
    assert change["raw_value"] == "4000000000" and change["metric"] == "shipping"
    assert "حمل" in change["label"] and "حمل" in change["definition"]
    assert all(link["category_id"] == "shipping" for link in change["drilldowns"])
    assert facts["filtered:change_pct:opex"]["value"] == 80


def test_shipping_dynamic_components_do_not_require_fixed_dashboard_intent(model, data):
    queue, _ = model
    queue.extend([plan(query("q", ["shipping", "opex"]), query("m", ["shipping", "opex"], MONTHS),
                       query("centers", ["opex"], ["q3"], "cost_center", "shipping")),
                  compose("حمل فصل سوم {{q:q3:shipping}}؛ افزایش نسبت به فصل دوم {{q:change_pct:shipping}} است.",
                          cards=[{"id": "cost", "title": "حمل فصل سوم", "fact_id": "q:q3:shipping"},
                                 {"id": "share", "title": "سهم از هزینهٔ عملیاتی", "fact_id": "q:q3:shipping_share"}],
                          charts=[chart("shipping_months", "line", "m", ["shipping"]),
                                  chart("shipping_share", "composed", "m", ["shipping", "shipping_share"], {"shipping_share": "right"})],
                          tables=[{"id": "sources", "title": "مرکز هزینهٔ موجود", "dataset_id": "centers", "columns": ["label", "value"]}],
                          insights=[insight("shipping", "negative")])])
    response = TestClient(app).post("/api/demo-finance/question", json={"question": "داشبورد حمل بده"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert {f["metric"] for f in body["facts"]} <= {"shipping", "opex", "shipping_share"}
    assert "80 درصد" in body["message"]
    assert [r["shipping"] for r in body["datasets"][1]["rows"]] == [1, 2, 2, 2, 3, 4]
    assert len(body["datasets"][2]["rows"]) == 1


@pytest.mark.parametrize("question,kind,charts,tables,findings", [
    ("داشبورد بده", "overview", [chart("trend", "line", "m", ["revenue", "operating_profit"])], [], [insight()]),
    ("داشبورد گزارشی بده", "report", [chart("bridge", "waterfall", "b", ["value"])], [{"id": "table", "title": "مقایسهٔ دوره‌ها", "dataset_id": "q", "columns": ["label", "revenue", "operating_profit"]}], [insight(), insight("operating_profit", "negative", "weakness")]),
    ("نقاط قوت و ضعف را نشان بده", "strengths", [], [], [insight(), insight("operating_profit", "negative", "weakness")]),
    ("روند درآمد را نشان بده", "trend", [chart("trend", "area", "m", ["revenue"])], [], [insight()]),
    ("فصل دوم و سوم را مقایسه کن", "comparison", [chart("comparison", "grouped_bar", "q", FINANCE)], [], [insight()]),
])
def test_sample_questions_have_question_driven_composition(model, data, question, kind, charts, tables, findings):
    queue, _ = model
    queue.extend([plan(query(), query("m", ["revenue", "operating_profit"], MONTHS), query("b", dimension="bridge")),
                  compose(charts=charts, tables=tables, insights=findings)])
    response = TestClient(app).post("/api/demo-finance/question", json={"question": question})
    assert response.status_code == 200, (kind, response.text)
    result = response.json()["spec"]
    assert [c["type"] for c in result["charts"]] == [c["type"] for c in charts]
    assert bool(result["tables"]) == bool(tables)
    assert len(result["insights"]) == len(findings)


@pytest.mark.parametrize("type,dataset,fields", [
    ("line", "monthly", ["shipping"]), ("area", "monthly", ["shipping"]),
    ("bar", "q", ["revenue"]), ("horizontal_bar", "mix", ["value"]),
    ("grouped_bar", "q", ["revenue", "operating_profit"]),
    ("stacked_bar", "monthly", ["payroll", "shipping", "admin"]),
    ("composed", "related", ["shipping", "shipping_share"]),
    ("pie", "mix", ["value"]), ("donut", "mix", ["value"]), ("radial", "mix", ["value"]),
    ("waterfall", "bridge", ["value"]), ("radar", "indices", ["q2", "q3"]),
])
def test_all_supported_chart_families_validate_real_fixture_inputs(data, type, dataset, fields):
    data.add([DataQuery.model_validate(q) for q in [query("monthly", ["payroll", "shipping", "admin"], MONTHS),
              query("q"), query("mix", ["opex"], ["q3"], "category"),
              query("related", ["shipping", "opex"], MONTHS), query("bridge", dimension="bridge"),
              query("indices", FINANCE, ["q2", "q3"], "normalized")]])
    spec = ChartSpec.model_validate(chart("plot", type, dataset, fields, {"shipping_share": "right"}))
    validate_chart(spec, next(d for d in data.datasets if d["id"] == dataset))


def test_only_one_supplementary_data_request_allowed(model, data):
    queue, _ = model
    queue.extend([plan(query("q", ["revenue"])), {"kind": "data_request", "queries": [query("m", ["revenue"], MONTHS)]},
                  compose(charts=[chart("trend", "line", "m", ["revenue"])])])
    result = post().json()
    assert result["meta"] == {"model_calls": 3, "supplementary_requests": 1}
    queue.extend([plan(query("q", ["revenue"])), {"kind": "data_request", "queries": [query("m", ["revenue"], MONTHS)]},
                  {"kind": "data_request", "queries": [query("more", ["cogs"], MONTHS)]}])
    response = post()
    assert response.status_code == 422 and response.json()["detail"]["code"] == "data_limit"


@pytest.mark.parametrize("scope,status", [("out_of_scope", "out_of_scope"), ("unavailable", "data_unavailable")])
def test_data_scope_is_explicit_without_fabricated_dashboard(model, data, scope, status):
    model[0].append({"scope": scope, "queries": [], "reason": "خارج از داده"})
    result = post().json()
    assert result["status"] == status and result["spec"] is None and result["facts"] == []


@pytest.mark.parametrize("question", ["درآمد ۲۰۲۷ چقدر بود؟", "فصل چهارم را نشان بده", "سود ٢٠٢٥ چقدر است؟"])
def test_explicit_unsupported_period_not_silently_remapped(model, data, question):
    result = TestClient(app).post("/api/demo-finance/question", json={"question": question}).json()
    assert result["status"] == "data_unavailable" and not model[1]


def test_missing_coverage_is_not_zero(model, data, monkeypatch):
    from app.demo_finance.metrics import IncompleteCoverage

    def missing(*_):
        raise IncompleteCoverage("missing")

    monkeypatch.setattr(data_module, "detail_rows", missing)
    model[0].append(plan(query("q", ["shipping"])))
    result = post().json()
    assert result["status"] == "data_unavailable" and result["spec"] is None
    assert len(model[1]) == 1


@pytest.mark.parametrize("payload", ['{"a":1,"a":2}', '{"a":NaN}', '[]', 'prefix {"a":1}', '{"a":Infinity}', '{"a":1e999}', None, []])
def test_ambiguous_or_nonfinite_json_rejected(payload):
    with pytest.raises((ValueError, TypeError)):
        questions.strict_json(payload)


def test_fenced_json_accepted():
    assert questions.strict_json('```json\n{"ok":true}\n```') == {"ok": True}


def test_numeric_word_detection_uses_whole_words():
    from app.demo_finance.dashboard_schema import NUMBER_WORD
    assert not NUMBER_WORD.search("تغییر ثبت‌شده برابر مقدار معتبر است.")
    assert NUMBER_WORD.search("درآمد ده میلیارد تومان است.")


def test_injected_sql_and_unknown_metric_rejected_before_database(model, data, caplog):
    injected = {**plan(query()), "sql": "DROP TABLE finance"}
    model[0].extend([injected, injected])
    response = post()
    assert response.status_code == 502 and response.json()["detail"]["code"] == "invalid_spec"
    assert "DROP TABLE" not in caplog.text and "secret-test-placeholder" not in caplog.text
    invalid_metric = plan(query(metrics=["revenue;DROP"]))
    model[0].extend([invalid_metric, invalid_metric])
    assert post().status_code == 502


def test_invalid_json_service_timeout_and_chart_are_distinct(model, data, monkeypatch):
    def timeout(*_, **__):
        raise error.URLError("timed out")

    old = questions.request.urlopen
    monkeypatch.setattr(questions.request, "urlopen", timeout)
    assert post().json()["detail"]["code"] == "model_timeout"

    def unavailable(*_, **__):
        raise error.HTTPError("https://provider.invalid", 503, "unavailable", None, None)

    monkeypatch.setattr(questions.request, "urlopen", unavailable)
    assert post().json()["detail"]["code"] == "model_unavailable"

    def invalid(*_, **__):
        response = Response({})
        response.payload = b'{"choices":[{"message":{"content":"{broken"}}]}'
        return response

    monkeypatch.setattr(questions.request, "urlopen", invalid)
    assert post().json()["detail"]["code"] == "invalid_json"
    monkeypatch.setattr(questions.request, "urlopen", old)
    invalid_chart = compose(charts=[chart("fake", "sankey", "q", ["revenue"])])
    model[0].extend([plan(query()), invalid_chart, invalid_chart])
    response = post()
    assert response.status_code == 502 and response.json()["detail"]["code"] == "unsupported_chart"


def test_model_repairs_invalid_numeric_prose_once_without_fallback(model, data):
    queue, calls = model
    bad = compose("درآمد فصل سوم 999 میلیارد تومان است.")
    queue.extend([plan(query()), bad, compose()])
    response = post()
    assert response.status_code == 200, response.text
    assert "135 میلیارد تومان" in response.json()["message"]
    assert response.json()["meta"] == {"model_calls": 3, "supplementary_requests": 0}
    repair_context = json.loads(calls[-1]["messages"][1]["content"])
    assert repair_context["repair"]["code"] == "unbound_numeric_claim"
    assert repair_context["repair"]["field"] == "answer"
    assert repair_context["repair"]["details"]["unbound_token"] == "999"
    assert repair_context["supplementary_request_allowed"] is False
    queue.extend([plan(query()), bad, bad])
    response = post()
    assert response.status_code == 502 and response.json()["detail"]["code"] == "unbound_numeric_claim"


def test_plan_repair_shares_three_call_budget_and_sends_specific_validation(model, data):
    queue, calls = model
    invalid = plan(query("q", ["shipping", "opex"], ["q2", "q3", "2026-04"]))
    queue.extend([invalid, plan(query()), compose()])
    response = post()
    assert response.status_code == 200, response.text
    assert response.json()["meta"] == {"model_calls": 3, "supplementary_requests": 0}
    repair = json.loads(calls[1]["messages"][1]["content"])["repair"]
    assert "overlapping quarter and month" in repair["validation"][0]["message"]
    composition = json.loads(calls[2]["messages"][1]["content"])
    assert composition["supplementary_request_allowed"] is False
    # No fourth call is spent to repair a draft after a planning repair.
    queue.extend([invalid, plan(query()), compose("درآمد 999 میلیارد تومان است.")])
    response = post()
    assert response.status_code == 502 and len(queue) == 0


def test_query_rejects_overlap_and_nonadditive_filters():
    for q in [query(periods=["q2", "2026-04"]), query(metrics=["revenue"], category="shipping"),
              query(metrics=["shipping"], dimension="category"), query(metrics=["revenue"], dimension="normalized")]:
        with pytest.raises(ValidationError):
            DataQuery.model_validate(q)


def test_model_budget_caps_context_and_hides_raw_response(model, data):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        questions.model_json("system", "x" * (questions.MAX_CONTEXT_BYTES + 1), stage="compose")
    assert exc.value.status_code == 422 and exc.value.detail["code"] == "data_limit"


def test_capability_unconfigured_keeps_observed_report_separate(monkeypatch):
    for key in ("FINANCE_LLM_BASE_URL", "FINANCE_LLM_MODEL", "FINANCE_LLM_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    client = TestClient(app)
    assert client.get("/api/demo-finance/question-capability").json()["enabled"] is False
    assert post().json()["detail"]["code"] == "model_unconfigured"
