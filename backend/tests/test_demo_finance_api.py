"""HTTP checks against dedicated PostgreSQL, with literal independent expectations."""

from __future__ import annotations

import os
from decimal import Decimal

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.conninfo import conninfo_to_dict

from app.demo_finance.seed import DATASET_ID, canonical_snapshot, install_schema, seed
from app.main import app

B = 1_000_000_000


@pytest.fixture(scope="module")
def database_url() -> str:
    url = os.getenv("TEST_API_DATABASE_URL")
    if not url:
        pytest.fail("TEST_API_DATABASE_URL is required for PostgreSQL API tests")
    info = conninfo_to_dict(url)
    if info.get("dbname") != "viradata_finance_test_api" or info.get("host") not in (
        "127.0.0.1", "localhost"
    ):
        pytest.fail("API tests require dedicated local viradata_finance_test_api")
    with psycopg.connect(url, autocommit=True) as conn:
        install_schema(conn)
        seed(conn)
    return url


@pytest.fixture
def client(database_url: str, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", database_url)
    return TestClient(app)


def test_scenario_http_numbers_sources_and_no_write(client: TestClient, database_url: str):
    with psycopg.connect(database_url) as conn:
        before = canonical_snapshot(conn)
    response = client.get("/api/demo-finance/q2-q3-2026")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["dataset_id"] == DATASET_ID
    assert data["dataset_version"] == "1.0.0"
    assert data["unit"] == {"code": "TOMAN_SYNTHETIC", "scale": "toman",
                            "amount_encoding": "decimal_string"}
    assert data["period"]["start"] == "2026-04-01"
    assert data["period"]["end_exclusive"] == "2026-10-01"
    assert data["time_zone"] == "Asia/Tehran"

    expected_quarters = {
        "q2": (120, 84, 18, 18),
        "q3": (135, 101, 24, 10),
    }
    for key, amounts in expected_quarters.items():
        values = data["quarters"][key]["values"]
        assert [values[field]["amount_toman"] for field in
                ("revenue", "cogs", "opex", "operating_profit")] == [
                    str(n * B) for n in amounts
                ]
        assert data["quarters"][key]["missing_buckets"] == []

    expected_months = [
        (38, 26, 5, 7), (40, 28, 6, 6), (42, 30, 7, 5),
        (44, 32, 7, 5), (46, 34, 8, 4), (45, 35, 9, 1),
    ]
    for month, expected in zip(data["monthly_trend"], expected_months):
        assert [month["values"][field]["amount_toman"] for field in
                ("revenue", "cogs", "opex", "operating_profit")] == [
                    str(n * B) for n in expected
                ]

    assert [data["quarter_changes"][field]["amount_toman"] for field in
            ("revenue", "cogs", "opex", "operating_profit")] == [
                str(n * B) for n in (15, 17, 6, -8)
            ]
    bridge = data["profit_bridge"]
    assert [bridge[key] for key in
            ("start_profit_toman", "revenue_effect_toman", "cogs_effect_toman",
             "opex_effect_toman", "end_profit_toman", "profit_delta_toman")] == [
                 str(n * B) for n in (18, 15, -17, -6, 10, -8)
             ]
    assert {item["category_id"]: item["amount_toman"] for item in
            data["q3_operating_expense"]["items"]} == {
                "payroll": str(12 * B), "shipping": str(9 * B), "admin": str(3 * B)
            }

    indexed = {row["line_id"]: row for row in data["drilldown_lines"]}
    assert len(indexed) == 36
    for period in [*data["quarters"].values(), *data["monthly_trend"]]:
        for bucket, field in (("REVENUE", "revenue"), ("COGS", "cogs"), ("OPEX", "opex")):
            figure = period["values"][field]
            assert sum((Decimal(indexed[line_id]["amount_toman"])
                        for line_id in figure["line_ids"]), Decimal(0)) == Decimal(
                            figure["amount_toman"])
            assert all(indexed[line_id]["bucket"] == bucket and
                       indexed[line_id]["document_id"] for line_id in figure["line_ids"])
    for item in data["q3_operating_expense"]["items"]:
        assert sum((Decimal(indexed[line_id]["amount_toman"])
                    for line_id in item["line_ids"]), Decimal(0)) == Decimal(
                        item["amount_toman"])
    with psycopg.connect(database_url) as conn:
        assert canonical_snapshot(conn) == before


def test_filtered_drilldown_is_bucket_subtotal_not_center_profit(client: TestClient):
    response = client.get("/api/demo-finance/lines", params={
        "period": "q3", "bucket": "OPEX", "category_id": "shipping",
        "cost_center_id": "operations",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["bucket_subtotal_toman"] == str(9 * B)
    assert len(data["lines"]) == 3
    assert "operating_profit" not in data
    assert sum(Decimal(row["amount_toman"]) for row in data["lines"]) == Decimal(9 * B)
    assert client.get("/api/demo-finance/lines", params={
        "period": "q1", "bucket": "OPEX"
    }).status_code == 422


def test_incomplete_coverage_is_null_not_zero(client: TestClient, database_url: str):
    try:
        with psycopg.connect(database_url) as conn:
            conn.execute(
                "UPDATE demo_finance.period_coverage SET coverage_status='incomplete',"
                "verified_at=NULL WHERE dataset_id=%s AND month_start='2026-08-01' "
                "AND bucket='OPEX'", (DATASET_ID,),
            )
        response = client.get("/api/demo-finance/q2-q3-2026")
        assert response.status_code == 200, response.text
        data = response.json()
        august = data["monthly_trend"][4]
        assert august["values"]["opex"] == {
            "amount_toman": None, "coverage": "missing", "line_ids": None
        }
        assert august["values"]["operating_profit"]["amount_toman"] is None
        assert data["quarters"]["q3"]["values"]["opex"]["amount_toman"] is None
        assert data["profit_bridge"]["coverage"] == "missing"
        assert data["q3_operating_expense"] == {"coverage": "missing", "items": None}
        detail = client.get("/api/demo-finance/lines", params={
            "period": "2026-08", "bucket": "OPEX"
        }).json()
        assert detail["bucket_subtotal_toman"] is None and detail["lines"] is None
    finally:
        with psycopg.connect(database_url) as conn:
            conn.execute(
                "UPDATE demo_finance.period_coverage SET coverage_status='complete',"
                "verified_at='2026-10-01T08:30:00+00:00' "
                "WHERE dataset_id=%s AND month_start='2026-08-01' AND bucket='OPEX'",
                (DATASET_ID,),
            )


def test_api_reports_unconfigured_database(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DATABASE_URL")
    for key in ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD"):
        monkeypatch.delenv(key, raising=False)
    response = client.get("/api/demo-finance/q2-q3-2026")
    assert response.status_code == 503
    assert response.json()["detail"] == "Database connection is not configured"
