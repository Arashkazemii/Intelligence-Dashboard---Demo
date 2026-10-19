"""Lazy, bounded semantic queries; every number originates in approved finance reads."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from .api import PERIODS
from .dashboard_schema import DataQuery, SpecViolation
from .metrics import IncompleteCoverage, detail_rows, period_metrics
from .seed import DATASET_ID

BILLION = Decimal(1_000_000_000)
LABELS = {"revenue": "درآمد", "cogs": "بهای کالای فروش‌رفته", "opex": "هزینهٔ عملیاتی",
          "operating_profit": "سود عملیاتی", "shipping": "هزینهٔ حمل", "payroll": "حقوق", "admin": "هزینهٔ اداری"}
BUCKETS = {"revenue": "REVENUE", "cogs": "COGS", "opex": "OPEX"}
CENTER_LABELS = {"sales": "فروش", "operations": "عملیات", "hq": "ستاد"}
MONEY = "میلیارد تومان"
MONTHS = {"2026-04": "آوریل", "2026-05": "مه", "2026-06": "ژوئن", "2026-07": "ژوئیه", "2026-08": "اوت", "2026-09": "سپتامبر"}
PERIOD_LABELS = {"q2": "فصل دوم", "q3": "فصل سوم", **MONTHS}
DEFINITIONS = {"revenue": "جمع خالص سطرهای درآمد ثبت‌شده، شامل برگشت و اصلاحات در تاریخ ثبت",
               "cogs": "جمع خالص بهای کالا در سطرهای ثبت‌شده",
               "opex": "جمع خالص هزینهٔ عملیاتی در سطرهای ثبت‌شده",
               "operating_profit": "درآمد منهای بهای کالا منهای هزینهٔ عملیاتی؛ فقط با پوشش کامل",
               **{k: f"جمع سطرهای هزینهٔ عملیاتی با دستهٔ {LABELS[k]}" for k in ("shipping", "payroll", "admin")}}


def number(value: Decimal | None, scale: Decimal = BILLION) -> float | None:
    return float(value / scale) if value is not None else None


def display(value: float | None, unit: str) -> str:
    if value is None:
        return "دادهٔ ناموجود"
    # Rounding is presentation only; exact source arithmetic stays in Decimal/raw_value.
    rendered = f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"{rendered} {unit}"


class DataBuilder:
    def __init__(self, conn):
        self.conn = conn
        self.snapshots = {}
        self.details = {}
        self.datasets: list[dict] = []
        self.facts: list[dict] = []
        self.query_ids: set[str] = set()
        with conn.cursor() as cursor:
            cursor.execute("SELECT version FROM demo_finance.dataset WHERE dataset_id=%s AND synthetic=true", (DATASET_ID,))
            found = cursor.fetchone()
        if not found:
            raise SpecViolation("insufficient_data", "دادهٔ مالی نمایشی نصب نشده است.")
        self.version = found[0]

    def rows(self, period: str, bucket: str) -> list[dict] | None:
        key = (period, bucket)
        if key not in self.details:
            try:
                self.details[key] = detail_rows(self.conn, *PERIODS[period], bucket)
            except IncompleteCoverage:
                self.details[key] = None
        return self.details[key]

    def metric(self, period: str, metric: str, category: str | None = None) -> tuple[Decimal | None, list[str], list[dict]]:
        if period not in self.snapshots:
            self.snapshots[period] = period_metrics(self.conn, *PERIODS[period])
        snapshot = self.snapshots[period]
        buckets = list(BUCKETS.values()) if metric == "operating_profit" else [BUCKETS.get(metric, "OPEX")]
        sources: list[str] = []
        links: list[dict] = []
        all_rows = []
        for bucket in buckets:
            rows = self.rows(period, bucket)
            if rows is None:
                return None, [], []
            if metric in {"shipping", "payroll", "admin"} or category:
                rows = [r for r in rows if r["category_id"] == (category or metric)]
            all_rows.extend(rows)
            sources.extend(str(r["line_id"]) for r in rows)
            links.append({"period": period, "bucket": bucket, "category_id": category or (metric if metric in {"shipping", "payroll", "admin"} else None)})
        if metric in {"shipping", "payroll", "admin"} or category:
            amount = sum((Decimal(str(r["amount_toman"])) for r in all_rows), Decimal(0))
        else:
            amount = getattr(snapshot, metric)
        return amount, sorted(set(sources)), links

    def add_fact(self, id: str, label: str, value: Decimal | None, period: str, metric: str,
                 sources: list[str], drilldowns: list[dict], *, unit: str = MONEY,
                 scale: Decimal = BILLION, formula: str | None = None,
                 comparison: str | None = None, favorable: bool | None = None) -> str:
        amount = number(value, scale)
        self.facts.append({"id": id, "label": label, "value": amount,
                           "display": display(amount, unit), "raw_value": str(value) if value is not None else None,
                           "unit": unit, "period": period, "metric": metric,
                           "definition": DEFINITIONS.get(metric, formula or label),
                           "source_ids": sources, "drilldowns": drilldowns,
                           "formula": formula, "comparison": comparison, "favorable": favorable})
        return id

    def add(self, queries: list[DataQuery]) -> None:
        if len(self.query_ids) + len(queries) > 8:
            raise SpecViolation("data_limit", "تعداد درخواست‌های داده بیش از حد مجاز است.")
        for query in queries:
            if query.id in self.query_ids:
                raise SpecViolation("invalid_reference", "شناسهٔ درخواست تکمیلی باید تازه باشد.")
            self.query_ids.add(query.id)
            if query.dimension in {"category", "cost_center"}:
                dataset = self.breakdown(query)
            elif query.dimension == "bridge":
                dataset = self.bridge(query)
            elif query.dimension == "normalized":
                dataset = self.normalized(query)
            else:
                dataset = self.series(query)
            self.datasets.append(dataset)
        if sum(len(d["rows"]) for d in self.datasets) > 100 or len(self.facts) > 250:
            raise SpecViolation("data_limit", "حجم دادهٔ لازم بیش از سقف این درخواست است.")

    @staticmethod
    def dataset(query: DataQuery, title: str, kind: str, fields: list[dict], rows: list[dict], **extra) -> dict:
        missing = any(r.get(f["key"]) is None for r in rows for f in fields if f["role"] == "measure")
        return {"id": query.id, "title": title, "kind": kind, "fields": fields,
                "rows": rows, "periods": query.periods, "coverage": "missing" if missing else "complete",
                "limitations": (["پوشش ناقص است؛ مقدار ناموجود صفر نیست."] if missing else []), **extra}

    @staticmethod
    def field(key: str, label: str, unit: str = MONEY, metric: str | None = None) -> dict:
        return {"key": key, "label": label, "role": "measure", "unit": unit, "metric": metric or key}

    def series(self, query: DataQuery) -> dict:
        periods = sorted(query.periods)
        rows = []
        amounts = {}
        for period in periods:
            row = {"id": f"{query.id}:{period}", "label": PERIOD_LABELS[period], "period": period, "source_ids": [], "drilldowns": []}
            for metric in query.metrics:
                value, sources, links = self.metric(period, metric, query.category)
                row[metric] = number(value)
                row["source_ids"] += sources
                row["drilldowns"] += links
                amounts[(period, metric)] = (value, sources, links)
                self.add_fact(f"{query.id}:{period}:{metric}", (LABELS.get(query.category) or LABELS[metric]) + "؛ " + PERIOD_LABELS[period],
                              value, period, query.category or metric, sources, links,
                              formula="revenue - cogs - opex" if metric == "operating_profit" else None)
            if {"shipping", "opex"} <= set(query.metrics):
                shipping, source, links = amounts[(period, "shipping")]
                opex, op_source, op_links = amounts[(period, "opex")]
                share = shipping / opex * 100 if shipping is not None and opex is not None and opex > 0 else None
                row["shipping_share"] = number(share, Decimal(1))
                self.add_fact(f"{query.id}:{period}:shipping_share", "سهم حمل از هزینهٔ عملیاتی؛ " + PERIOD_LABELS[period], share,
                              period, "shipping_share", sorted(set(source + op_source)), links + op_links,
                              unit="درصد", scale=Decimal(1), formula="shipping / opex * 100", comparison="هزینهٔ عملیاتی همان دوره")
            row["source_ids"] = sorted(set(row["source_ids"]))
            rows.append(row)
        if len(periods) >= 2:
            for metric in query.metrics:
                first, sources_a, links_a = amounts[(periods[0], metric)]
                last, sources_b, links_b = amounts[(periods[-1], metric)]
                change = last - first if last is not None and first is not None else None
                pct = change / first * 100 if change is not None and first is not None and first > 0 else None
                sources, links = sorted(set(sources_a + sources_b)), links_a + links_b
                baseline = f"{PERIOD_LABELS[periods[-1]]} نسبت به {PERIOD_LABELS[periods[0]]}"
                favorable = (change > 0 if metric in {"revenue", "operating_profit"} else change < 0) if change is not None and change else None
                semantic_metric = query.category or metric
                self.add_fact(f"{query.id}:change:{metric}", "تغییر " + LABELS[semantic_metric], change, ":".join((periods[0], periods[-1])), semantic_metric,
                              sources, links, formula="last - first", comparison=baseline, favorable=favorable)
                self.add_fact(f"{query.id}:change_pct:{metric}", "درصد تغییر " + LABELS[semantic_metric], pct, ":".join((periods[0], periods[-1])), semantic_metric,
                              sources, links, unit="درصد", scale=Decimal(1), formula="(last - first) / first * 100; first > 0",
                              comparison=baseline, favorable=favorable)
        fields = [{"key": "label", "label": "دوره", "role": "dimension", "unit": ""},
                  *[self.field(m, LABELS.get(query.category) or LABELS[m], metric=query.category or m) for m in query.metrics]]
        if {"shipping", "opex"} <= set(query.metrics):
            fields.append(self.field("shipping_share", "سهم حمل از هزینهٔ عملیاتی", "درصد"))
        return self.dataset(query, "مقایسهٔ دوره‌ای" if periods[0].startswith("q") else "مقادیر ماهانه", "comparison" if periods[0].startswith("q") else "time_series", fields, rows)

    def breakdown(self, query: DataQuery) -> dict:
        groups = defaultdict(dict)
        missing = False
        for period in query.periods:
            rows = self.rows(period, "OPEX")
            if rows is None:
                missing = True
                continue
            for row in rows:
                if query.category and row["category_id"] != query.category:
                    continue
                key = str(row["category_id"] if query.dimension == "category" else row["cost_center_id"])
                groups[key].setdefault(period, []).append(row)
        result_rows = []
        series_keys = ["value"] if len(query.periods) == 1 else query.periods
        total = Decimal(0)
        for group, grouped in sorted(groups.items()):
            label = LABELS[group] if query.dimension == "category" else CENTER_LABELS.get(group, group)
            row = {"id": f"{query.id}:{group}", "label": label, "period": ":".join(query.periods), "source_ids": [], "drilldowns": []}
            for period, field in zip(query.periods, series_keys):
                lines = grouped.get(period, [])
                amount = sum((Decimal(str(r["amount_toman"])) for r in lines), Decimal(0))
                sources = [str(r["line_id"]) for r in lines]
                link = {"period": period, "bucket": "OPEX", "category_id": group if query.dimension == "category" else query.category,
                        "cost_center_id": group if query.dimension == "cost_center" else None}
                row[field] = None if missing else number(amount)
                row["source_ids"] += sources
                row["drilldowns"].append(link)
                total += amount
                self.add_fact(f"{query.id}:{group}:{period}", label + "؛ " + PERIOD_LABELS[period], None if missing else amount, period, "opex", sources, [link], comparison="اجزای هزینهٔ عملیاتی همان دوره")
            result_rows.append(row)
        fields = [{"key": "label", "label": "دسته" if query.dimension == "category" else "مرکز هزینه", "role": "dimension", "unit": ""},
                  *[self.field(key, "مقدار" if key == "value" else PERIOD_LABELS[key], metric="opex") for key in series_keys]]
        dataset = self.dataset(query, "ترکیب هزینهٔ عملیاتی", "breakdown", fields, result_rows,
                               total=number(total) if len(query.periods) == 1 and not missing else None)
        if missing:
            dataset["coverage"] = "missing"
        return dataset

    def bridge(self, query: DataQuery) -> dict:
        values = {p: {m: self.metric(p, m) for m in query.metrics} for p in query.periods}
        a, b = values["q2"], values["q3"]
        complete = all(x[0] is not None for row in values.values() for x in row.values())
        components = [("start", "سود فصل دوم", "start", a["operating_profit"][0]),
                      ("revenue", "اثر تغییر درآمد", "delta", b["revenue"][0] - a["revenue"][0] if complete else None),
                      ("cogs", "اثر تغییر بهای کالا", "delta", a["cogs"][0] - b["cogs"][0] if complete else None),
                      ("opex", "اثر تغییر هزینهٔ عملیاتی", "delta", a["opex"][0] - b["opex"][0] if complete else None),
                      ("end", "سود فصل سوم", "end", b["operating_profit"][0])]
        if complete and sum(v for _, _, role, v in components if role != "end") != b["operating_profit"][0]:
            raise SpecViolation("invalid_calculation", "پل سود با ابتدا و انتها تطبیق ندارد.")
        rows = []
        all_sources = sorted({s for row in values.values() for _, sources, _ in row.values() for s in sources})
        links = [link for row in values.values() for _, _, refs in row.values() for link in refs]
        for key, label, role, value in components:
            rows.append({"id": f"{query.id}:{key}", "label": label, "period": "q2:q3", "value": number(value), "role": role, "source_ids": all_sources, "drilldowns": links})
            self.add_fact(f"{query.id}:{key}", label, value, "q2:q3", "operating_profit", all_sources, links,
                          formula="start_profit + revenue_effect + cogs_effect + opex_effect = end_profit",
                          comparison="تجزیهٔ حسابداری فصل سوم نسبت به فصل دوم؛ علت تجاری را اثبات نمی‌کند")
        return self.dataset(query, "پل تغییر سود عملیاتی", "bridge", [{"key": "label", "label": "جزء تغییر", "role": "dimension", "unit": ""}, self.field("value", "اثر بر سود", metric="operating_profit")], rows)

    def normalized(self, query: DataQuery) -> dict:
        rows = []
        for metric in query.metrics:
            a, sa, la = self.metric("q2", metric)
            b, sb, lb = self.metric("q3", metric)
            base = Decimal(100) if a is not None and a > 0 else None
            current = b / a * 100 if base is not None and b is not None and b >= 0 else None
            rows.append({"id": f"{query.id}:{metric}", "label": LABELS[metric], "period": "q2:q3", "q2": number(base, Decimal(1)), "q3": number(current, Decimal(1)), "source_ids": sorted(set(sa + sb)), "drilldowns": la + lb})
            self.add_fact(f"{query.id}:{metric}:q3_index", LABELS[metric] + "؛ شاخص فصل سوم", current, "q2:q3", metric, sorted(set(sa + sb)), la + lb,
                          unit="شاخص؛ مبنا صد", scale=Decimal(1), formula="q3 / q2 * 100; q2 > 0", comparison="فصل دوم برابر صد")
        fields = [{"key": "label", "label": "شاخص", "role": "dimension", "unit": ""},
                  self.field("q2", "فصل دوم", "شاخص؛ مبنا صد"), self.field("q3", "فصل سوم", "شاخص؛ مبنا صد")]
        return self.dataset(query, "مقایسهٔ شاخص‌ها؛ مبنای فصل دوم برابر صد", "normalized", fields, rows)
