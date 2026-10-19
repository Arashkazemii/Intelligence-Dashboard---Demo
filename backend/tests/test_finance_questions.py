"""Question boundary: model plans, approved metrics supply all amounts and sources."""

import json
from contextlib import contextmanager
from urllib import error

import pytest
from fastapi.testclient import TestClient

from app.demo_finance import questions
from app.main import app


def fake_report(missing=False):
    def snapshot(revenue, cogs, opex, prefix):
        values = {}
        for key, amount in (("revenue", revenue), ("cogs", cogs), ("opex", opex)):
            values[key] = {"amount_toman": None if missing and key == "opex" else str(amount * 10**9),
                           "line_ids": None if missing and key == "opex" else [f"{prefix}-{key}"]}
        values["operating_profit"] = {"amount_toman": None if missing else str((revenue - cogs - opex) * 10**9)}
        return {"values": values}
    return {"dataset_id": "synthetic-test", "dataset_version": "1.0.0",
            "unit": {"code": "TOMAN_SYNTHETIC"},
            "quarters": {"q2": snapshot(120, 84, 18, "q2"), "q3": snapshot(135, 101, 24, "q3")},
            "monthly_trend": [{"month": f"2026-{month:02d}", **snapshot(40, 28, 6, str(month))}
                              for month in range(4, 10)],
            "quarter_changes": {"revenue": {"amount_toman": str(15 * 10**9)},
                                "cogs": {"amount_toman": str(17 * 10**9)},
                                "opex": {"amount_toman": str(6 * 10**9)}},
            "q3_operating_expense": {"coverage": "complete", "items": [
                {"category_id": "shipping", "category_name_fa": "حمل", "cost_center_id": "sales",
                 "amount_toman": str(9 * 10**9), "line_ids": ["shipping-source"]}]},
            "profit_bridge": {"coverage": "complete", "start_profit_toman": str(18 * 10**9),
                              "revenue_effect_toman": str(15 * 10**9),
                              "cogs_effect_toman": str(-17 * 10**9),
                              "opex_effect_toman": str(-6 * 10**9),
                              "end_profit_toman": str(10 * 10**9),
                              "profit_delta_toman": str(-8 * 10**9)}}


class ModelResponse:
    def __init__(self, plan):
        self.data = json.dumps({"choices": [{"message": {"content": json.dumps(plan)}}]}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def read(self, *_):
        return self.data


@pytest.fixture
def model(monkeypatch):
    for key, value in {"FINANCE_LLM_BASE_URL": "http://127.0.0.1:9999/v1",
                       "FINANCE_LLM_MODEL": "fake", "FINANCE_LLM_API_KEY": "test-placeholder"}.items():
        monkeypatch.setenv(key, value)
    plans = []

    def urlopen(req, timeout):
        assert timeout == 12
        body = json.loads(req.data)
        assert "SELECT" not in body["messages"][1]["content"]
        return ModelResponse(plans.pop(0))

    monkeypatch.setattr(questions.request, "urlopen", urlopen)
    return plans


@pytest.fixture
def data(monkeypatch):
    monkeypatch.setattr(questions, "_report", lambda conn: fake_report())

    @contextmanager
    def connect(*_args, **_kwargs):
        class Connection:
            def execute(self, sql):
                assert sql == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
        yield Connection()

    monkeypatch.setattr(questions.psycopg, "connect", connect)
    monkeypatch.setattr(questions, "_database_url", lambda: "test-only")
    monkeypatch.setattr(questions, "detail_rows", lambda conn, start, end, bucket, **kwargs:
                        [{"line_id": "shipping-source", "amount_toman": 9 * 10**9}])


def plan(intent="bridge", metrics=None, periods=None, category=None, view="bridge"):
    return {"intent": intent, "metrics": metrics or list(questions.LABELS),
            "periods": periods or ["q2", "q3"], "category": category, "view": view}


def test_overview_is_five_widgets_with_reconciled_insight(model, data):
    model.append(plan("overview", view="dashboard"))
    result = TestClient(app).post("/api/demo-finance/question", json={"question": "داشبورد برام درست کن از تمامی گزارشات"}).json()
    assert result["status"] == "answered" and result["layout"] == "overview"
    assert result["widgets"] == ["kpis", "trend", "comparison", "bridge", "expense_mix"]
    assert len(result["values"]) == 8  # Two quarters, four KPIs; no monthly cards.
    assert result["dataset_version"] == "1.0.0"
    insight = result["insights"][0]
    assert insight["components"] == {"revenue": str(15 * 10**9), "cogs": str(17 * 10**9), "opex": str(6 * 10**9)}
    assert int(insight["components"]["revenue"]) - int(insight["components"]["cogs"]) - int(insight["components"]["opex"]) == int(insight["amount_toman"]) == -8 * 10**9
    assert "علت تجاری واقعی" in insight["basis"] and insight["line_ids"]


def test_six_month_revenue_profit_trend_has_only_requested_series(model, data):
    model.append(plan("trend", ["revenue", "operating_profit"], [f"2026-{m:02d}" for m in range(4, 10)], view="trend"))
    result = TestClient(app).post("/api/demo-finance/question", json={"question": "روند شش‌ماههٔ درآمد و سود چگونه بود؟"}).json()
    assert result["widgets"] == ["trend"]
    assert len(result["values"]) == 12
    assert {value["metric"] for value in result["values"]} == {"revenue", "operating_profit"}
    assert all(value["line_ids"] for value in result["values"])


@pytest.mark.parametrize("question", ["درآمد ۲۰۲۷ چقدر بود؟", "سود فصل چهارم چقدر بود؟"])
def test_explicit_unsupported_period_is_not_silently_remapped(model, data, question):
    result = TestClient(app).post("/api/demo-finance/question", json={"question": question}).json()
    assert result["status"] == "data_unavailable" and result["values"] == []


@pytest.mark.parametrize("question", ["چرا سود فصل سوم کمتر شد؟", "علت افت سود عملیاتی از فصل دو به سه چیست؟"])
def test_persian_paraphrases_use_same_accounting_bridge(model, data, question):
    model.append(plan())
    response = TestClient(app).post("/api/demo-finance/question", json={"question": question})
    assert response.status_code == 200
    result = response.json()
    assert result["view"] == "bridge"
    assert result["bridge"]["profit_delta_toman"] == str(-8 * 10**9)
    assert "تجزیهٔ حسابداری تغییر" in result["message"]
    assert "علت تجاری واقعی را مشخص نمی‌کند" in result["message"]
    assert result["values"][0]["line_ids"] == ["q2-revenue"]


def test_shipping_amount_uses_approved_filtered_rows(model, data):
    model.append(plan("metric", ["opex"], ["q3"], "shipping", "card"))
    result = TestClient(app).post("/api/demo-finance/question", json={"question": "هزینهٔ حمل چقدر بود؟"}).json()
    assert result["values"][0]["amount_toman"] == str(9 * 10**9)
    assert result["drilldowns"][0]["line_ids"] == ["shipping-source"]


def test_trend_and_comparison_return_only_requested_values(model, data):
    model.extend([plan("trend", ["revenue"], [f"2026-{m:02d}" for m in range(4, 10)], view="trend"),
                  plan("compare", ["revenue", "operating_profit"], ["q2", "q3"], view="comparison")])
    client = TestClient(app)
    trend = client.post("/api/demo-finance/question", json={"question": "روند درآمد را نشان بده"}).json()
    assert trend["view"] == "trend" and len(trend["values"]) == 6
    assert all(value["metric"] == "revenue" and value["line_ids"] for value in trend["values"])
    comparison = client.post("/api/demo-finance/question", json={"question": "فصل دوم و سوم را مقایسه کن"}).json()
    assert comparison["view"] == "comparison" and len(comparison["values"]) == 4
    assert comparison["values"][3]["amount_toman"] == str(10 * 10**9)
    assert comparison["values"][3]["formula"] == "revenue - cogs - opex"


def test_out_of_scope_and_absent_period(model, data):
    model.extend([plan("out_of_scope", [], [], view="none"),
                  plan("metric", ["revenue"], ["2027-01"], view="card")])
    client = TestClient(app)
    scope = client.post("/api/demo-finance/question", json={"question": "سلام"}).json()
    assert scope["status"] == "out_of_scope" and scope["values"] == []
    absent = client.post("/api/demo-finance/question", json={"question": "درآمد ژانویه ۲۰۲۷ چقدر بود؟"}).json()
    assert absent["status"] == "data_unavailable" and absent["values"] == []


def test_invalid_model_and_sql_payload_rejected(model, data, caplog):
    client = TestClient(app)
    model.append({**plan("metric", ["revenue"], ["q3"], view="card"), "sql": "DROP TABLE demo_finance.line"})
    assert client.post("/api/demo-finance/question", json={"question": "درآمد چقدر بود؟"}).status_code == 502
    assert "finance model response invalid: ValidationError" in caplog.text
    assert "DROP TABLE" not in caplog.text and "test-placeholder" not in caplog.text
    model.append(plan("metric", ["revenue; DROP TABLE demo_finance.line"], ["q3"], view="card"))
    result = client.post("/api/demo-finance/question", json={"question": "درآمد چقدر بود؟"}).json()
    assert result["status"] == "data_unavailable"


def test_model_timeout_returns_service_error(model, data, monkeypatch):
    def timeout(*_args, **_kwargs):
        raise error.URLError("timed out")
    monkeypatch.setattr(questions.request, "urlopen", timeout)
    response = TestClient(app).post("/api/demo-finance/question", json={"question": "درآمد چقدر بود؟"})
    assert response.status_code == 503
    assert "سرویس مدل" in response.json()["detail"]


def test_incomplete_coverage_is_not_zero(monkeypatch):
    monkeypatch.setattr(questions, "_report", lambda conn: fake_report(missing=True))
    result = questions.execute(questions.Plan.model_validate(plan("metric", ["opex"], ["q3"], view="card")), object())
    assert result["status"] == "data_unavailable"
    assert result["values"][0]["amount_toman"] is None


def test_unconfigured_capability_keeps_report_separate(monkeypatch):
    for key in ("FINANCE_LLM_BASE_URL", "FINANCE_LLM_MODEL", "FINANCE_LLM_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    client = TestClient(app)
    assert client.get("/api/demo-finance/question-capability").json()["enabled"] is False
    assert client.post("/api/demo-finance/question", json={"question": "درآمد چقدر بود؟"}).status_code == 503
