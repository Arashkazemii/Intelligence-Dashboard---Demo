"""PostgreSQL checks against fixed numbers from the reviewed finance design.

The expected values below are literals: none are calculated by the seed builder.
Two explicitly named disposable test databases are required. No database is dropped.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from decimal import Decimal

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from app.demo_finance.metrics import (
    IncompleteCoverage,
    detail_rows,
    expense_breakdown,
    month_metrics,
    period_metrics,
    profit_bridge,
    quarter_metrics,
    shipping_counterfactual,
)
from app.demo_finance.seed import DATASET_ID, canonical_snapshot, install_schema, seed

B = 1_000_000_000
EXPECTED_MONTHS = {
    4: (38, 26, 5, 7),
    5: (40, 28, 6, 6),
    6: (42, 30, 7, 5),
    7: (44, 32, 7, 5),
    8: (46, 34, 8, 4),
    9: (45, 35, 9, 1),
}


def _url(name: str) -> str:
    url = os.getenv(name)
    if not url:
        pytest.fail(f"{name} is required; use a dedicated local PostgreSQL test database")
    info = conninfo_to_dict(url)
    if info.get("dbname") not in ("viradata_finance_test_a", "viradata_finance_test_b"):
        pytest.fail(f"{name} must name a dedicated viradata_finance_test database")
    if info.get("host") not in ("127.0.0.1", "localhost"):
        pytest.fail(f"{name} must point to a local PostgreSQL server")
    return url


@pytest.fixture(scope="session")
def urls() -> tuple[str, str]:
    primary = _url("TEST_DATABASE_URL")
    secondary = _url("TEST_DATABASE_URL_SECONDARY")
    if primary == secondary:
        pytest.fail("two distinct test databases are required for seed stability")
    with psycopg.connect(primary, autocommit=True) as connection:
        install_schema(connection)
        seed(connection)
    return primary, secondary


@pytest.fixture
def conn(urls: tuple[str, str]):
    with psycopg.connect(urls[0]) as connection:
        yield connection
        connection.rollback()


def _amounts(snapshot) -> tuple[Decimal | None, ...]:
    return (snapshot.revenue, snapshot.cogs, snapshot.opex, snapshot.operating_profit)


def _raw_bucket_totals(conn: psycopg.Connection, start: date, end: date) -> dict[str, Decimal]:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT l.bucket, SUM(l.amount_toman) FROM demo_finance.line l "
            "JOIN demo_finance.document d USING (document_id) "
            "WHERE d.dataset_id=%s AND d.status='posted' "
            "AND (d.posted_at AT TIME ZONE 'Asia/Tehran')::date >= %s "
            "AND (d.posted_at AT TIME ZONE 'Asia/Tehran')::date < %s "
            "GROUP BY l.bucket",
            (DATASET_ID, start, end),
        )
        return dict(cursor.fetchall())


def test_seed_is_stable_across_two_postgresql_databases(urls):
    with psycopg.connect(urls[0], autocommit=True) as first:
        before = canonical_snapshot(first)
        second_run = seed(first)
        after = canonical_snapshot(first)
        with first.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM demo_finance.line l "
                "JOIN demo_finance.document d USING (document_id) "
                "WHERE d.dataset_id=%s AND d.status='posted'", (DATASET_ID,)
            )
            assert cursor.fetchone()[0] == 36
            cursor.execute("SELECT version,seed_sha256 FROM demo_finance.dataset WHERE dataset_id=%s",
                           (DATASET_ID,))
            version, digest = cursor.fetchone()
    with psycopg.connect(urls[1], autocommit=True) as second:
        install_schema(second)
        new_run = seed(second)
        other = canonical_snapshot(second)
    assert second_run.inserted is False
    assert new_run.sha256 == second_run.sha256 == digest.strip()
    assert version == "1.0.0"
    assert before == after == other


def test_line_to_month_and_month_to_quarter(conn):
    observed = {}
    for month, expected in EXPECTED_MONTHS.items():
        start = date(2026, month, 1)
        end = date(2026, month + 1, 1)
        snapshot = month_metrics(conn, 2026, month)
        assert _amounts(snapshot) == tuple(Decimal(number * B) for number in expected)
        raw = _raw_bucket_totals(conn, start, end)
        assert (raw["REVENUE"], raw["COGS"], raw["OPEX"]) == tuple(
            Decimal(number * B) for number in expected[:3]
        )
        observed[month] = snapshot

    q2, q3 = quarter_metrics(conn, 2026, 2), quarter_metrics(conn, 2026, 3)
    assert _amounts(q2) == tuple(Decimal(number * B) for number in (120, 84, 18, 18))
    assert _amounts(q3) == tuple(Decimal(number * B) for number in (135, 101, 24, 10))
    for quarter, months in ((q2, (4, 5, 6)), (q3, (7, 8, 9))):
        assert _amounts(quarter) == tuple(
            sum((getattr(observed[m], field) for m in months), Decimal(0))
            for field in ("revenue", "cogs", "opex", "operating_profit")
        )
    half_year = period_metrics(conn, date(2026, 4, 1), date(2026, 10, 1))
    assert _amounts(half_year) == tuple(Decimal(number * B) for number in (255, 185, 42, 28))
    assert _raw_bucket_totals(conn, half_year.start, half_year.end) == {
        "REVENUE": Decimal(255 * B), "COGS": Decimal(185 * B), "OPEX": Decimal(42 * B)
    }
    assert q2.operating_margin == Decimal("0.15")
    assert abs(q3.operating_margin - Decimal(10) / Decimal(135)) < Decimal("1e-26")


def test_profit_bridge_reconciles_with_expense_drivers(conn):
    q2, q3 = quarter_metrics(conn, 2026, 2), quarter_metrics(conn, 2026, 3)
    bridge = profit_bridge(q2, q3)
    assert (bridge.start_profit, bridge.revenue_effect, bridge.cogs_effect,
            bridge.opex_effect, bridge.end_profit, bridge.profit_delta) == tuple(
                Decimal(n * B) for n in (18, 15, -17, -6, 10, -8)
            )
    before = {row["category_id"]: row["amount_toman"] for row in
              expense_breakdown(conn, q2.start, q2.end)}
    after = {row["category_id"]: row["amount_toman"] for row in
             expense_breakdown(conn, q3.start, q3.end)}
    assert {key: after[key] - before[key] for key in after} == {
        "payroll": Decimal(2 * B), "shipping": Decimal(4 * B), "admin": Decimal(0)
    }
    assert sum(after.values()) - sum(before.values()) == Decimal(6 * B)


def test_return_reverses_july_item_in_august_and_cannot_overreturn(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT l.bucket,l.amount_toman,l.quantity_delta,l.unit_amount_toman,"
            "l.source_line_id,s.amount_toman,s.quantity_delta "
            "FROM demo_finance.line l JOIN demo_finance.line s ON s.line_id=l.source_line_id "
            "WHERE l.document_id='return-2026-08' ORDER BY l.line_no"
        )
        rows = cursor.fetchall()
    assert rows == [
        ("REVENUE", Decimal(-2 * B), Decimal(-1), Decimal(2 * B),
         "sale-2026-07:1", Decimal(2 * B), Decimal(1)),
        ("COGS", Decimal(-1 * B), Decimal(-1), Decimal(1 * B),
         "sale-2026-07:2", Decimal(1 * B), Decimal(1)),
    ]
    assert _amounts(month_metrics(conn, 2026, 7)) == tuple(
        Decimal(n * B) for n in (44, 32, 7, 5)
    )
    assert _amounts(month_metrics(conn, 2026, 8)) == tuple(
        Decimal(n * B) for n in (46, 34, 8, 4)
    )

    with pytest.raises(psycopg.errors.CheckViolation):
        with conn.transaction():
            conn.execute(
                "INSERT INTO demo_finance.document "
                "(document_id,dataset_id,kind,status,occurred_at,reason_code) "
                "VALUES ('test-over-return',%s,'RETURN','draft',%s,'TEST')",
                (DATASET_ID, datetime(2026, 8, 21, tzinfo=timezone.utc)),
            )
            for number, bucket, category, center, amount, unit, source in (
                (1, "REVENUE", "sales", "sales", -2, 2, "sale-2026-07:1"),
                (2, "COGS", "merchandise", "operations", -1, 1, "sale-2026-07:2"),
            ):
                conn.execute(
                    "INSERT INTO demo_finance.line "
                    "(line_id,document_id,line_no,bucket,category_id,cost_center_id,"
                    "amount_toman,item_key,quantity_delta,unit_amount_toman,source_line_id) "
                    "VALUES (%s,'test-over-return',%s,%s,%s,%s,%s,'JUL-RETURNABLE',-1,%s,%s)",
                    (f"test-over-return:{number}", number, bucket, category, center,
                     amount * B, unit * B, source),
                )
            conn.execute(
                "UPDATE demo_finance.document SET status='posted',posted_at=%s "
                "WHERE document_id='test-over-return'",
                (datetime(2026, 8, 21, tzinfo=timezone.utc),),
            )


def test_correction_is_recognized_in_september_not_june(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT l.bucket,l.amount_toman,l.source_line_id,s.bucket "
            "FROM demo_finance.line l JOIN demo_finance.line s ON s.line_id=l.source_line_id "
            "WHERE l.document_id='adjustment-2026-09' ORDER BY l.line_no"
        )
        assert cursor.fetchall() == [
            ("REVENUE", Decimal(3 * B), "sale-2026-06:1", "REVENUE"),
            ("COGS", Decimal(1 * B), "sale-2026-06:2", "COGS"),
        ]
        cursor.execute(
            "SELECT l.bucket,SUM(l.amount_toman) FROM demo_finance.line l "
            "JOIN demo_finance.document d USING (document_id) "
            "WHERE d.status='posted' AND d.kind<>'ADJUSTMENT' "
            "AND (d.posted_at AT TIME ZONE 'Asia/Tehran')::date >= '2026-09-01' "
            "AND (d.posted_at AT TIME ZONE 'Asia/Tehran')::date < '2026-10-01' "
            "GROUP BY l.bucket"
        )
        without_correction = dict(cursor.fetchall())
    assert without_correction == {
        "REVENUE": Decimal(42 * B), "COGS": Decimal(34 * B), "OPEX": Decimal(9 * B)
    }
    assert without_correction["REVENUE"] - without_correction["COGS"] - without_correction["OPEX"] == Decimal(-1 * B)
    assert _amounts(month_metrics(conn, 2026, 6)) == tuple(
        Decimal(n * B) for n in (42, 30, 7, 5)
    )
    assert _amounts(quarter_metrics(conn, 2026, 2)) == tuple(
        Decimal(n * B) for n in (120, 84, 18, 18)
    )
    assert _amounts(month_metrics(conn, 2026, 9)) == tuple(
        Decimal(n * B) for n in (45, 35, 9, 1)
    )


def test_status_pairing_uniqueness_sources_and_posted_immutability(conn):
    when = datetime(2026, 9, 25, tzinfo=timezone.utc)
    conn.execute(
        "INSERT INTO demo_finance.document "
        "(document_id,dataset_id,kind,status,occurred_at) "
        "VALUES ('test-draft-expense',%s,'EXPENSE','draft',%s)", (DATASET_ID, when)
    )
    conn.execute(
        "INSERT INTO demo_finance.line "
        "(line_id,document_id,line_no,bucket,category_id,cost_center_id,amount_toman) "
        "VALUES ('test-draft-expense:1','test-draft-expense',1,'OPEX','admin','hq',%s)",
        (999 * B,),
    )
    assert month_metrics(conn, 2026, 9).opex == Decimal(9 * B)

    with pytest.raises(psycopg.errors.UniqueViolation):
        with conn.transaction():
            conn.execute(
                "INSERT INTO demo_finance.line "
                "(line_id,document_id,line_no,bucket,category_id,cost_center_id,amount_toman) "
                "VALUES ('test-duplicate','test-draft-expense',1,'OPEX','admin','hq',1)"
            )
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with conn.transaction():
            conn.execute(
                "INSERT INTO demo_finance.line "
                "(line_id,document_id,line_no,bucket,category_id,cost_center_id,amount_toman) "
                "VALUES ('test-wrong-category','test-draft-expense',2,'OPEX','sales','hq',1)"
            )
    with pytest.raises(psycopg.errors.CheckViolation):
        with conn.transaction():
            conn.execute(
                "UPDATE demo_finance.line SET amount_toman=1 WHERE line_id='sale-2026-04:1'"
            )
    with pytest.raises(psycopg.errors.CheckViolation):
        with conn.transaction():
            conn.execute(
                "UPDATE demo_finance.document SET reason_code='MUTATED' "
                "WHERE document_id='sale-2026-04'"
            )

    conn.execute(
        "INSERT INTO demo_finance.document "
        "(document_id,dataset_id,kind,status,occurred_at) "
        "VALUES ('test-unpaired-sale',%s,'SALE','draft',%s)", (DATASET_ID, when)
    )
    conn.execute(
        "INSERT INTO demo_finance.line "
        "(line_id,document_id,line_no,bucket,category_id,cost_center_id,amount_toman,"
        "item_key,quantity_delta,unit_amount_toman) "
        "VALUES ('test-unpaired-sale:1','test-unpaired-sale',1,'REVENUE','sales','sales',"
        "100,'TEST-ITEM',1,100)"
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        with conn.transaction():
            conn.execute(
                "UPDATE demo_finance.document SET status='posted',posted_at=%s "
                "WHERE document_id='test-unpaired-sale'", (when,)
            )

    conn.execute(
        "INSERT INTO demo_finance.document "
        "(document_id,dataset_id,kind,status,occurred_at,reason_code) "
        "VALUES ('test-bad-source',%s,'ADJUSTMENT','draft',%s,'TEST')", (DATASET_ID, when)
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        with conn.transaction():
            conn.execute(
                "INSERT INTO demo_finance.line "
                "(line_id,document_id,line_no,bucket,category_id,cost_center_id,amount_toman,"
                "item_key,source_line_id) "
                "VALUES ('test-bad-source:1','test-bad-source',1,'REVENUE','sales','sales',"
                "1,'SALE-2026-06','sale-2026-06:2')"
            )
    with pytest.raises(psycopg.errors.CheckViolation, match="invalid source finance line"):
        with conn.transaction():
            conn.execute(
                "INSERT INTO demo_finance.line "
                "(line_id,document_id,line_no,bucket,category_id,cost_center_id,amount_toman,"
                "item_key,source_line_id) "
                "VALUES ('test-missing-source:1','test-bad-source',2,'REVENUE','sales','sales',"
                "1,'SALE-2026-06','missing-source-line')"
            )


def test_drilldown_reconciles_categories_centers_and_source_rows(conn):
    periods = [month_metrics(conn, 2026, month) for month in range(4, 10)]
    periods += [quarter_metrics(conn, 2026, 2), quarter_metrics(conn, 2026, 3)]
    for period in periods:
        for bucket, expected in (("REVENUE", period.revenue),
                                 ("COGS", period.cogs), ("OPEX", period.opex)):
            rows = detail_rows(conn, period.start, period.end, bucket)
            assert sum((row["amount_toman"] for row in rows), Decimal(0)) == expected
            assert all(row["line_id"] and row["document_id"] for row in rows)
            for dimension in ("category_id", "cost_center_id"):
                groups = {row[dimension] for row in rows}
                assert sum((sum((row["amount_toman"] for row in rows if row[dimension] == key),
                                Decimal(0)) for key in groups), Decimal(0)) == expected

    q3 = quarter_metrics(conn, 2026, 3)

    by_category = {row["category_id"]: row["amount_toman"] for row in
                   expense_breakdown(conn, q3.start, q3.end)}
    assert by_category == {
        "payroll": Decimal(12 * B), "shipping": Decimal(9 * B), "admin": Decimal(3 * B)
    }
    shipping = detail_rows(conn, q3.start, q3.end, "OPEX", category_id="shipping")
    assert len(shipping) == 3
    assert sum((row["amount_toman"] for row in shipping), Decimal(0)) == Decimal(9 * B)
    assert {row["cost_center_id"] for row in shipping} == {"operations"}


def test_incomplete_coverage_zero_missing_and_tehran_boundary(conn):
    conn.execute(
        "UPDATE demo_finance.period_coverage SET coverage_status='incomplete',verified_at=NULL "
        "WHERE dataset_id=%s AND month_start='2026-08-01' AND bucket='OPEX'", (DATASET_ID,)
    )
    august = month_metrics(conn, 2026, 8)
    assert (august.revenue, august.cogs, august.opex, august.operating_profit,
            august.operating_margin, august.margin_reason) == (
                Decimal(46 * B), Decimal(34 * B), None, None, None, "incomplete_coverage"
            )
    assert quarter_metrics(conn, 2026, 3).operating_profit is None
    with pytest.raises(IncompleteCoverage):
        detail_rows(conn, date(2026, 8, 1), date(2026, 9, 1), "OPEX")
    conn.execute(
        "UPDATE demo_finance.period_coverage SET coverage_status='complete',verified_at=%s "
        "WHERE dataset_id=%s AND month_start='2026-08-01' AND bucket='OPEX'",
        (datetime(2026, 10, 1, tzinfo=timezone.utc), DATASET_ID),
    )
    conn.execute(
        "DELETE FROM demo_finance.period_coverage "
        "WHERE dataset_id=%s AND month_start='2026-09-01' AND bucket='REVENUE'",
        (DATASET_ID,),
    )
    september = month_metrics(conn, 2026, 9)
    assert september.revenue is None and september.operating_profit is None
    assert september.missing_buckets == ("REVENUE",)

    for bucket in ("REVENUE", "COGS", "OPEX"):
        conn.execute(
            "INSERT INTO demo_finance.period_coverage "
            "(dataset_id,month_start,bucket,coverage_status,verified_at) "
            "VALUES (%s,'2026-10-01',%s,'complete',%s)",
            (DATASET_ID, bucket, datetime(2026, 10, 2, tzinfo=timezone.utc)),
        )
    october = month_metrics(conn, 2026, 10)
    assert _amounts(october) == (Decimal(0), Decimal(0), Decimal(0), Decimal(0))
    assert october.operating_margin is None and october.margin_reason == "zero_denominator"
    november = month_metrics(conn, 2026, 11)
    assert _amounts(november) == (None, None, None, None)
    assert november.margin_reason == "incomplete_coverage"

    boundary = datetime(2026, 7, 31, 20, 45, tzinfo=timezone.utc)
    conn.execute(
        "INSERT INTO demo_finance.document "
        "(document_id,dataset_id,kind,status,occurred_at) "
        "VALUES ('test-boundary',%s,'EXPENSE','draft',%s)", (DATASET_ID, boundary)
    )
    conn.execute(
        "INSERT INTO demo_finance.line "
        "(line_id,document_id,line_no,bucket,category_id,cost_center_id,amount_toman) "
        "VALUES ('test-boundary:1','test-boundary',1,'OPEX','admin','hq',%s)", (B,)
    )
    conn.execute(
        "UPDATE demo_finance.document SET status='posted',posted_at=%s "
        "WHERE document_id='test-boundary'", (boundary,)
    )
    assert month_metrics(conn, 2026, 7).opex == Decimal(7 * B)
    assert month_metrics(conn, 2026, 8).opex == Decimal(9 * B)


def test_shipping_what_if_is_separate_from_observed_data(conn):
    q2, q3 = quarter_metrics(conn, 2026, 2), quarter_metrics(conn, 2026, 3)
    before_bridge = profit_bridge(q2, q3)
    modeled = shipping_counterfactual(conn, q3.start, q3.end, Decimal(2 * B))
    assert modeled == {
        "observed_profit": Decimal(10 * B),
        "assumed_shipping_reduction": Decimal(2 * B),
        "modeled_profit": Decimal(12 * B),
    }
    assert quarter_metrics(conn, 2026, 3).operating_profit == Decimal(10 * B)
    assert profit_bridge(quarter_metrics(conn, 2026, 2),
                         quarter_metrics(conn, 2026, 3)) == before_bridge
