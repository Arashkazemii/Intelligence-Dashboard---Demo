"""Versioned synthetic fixture. Explicit invocation only; existing rows are never erased."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row

DATASET_ID = "finance-2026-q2-q3-v1"
SEED_VERSION = "1.0.0"
BILLION = 1_000_000_000
TEHRAN = ZoneInfo("Asia/Tehran")
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


@dataclass(frozen=True)
class SeedResult:
    dataset_id: str
    version: str
    sha256: str
    inserted: bool


def _moment(month: int, day: int = 15) -> datetime:
    return datetime(2026, month, day, 12, 0, tzinfo=TEHRAN)


def _normalize(value: object) -> object:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else str(value)
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


def build_seed_payload() -> dict[str, object]:
    """Construct records in stable order. No KPI totals are stored here."""
    dataset = {
        "dataset_id": DATASET_ID,
        "version": SEED_VERSION,
        "company_name_fa": "شرکت نمایشی سپهر",
        "synthetic": True,
        "base_unit": "TOMAN_SYNTHETIC",
    }
    categories = [
        {"category_id": "sales", "bucket": "REVENUE", "name_fa": "فروش"},
        {"category_id": "merchandise", "bucket": "COGS", "name_fa": "بهای کالای فروش‌رفته"},
        {"category_id": "payroll", "bucket": "OPEX", "name_fa": "حقوق"},
        {"category_id": "shipping", "bucket": "OPEX", "name_fa": "حمل"},
        {"category_id": "admin", "bucket": "OPEX", "name_fa": "اداری"},
    ]
    centers = [
        {"cost_center_id": "sales", "name_fa": "فروش"},
        {"cost_center_id": "operations", "name_fa": "عملیات"},
        {"cost_center_id": "hq", "name_fa": "ستاد"},
    ]
    coverage = [
        {
            "dataset_id": DATASET_ID,
            "month_start": date(2026, month, 1),
            "bucket": bucket,
            "coverage_status": "complete",
            "verified_at": datetime(2026, 10, 1, 12, tzinfo=TEHRAN),
        }
        for month in range(4, 10)
        for bucket in ("REVENUE", "COGS", "OPEX")
    ]
    documents: list[dict[str, object]] = []
    lines: list[dict[str, object]] = []

    def document(document_id: str, kind: str, moment: datetime, reason: str | None = None) -> None:
        documents.append(
            {
                "document_id": document_id,
                "dataset_id": DATASET_ID,
                "kind": kind,
                "status": "posted",
                "occurred_at": moment,
                "posted_at": moment,
                "reason_code": reason,
            }
        )

    def line(
        document_id: str,
        number: int,
        bucket: str,
        category: str,
        center: str,
        billions: int,
        item_key: str | None = None,
        quantity: int | None = None,
        unit_billions: int | None = None,
        source: str | None = None,
    ) -> None:
        lines.append(
            {
                "line_id": f"{document_id}:{number}",
                "document_id": document_id,
                "line_no": number,
                "bucket": bucket,
                "category_id": category,
                "cost_center_id": center,
                "amount_toman": billions * BILLION,
                "item_key": item_key,
                "quantity_delta": quantity,
                "unit_amount_toman": unit_billions * BILLION if unit_billions is not None else None,
                "source_line_id": source,
            }
        )

    months = (
        (4, 38, 26, 3, 1, 1),
        (5, 40, 28, 3, 2, 1),
        (6, 42, 30, 4, 2, 1),
        (7, 44, 32, 4, 2, 1),
        (8, 48, 35, 4, 3, 1),
        (9, 42, 34, 4, 4, 1),
    )
    for month, revenue, cogs, payroll, shipping, admin in months:
        sale_id = f"sale-2026-{month:02d}"
        expense_id = f"expense-2026-{month:02d}"
        moment = _moment(month)
        document(sale_id, "SALE", moment)
        if month == 7:
            sale_items = (("JUL-RETURNABLE", 2, 1), ("JUL-OTHER", 42, 31))
        else:
            sale_items = ((f"SALE-2026-{month:02d}", revenue, cogs),)
        for index, (item_key, item_revenue, item_cogs) in enumerate(sale_items):
            line(sale_id, index * 2 + 1, "REVENUE", "sales", "sales", item_revenue,
                 item_key, 1, item_revenue)
            line(sale_id, index * 2 + 2, "COGS", "merchandise", "operations", item_cogs,
                 item_key, 1, item_cogs)

        document(expense_id, "EXPENSE", moment)
        line(expense_id, 1, "OPEX", "payroll", "hq", payroll)
        line(expense_id, 2, "OPEX", "shipping", "operations", shipping)
        line(expense_id, 3, "OPEX", "admin", "hq", admin)

    document("return-2026-08", "RETURN", _moment(8, 20), "CUSTOMER_RETURN")
    line("return-2026-08", 1, "REVENUE", "sales", "sales", -2,
         "JUL-RETURNABLE", -1, 2, "sale-2026-07:1")
    line("return-2026-08", 2, "COGS", "merchandise", "operations", -1,
         "JUL-RETURNABLE", -1, 1, "sale-2026-07:2")

    document("adjustment-2026-09", "ADJUSTMENT", _moment(9, 20), "PRIOR_SALE_CORRECTION")
    line("adjustment-2026-09", 1, "REVENUE", "sales", "sales", 3,
         "SALE-2026-06", source="sale-2026-06:1")
    line("adjustment-2026-09", 2, "COGS", "merchandise", "operations", 1,
         "SALE-2026-06", source="sale-2026-06:2")

    return {
        "dataset": dataset,
        "categories": categories,
        "centers": centers,
        "coverage": coverage,
        "documents": documents,
        "lines": lines,
    }


def _digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(_normalize(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def install_schema(conn: psycopg.Connection) -> None:
    """Install only this module's schema; never remove existing objects or data."""
    with conn.transaction():
        conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))


def _actual_payload(conn: psycopg.Connection) -> dict[str, object]:
    queries = {
        "dataset": (
            "SELECT dataset_id, version, company_name_fa, synthetic, base_unit "
            "FROM demo_finance.dataset WHERE dataset_id = %s",
            (DATASET_ID,),
        ),
        "categories": (
            "SELECT category_id, bucket, name_fa FROM demo_finance.category "
            "WHERE category_id = ANY(%s) ORDER BY category_id",
            (["sales", "merchandise", "payroll", "shipping", "admin"],),
        ),
        "centers": (
            "SELECT cost_center_id, name_fa FROM demo_finance.cost_center "
            "WHERE cost_center_id = ANY(%s) ORDER BY cost_center_id",
            (["sales", "operations", "hq"],),
        ),
        "coverage": (
            "SELECT dataset_id, month_start, bucket, coverage_status, verified_at "
            "FROM demo_finance.period_coverage WHERE dataset_id = %s ORDER BY month_start, bucket",
            (DATASET_ID,),
        ),
        "documents": (
            "SELECT document_id, dataset_id, kind, status, occurred_at, posted_at, reason_code "
            "FROM demo_finance.document WHERE dataset_id = %s ORDER BY document_id",
            (DATASET_ID,),
        ),
        "lines": (
            "SELECT l.line_id, l.document_id, l.line_no, l.bucket, l.category_id, "
            "l.cost_center_id, l.amount_toman, l.item_key, l.quantity_delta, "
            "l.unit_amount_toman, l.source_line_id "
            "FROM demo_finance.line l JOIN demo_finance.document d USING (document_id) "
            "WHERE d.dataset_id = %s ORDER BY l.line_id",
            (DATASET_ID,),
        ),
    }
    result: dict[str, object] = {}
    with conn.cursor(row_factory=dict_row) as cursor:
        for key, (sql, params) in queries.items():
            cursor.execute(sql, params)
            rows = [dict(row) for row in cursor.fetchall()]
            result[key] = rows[0] if key == "dataset" and rows else rows
    return result


def canonical_snapshot(conn: psycopg.Connection) -> str:
    """Stable JSON of this dataset's persisted rows for independent build comparison."""
    return json.dumps(_normalize(_actual_payload(conn)), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def seed(conn: psycopg.Connection) -> SeedResult:
    """Insert the named dataset once; refuse a conflicting or modified existing dataset."""
    payload = build_seed_payload()
    digest = _digest(payload)
    expected = {
        "dataset": payload["dataset"],
        "categories": sorted(payload["categories"], key=lambda row: row["category_id"]),
        "centers": sorted(payload["centers"], key=lambda row: row["cost_center_id"]),
        "coverage": sorted(payload["coverage"], key=lambda row: (row["month_start"], row["bucket"])),
        "documents": sorted(payload["documents"], key=lambda row: row["document_id"]),
        "lines": sorted(payload["lines"], key=lambda row: row["line_id"]),
    }
    expected_json = json.dumps(_normalize(expected), ensure_ascii=False, sort_keys=True,
                               separators=(",", ":"))
    with conn.transaction():
        with conn.cursor() as cursor:
            cursor.execute("SELECT seed_sha256 FROM demo_finance.dataset WHERE dataset_id = %s FOR UPDATE",
                           (DATASET_ID,))
            existing = cursor.fetchone()
            if existing:
                if existing[0].strip() != digest or canonical_snapshot(conn) != expected_json:
                    raise ValueError("Existing demo finance dataset differs; no rows were changed")
                return SeedResult(DATASET_ID, SEED_VERSION, digest, False)

            for row in payload["categories"]:
                cursor.execute(
                    "INSERT INTO demo_finance.category (category_id,bucket,name_fa) "
                    "VALUES (%s,%s,%s) ON CONFLICT (category_id) DO NOTHING",
                    (row["category_id"], row["bucket"], row["name_fa"]),
                )
            for row in payload["centers"]:
                cursor.execute(
                    "INSERT INTO demo_finance.cost_center (cost_center_id,name_fa) "
                    "VALUES (%s,%s) ON CONFLICT (cost_center_id) DO NOTHING",
                    (row["cost_center_id"], row["name_fa"]),
                )
            ds = payload["dataset"]
            cursor.execute(
                "INSERT INTO demo_finance.dataset "
                "(dataset_id,version,company_name_fa,synthetic,base_unit,seed_sha256) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (ds["dataset_id"], ds["version"], ds["company_name_fa"], ds["synthetic"],
                 ds["base_unit"], digest),
            )
            for row in payload["coverage"]:
                cursor.execute(
                    "INSERT INTO demo_finance.period_coverage "
                    "(dataset_id,month_start,bucket,coverage_status,verified_at) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    tuple(row.values()),
                )
            lines_by_document: dict[str, list[dict[str, object]]] = {}
            for row in payload["lines"]:
                lines_by_document.setdefault(row["document_id"], []).append(row)
            for row in payload["documents"]:
                cursor.execute(
                    "INSERT INTO demo_finance.document "
                    "(document_id,dataset_id,kind,status,occurred_at,posted_at,reason_code) "
                    "VALUES (%s,%s,%s,'draft',%s,NULL,%s)",
                    (row["document_id"], row["dataset_id"], row["kind"], row["occurred_at"],
                     row["reason_code"]),
                )
                for item in lines_by_document[row["document_id"]]:
                    cursor.execute(
                        "INSERT INTO demo_finance.line "
                        "(line_id,document_id,line_no,bucket,category_id,cost_center_id,amount_toman,"
                        "item_key,quantity_delta,unit_amount_toman,source_line_id) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        tuple(item.values()),
                    )
                cursor.execute(
                    "UPDATE demo_finance.document SET status='posted', posted_at=%s WHERE document_id=%s",
                    (row["posted_at"], row["document_id"]),
                )

        if canonical_snapshot(conn) != expected_json:
            raise ValueError("Persisted demo finance rows differ from the versioned seed")
    return SeedResult(DATASET_ID, SEED_VERSION, digest, True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Install and seed isolated synthetic finance tables")
    parser.add_argument("--apply", action="store_true", help="Required: explicitly write module tables")
    args = parser.parse_args()
    if not args.apply:
        parser.error("--apply is required; this command never runs during API startup")
    database_url = os.getenv("DATABASE_URL", "")
    with psycopg.connect(database_url, autocommit=True) as conn:
        install_schema(conn)
        print(seed(conn))


if __name__ == "__main__":
    main()
