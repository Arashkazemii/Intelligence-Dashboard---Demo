"""Approved, parameterized calculations over synthetic posted finance lines."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row

from .seed import DATASET_ID

BUCKETS = ("REVENUE", "COGS", "OPEX")
ZERO = Decimal(0)


class IncompleteCoverage(ValueError):
    """A monetary total cannot be reported for an incomplete period."""


@dataclass(frozen=True)
class MetricSnapshot:
    dataset_id: str
    start: date
    end: date
    revenue: Decimal | None
    cogs: Decimal | None
    opex: Decimal | None
    operating_profit: Decimal | None
    operating_margin: Decimal | None
    margin_reason: str | None
    missing_buckets: tuple[str, ...]


@dataclass(frozen=True)
class ProfitBridge:
    start_profit: Decimal
    revenue_effect: Decimal
    cogs_effect: Decimal
    opex_effect: Decimal
    end_profit: Decimal
    profit_delta: Decimal


def _month_count(start: date, end: date) -> int:
    if start.day != 1 or end.day != 1 or end <= start:
        raise ValueError("period bounds must be ascending first days of calendar months")
    return (end.year - start.year) * 12 + end.month - start.month


def period_metrics(
    conn: psycopg.Connection,
    start: date,
    end: date,
    dataset_id: str = DATASET_ID,
) -> MetricSnapshot:
    """Use coverage before treating missing lines as a verified zero."""
    required_months = _month_count(start, end)
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT bucket, COUNT(*) FILTER (WHERE coverage_status = 'complete') "
            "FROM demo_finance.period_coverage "
            "WHERE dataset_id = %s AND month_start >= %s AND month_start < %s "
            "GROUP BY bucket",
            (dataset_id, start, end),
        )
        complete = {bucket: count for bucket, count in cursor.fetchall()}
        cursor.execute(
            "SELECT l.bucket, SUM(l.amount_toman) "
            "FROM demo_finance.line l "
            "JOIN demo_finance.document d ON d.document_id = l.document_id "
            "WHERE d.dataset_id = %s AND d.status = 'posted' "
            "AND (d.posted_at AT TIME ZONE 'Asia/Tehran')::date >= %s "
            "AND (d.posted_at AT TIME ZONE 'Asia/Tehran')::date < %s "
            "GROUP BY l.bucket",
            (dataset_id, start, end),
        )
        totals = {bucket: amount for bucket, amount in cursor.fetchall()}

    amounts: dict[str, Decimal | None] = {
        bucket: totals.get(bucket, ZERO) if complete.get(bucket) == required_months else None
        for bucket in BUCKETS
    }
    revenue, cogs, opex = (amounts[bucket] for bucket in BUCKETS)
    missing = tuple(bucket for bucket in BUCKETS if amounts[bucket] is None)
    profit = revenue - cogs - opex if not missing else None
    margin = profit / revenue if profit is not None and revenue != ZERO else None
    reason = "incomplete_coverage" if missing else "zero_denominator" if revenue == ZERO else None
    return MetricSnapshot(dataset_id, start, end, revenue, cogs, opex, profit, margin,
                          reason, missing)


def month_metrics(conn: psycopg.Connection, year: int, month: int,
                  dataset_id: str = DATASET_ID) -> MetricSnapshot:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return period_metrics(conn, start, end, dataset_id)


def quarter_metrics(conn: psycopg.Connection, year: int, quarter: int,
                    dataset_id: str = DATASET_ID) -> MetricSnapshot:
    if quarter not in (1, 2, 3, 4):
        raise ValueError("quarter must be 1 through 4")
    start_month = (quarter - 1) * 3 + 1
    start = date(year, start_month, 1)
    end = date(year + 1, 1, 1) if quarter == 4 else date(year, start_month + 3, 1)
    return period_metrics(conn, start, end, dataset_id)


def profit_bridge(previous: MetricSnapshot, current: MetricSnapshot) -> ProfitBridge:
    if previous.dataset_id != current.dataset_id or previous.end != current.start:
        raise ValueError("bridge periods must be consecutive and use the same dataset")
    if previous.missing_buckets or current.missing_buckets:
        raise IncompleteCoverage("cannot bridge incomplete finance periods")
    assert previous.operating_profit is not None and current.operating_profit is not None
    assert previous.revenue is not None and current.revenue is not None
    assert previous.cogs is not None and current.cogs is not None
    assert previous.opex is not None and current.opex is not None
    revenue_effect = current.revenue - previous.revenue
    cogs_effect = -(current.cogs - previous.cogs)
    opex_effect = -(current.opex - previous.opex)
    delta = revenue_effect + cogs_effect + opex_effect
    if previous.operating_profit + delta != current.operating_profit:
        raise ArithmeticError("profit bridge does not reconcile")
    return ProfitBridge(previous.operating_profit, revenue_effect, cogs_effect,
                        opex_effect, current.operating_profit, delta)


def detail_rows(
    conn: psycopg.Connection,
    start: date,
    end: date,
    bucket: str,
    *,
    category_id: str | None = None,
    cost_center_id: str | None = None,
    dataset_id: str = DATASET_ID,
) -> list[dict[str, object]]:
    """Return traceable posted lines for one bucket; never label a filtered sum as profit."""
    if bucket not in BUCKETS:
        raise ValueError("unsupported finance bucket")
    snapshot = period_metrics(conn, start, end, dataset_id)
    if bucket in snapshot.missing_buckets:
        raise IncompleteCoverage(f"{bucket} coverage is incomplete")
    with conn.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "SELECT l.line_id, l.document_id, d.kind, l.source_line_id, l.bucket, "
            "l.category_id, l.cost_center_id, l.item_key, l.quantity_delta, "
            "l.amount_toman, (d.posted_at AT TIME ZONE 'Asia/Tehran')::date AS posted_local_date "
            "FROM demo_finance.line l JOIN demo_finance.document d USING (document_id) "
            "WHERE d.dataset_id = %s AND d.status = 'posted' AND l.bucket = %s "
            "AND (d.posted_at AT TIME ZONE 'Asia/Tehran')::date >= %s "
            "AND (d.posted_at AT TIME ZONE 'Asia/Tehran')::date < %s "
            "AND (%s::text IS NULL OR l.category_id = %s) "
            "AND (%s::text IS NULL OR l.cost_center_id = %s) "
            "ORDER BY d.posted_at, l.document_id, l.line_no",
            (dataset_id, bucket, start, end, category_id, category_id,
             cost_center_id, cost_center_id),
        )
        return [dict(row) for row in cursor.fetchall()]


def expense_breakdown(conn: psycopg.Connection, start: date, end: date,
                      dataset_id: str = DATASET_ID) -> list[dict[str, object]]:
    """OPEX category/center totals; includes every signed detail row."""
    rows = detail_rows(conn, start, end, "OPEX", dataset_id=dataset_id)
    totals: dict[tuple[str, str], Decimal] = {}
    for row in rows:
        key = (str(row["category_id"]), str(row["cost_center_id"]))
        totals[key] = totals.get(key, ZERO) + row["amount_toman"]
    return [
        {"category_id": category, "cost_center_id": center, "amount_toman": amount}
        for (category, center), amount in sorted(totals.items())
    ]


def shipping_counterfactual(conn: psycopg.Connection, start: date, end: date,
                            reduction_toman: Decimal,
                            dataset_id: str = DATASET_ID) -> dict[str, Decimal]:
    """Model a separate result without changing observed finance lines."""
    snapshot = period_metrics(conn, start, end, dataset_id)
    if snapshot.missing_buckets:
        raise IncompleteCoverage("cannot model incomplete finance periods")
    shipping = sum(
        (row["amount_toman"] for row in detail_rows(
            conn, start, end, "OPEX", category_id="shipping", dataset_id=dataset_id
        )),
        ZERO,
    )
    if reduction_toman < ZERO or reduction_toman > shipping:
        raise ValueError("shipping reduction must be between zero and observed shipping cost")
    assert snapshot.operating_profit is not None
    return {
        "observed_profit": snapshot.operating_profit,
        "assumed_shipping_reduction": reduction_toman,
        "modeled_profit": snapshot.operating_profit + reduction_toman,
    }
