"""Read-only, source-linked response for the fixed 2026 Q2/Q3 finance scenario."""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from typing import Literal

import psycopg
from fastapi import APIRouter, HTTPException, Query

from .metrics import (
    IncompleteCoverage,
    MetricSnapshot,
    detail_rows,
    expense_breakdown,
    month_metrics,
    profit_bridge,
    quarter_metrics,
)
from .seed import DATASET_ID

router = APIRouter(prefix="/api/demo-finance", tags=["synthetic-finance"])
BUCKET_FIELDS = {"REVENUE": "revenue", "COGS": "cogs", "OPEX": "opex"}
PERIODS = {
    "q2": (date(2026, 4, 1), date(2026, 7, 1)),
    "q3": (date(2026, 7, 1), date(2026, 10, 1)),
    **{
        f"2026-{month:02d}": (date(2026, month, 1), date(2026, month + 1, 1))
        for month in range(4, 10)
    },
}


def _money(value: Decimal | None) -> str | None:
    """JSON decimal strings preserve each toman exactly."""
    return str(value) if value is not None else None


def _row_json(row: dict[str, object]) -> dict[str, object]:
    return {
        **row,
        "amount_toman": _money(row["amount_toman"]),
        "quantity_delta": _money(row["quantity_delta"]),
        "posted_local_date": row["posted_local_date"].isoformat(),
    }


def _snapshot_json(conn: psycopg.Connection, snapshot: MetricSnapshot,
                   lines: dict[str, dict[str, object]]) -> dict[str, object]:
    values: dict[str, object] = {}
    for bucket, field in BUCKET_FIELDS.items():
        amount = getattr(snapshot, field)
        if amount is None:
            values[field] = {"amount_toman": None, "coverage": "missing", "line_ids": None}
            continue
        rows = detail_rows(conn, snapshot.start, snapshot.end, bucket)
        for row in rows:
            lines[str(row["line_id"])] = _row_json(row)
        values[field] = {
            "amount_toman": _money(amount),
            "coverage": "complete",
            "line_ids": [row["line_id"] for row in rows],
        }
    values["operating_profit"] = {
        "amount_toman": _money(snapshot.operating_profit),
        "coverage": "missing" if snapshot.operating_profit is None else "complete",
        "formula": "revenue - cogs - opex",
        "components": ["revenue", "cogs", "opex"],
    }
    values["operating_margin"] = {
        "ratio": _money(snapshot.operating_margin),
        "reason": snapshot.margin_reason,
        "formula": "operating_profit / revenue",
    }
    return {
        "start": snapshot.start.isoformat(),
        "end_exclusive": snapshot.end.isoformat(),
        "missing_buckets": list(snapshot.missing_buckets),
        "values": values,
    }


def _change(before: dict[str, object], after: dict[str, object],
            field: str) -> dict[str, object]:
    first = before["values"][field]
    second = after["values"][field]
    if first["amount_toman"] is None or second["amount_toman"] is None:
        amount = None
    else:
        amount = str(Decimal(second["amount_toman"]) - Decimal(first["amount_toman"]))
    result = {"amount_toman": amount, "coverage": "missing" if amount is None else "complete"}
    if field in BUCKET_FIELDS.values():
        result["q2_line_ids"] = first["line_ids"]
        result["q3_line_ids"] = second["line_ids"]
    else:
        result["formula"] = "change_revenue - change_cogs - change_opex"
    return result


def _report(conn: psycopg.Connection) -> dict[str, object]:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT version, company_name_fa, base_unit FROM demo_finance.dataset "
            "WHERE dataset_id=%s AND synthetic=true", (DATASET_ID,),
        )
        dataset = cursor.fetchone()
    if dataset is None:
        raise HTTPException(status_code=404, detail="Synthetic finance dataset is not installed")

    lines: dict[str, dict[str, object]] = {}
    quarters = {
        f"q{quarter}": _snapshot_json(conn, quarter_metrics(conn, 2026, quarter), lines)
        for quarter in (2, 3)
    }
    monthly = [
        {"month": f"2026-{month:02d}",
         **_snapshot_json(conn, month_metrics(conn, 2026, month), lines)}
        for month in range(4, 10)
    ]
    changes = {
        field: _change(quarters["q2"], quarters["q3"], field)
        for field in (*BUCKET_FIELDS.values(), "operating_profit")
    }

    q2, q3 = quarter_metrics(conn, 2026, 2), quarter_metrics(conn, 2026, 3)
    if q2.missing_buckets or q3.missing_buckets:
        bridge: dict[str, object] = {"coverage": "missing", "start_profit_toman": None,
                                     "revenue_effect_toman": None, "cogs_effect_toman": None,
                                     "opex_effect_toman": None, "end_profit_toman": None,
                                     "profit_delta_toman": None}
    else:
        amounts = profit_bridge(q2, q3)
        bridge = {
            "coverage": "complete",
            "start_profit_toman": _money(amounts.start_profit),
            "revenue_effect_toman": _money(amounts.revenue_effect),
            "cogs_effect_toman": _money(amounts.cogs_effect),
            "opex_effect_toman": _money(amounts.opex_effect),
            "end_profit_toman": _money(amounts.end_profit),
            "profit_delta_toman": _money(amounts.profit_delta),
            "source_changes": {
                bucket.lower(): {
                    "q2_line_ids": quarters["q2"]["values"][field]["line_ids"],
                    "q3_line_ids": quarters["q3"]["values"][field]["line_ids"],
                }
                for bucket, field in BUCKET_FIELDS.items()
            },
            "formula": "start_profit + revenue_effect + cogs_effect + opex_effect = end_profit",
        }

    if q3.opex is None:
        q3_expenses: dict[str, object] = {"coverage": "missing", "items": None}
    else:
        q3_opex_rows = detail_rows(conn, q3.start, q3.end, "OPEX")
        with conn.cursor() as cursor:
            cursor.execute("SELECT category_id,name_fa FROM demo_finance.category WHERE bucket='OPEX'")
            category_names = dict(cursor.fetchall())
        q3_expenses = {
            "coverage": "complete",
            "items": [
                {
                    "category_id": row["category_id"],
                    "category_name_fa": category_names[row["category_id"]],
                    "cost_center_id": row["cost_center_id"],
                    "amount_toman": _money(row["amount_toman"]),
                    "line_ids": [item["line_id"] for item in q3_opex_rows
                                 if item["category_id"] == row["category_id"]
                                 and item["cost_center_id"] == row["cost_center_id"]],
                }
                for row in expense_breakdown(conn, q3.start, q3.end)
            ],
        }

    return {
        "dataset_id": DATASET_ID,
        "dataset_version": dataset[0],
        "company_name_fa": dataset[1],
        "synthetic": True,
        "unit": {"code": dataset[2], "scale": "toman", "amount_encoding": "decimal_string"},
        "calendar": "gregorian",
        "time_zone": "Asia/Tehran",
        "period": {"start": "2026-04-01", "end_exclusive": "2026-10-01",
                   "label_fa": "دو فصل نمونهٔ ۲۰۲۶"},
        "quarters": quarters,
        "quarter_changes": changes,
        "monthly_trend": monthly,
        "profit_bridge": bridge,
        "q3_operating_expense": q3_expenses,
        "drilldown_lines": [lines[key] for key in sorted(lines)],
    }


def _database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url and not all(os.getenv(key) for key in
                                    ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD")):
        raise HTTPException(status_code=503, detail="Database connection is not configured")
    return database_url or ""


@router.get("/q2-q3-2026")
def q2_q3_2026() -> dict[str, object]:
    """Observed source-linked report. No writes, cached totals, or model calls."""
    try:
        with psycopg.connect(_database_url(), connect_timeout=3) as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            return _report(conn)
    except psycopg.Error:
        raise HTTPException(status_code=503, detail="Finance database is unavailable") from None


@router.get("/lines")
def finance_lines(
    period: Literal["q2", "q3", "2026-04", "2026-05", "2026-06",
                    "2026-07", "2026-08", "2026-09"],
    bucket: Literal["REVENUE", "COGS", "OPEX"],
    category_id: str | None = Query(default=None, max_length=80),
    cost_center_id: str | None = Query(default=None, max_length=80),
) -> dict[str, object]:
    """Filtered bucket rows and subtotal; never calls this subtotal center profit."""
    start, end = PERIODS[period]
    try:
        with psycopg.connect(_database_url(), connect_timeout=3) as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            try:
                rows = detail_rows(conn, start, end, bucket,
                                   category_id=category_id, cost_center_id=cost_center_id)
            except IncompleteCoverage:
                return {
                    "period": period, "start": start.isoformat(), "end_exclusive": end.isoformat(),
                    "unit": "TOMAN_SYNTHETIC", "bucket": bucket,
                    "category_id": category_id, "cost_center_id": cost_center_id,
                    "coverage": "missing", "bucket_subtotal_toman": None, "lines": None,
                }
            return {
                "period": period, "start": start.isoformat(), "end_exclusive": end.isoformat(),
                "unit": "TOMAN_SYNTHETIC", "bucket": bucket,
                "category_id": category_id, "cost_center_id": cost_center_id,
                "coverage": "complete",
                "bucket_subtotal_toman": _money(sum(
                    (row["amount_toman"] for row in rows), Decimal(0))),
                "lines": [_row_json(row) for row in rows],
            }
    except psycopg.Error:
        raise HTTPException(status_code=503, detail="Finance database is unavailable") from None
