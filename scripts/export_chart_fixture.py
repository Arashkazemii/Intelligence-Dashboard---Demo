"""Read actual ledger data and export a validated renderer coverage fixture.

This bypasses model composition only for explicit browser renderer tests. It never
changes source data and is not used by the product's question endpoint.
Run within the API container, whose database connection is already configured.
"""

import json

import psycopg

from app.demo_finance.api import _database_url
from app.demo_finance.dashboard_data import DataBuilder
from app.demo_finance.dashboard_schema import DataQuery, DashboardSpec, validate_dashboard


def main():
    periods = [f"2026-{month:02d}" for month in range(4, 10)]
    queries = [
        {"id": "monthly", "metrics": ["revenue", "operating_profit"], "periods": periods},
        {"id": "expenses", "metrics": ["payroll", "shipping", "admin"], "periods": periods},
        {"id": "mix", "metrics": ["opex"], "periods": ["q3"], "dimension": "category"},
        {"id": "bridge", "metrics": ["revenue", "cogs", "opex", "operating_profit"], "periods": ["q2", "q3"], "dimension": "bridge"},
        {"id": "indices", "metrics": ["revenue", "opex", "operating_profit"], "periods": ["q2", "q3"], "dimension": "normalized"},
    ]
    charts = []
    for kind, dataset_id, fields in (
        ("line", "monthly", ["revenue"]),
        ("area", "monthly", ["revenue"]),
        ("bar", "monthly", ["revenue"]),
        ("horizontal_bar", "mix", ["value"]),
        ("grouped_bar", "monthly", ["revenue", "operating_profit"]),
        ("stacked_bar", "expenses", ["payroll", "shipping", "admin"]),
        ("composed", "monthly", ["revenue", "operating_profit"]),
        ("pie", "mix", ["value"]),
        ("donut", "mix", ["value"]),
        ("radial", "mix", ["value"]),
        ("waterfall", "bridge", ["value"]),
        ("radar", "indices", ["q2", "q3"]),
    ):
        charts.append({"id": kind, "type": kind, "title": "بررسی نمودار " + kind,
                       "dataset_id": dataset_id, "x": "label",
                       "series": [{"field": field, "axis": "left"} for field in fields], "width": "half"})
    with psycopg.connect(_database_url(), connect_timeout=3) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        builder = DataBuilder(conn)
        builder.add([DataQuery.model_validate(q) for q in queries])
        pages = []
        for start in (0, 6):
            selected = charts[start:start + 6]
            spec = DashboardSpec.model_validate({
                "version": "2.0", "title": "آزمون پوشش renderer؛ دادهٔ واقعی دیتابیس نمایشی",
                "answer": "درآمد سپتامبر برابر {{monthly:2026-09:revenue}} است. این صفحه فقط برای آزمون renderer است.",
                "layout": [chart["id"] for chart in selected], "charts": selected,
            })
            pages.append({
                "status": "answered", "message": "دادهٔ آزمون renderer",
                "spec": validate_dashboard(spec, builder.datasets, builder.facts),
                "datasets": builder.datasets, "facts": builder.facts,
                "dataset_id": "finance-2026-q2-q3-v1", "dataset_version": builder.version,
                "synthetic": True, "limitations": ["این خروجی fixture آزمون است؛ ترکیب آن را مدل انتخاب نکرده است."],
                "meta": {"model_calls": 0, "supplementary_requests": 0},
            })
        result = {"pages": pages}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
