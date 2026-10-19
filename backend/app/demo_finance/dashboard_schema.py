"""Closed dashboard contracts and semantic validation; no renderer options or code."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Metric = Literal["revenue", "cogs", "opex", "operating_profit", "shipping", "payroll", "admin"]
Period = Literal["q2", "q3", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]
ChartType = Literal["area", "line", "bar", "horizontal_bar", "grouped_bar", "stacked_bar",
                    "composed", "pie", "donut", "radial", "waterfall", "radar"]


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DataQuery(ClosedModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    metrics: list[Metric] = Field(min_length=1, max_length=7)
    periods: list[Period] = Field(min_length=1, max_length=8)
    dimension: Literal["period", "category", "cost_center", "bridge", "normalized"] = "period"
    category: Literal["shipping", "payroll", "admin"] | None = None

    @model_validator(mode="after")
    def valid_combination(self):
        if len(set(self.metrics)) != len(self.metrics) or len(set(self.periods)) != len(self.periods):
            raise ValueError("duplicate metric or period")
        if self.category and self.metrics != ["opex"]:
            raise ValueError("category filter requires opex only; shipping is also a standalone metric")
        if self.dimension in {"category", "cost_center"}:
            if self.metrics != ["opex"] or len(self.periods) > 2:
                raise ValueError("expense breakdown requires opex and at most two periods")
            if self.dimension == "category" and self.category:
                raise ValueError("category breakdown cannot also filter category")
        if self.dimension in {"bridge", "normalized"}:
            if self.periods != ["q2", "q3"] or self.category:
                raise ValueError("bridge and normalized comparison require q2 then q3")
        if self.dimension == "bridge" and set(self.metrics) != {"revenue", "cogs", "opex", "operating_profit"}:
            raise ValueError("bridge requires all four accounting metrics")
        if self.dimension == "normalized" and len(self.metrics) < 3:
            raise ValueError("radar normalization requires at least three comparable indices")
        if any(p.startswith("q") for p in self.periods) and any(p.startswith("2026") for p in self.periods):
            raise ValueError("overlapping quarter and month grain forbidden")
        return self


class DataPlan(ClosedModel):
    scope: Literal["finance", "out_of_scope", "unavailable"]
    queries: list[DataQuery] = Field(default_factory=list, max_length=6)
    reason: str = Field(default="", max_length=350)

    @model_validator(mode="after")
    def scope_queries(self):
        if self.scope == "finance" and not self.queries:
            raise ValueError("finance plan needs a data query")
        if len({q.id for q in self.queries}) != len(self.queries):
            raise ValueError("duplicate query id")
        return self


class CardSpec(ClosedModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    title: str = Field(min_length=1, max_length=140)
    fact_id: str = Field(min_length=1, max_length=150)


class SeriesSpec(ClosedModel):
    field: str = Field(min_length=1, max_length=60)
    axis: Literal["left", "right"] = "left"


class ChartSpec(ClosedModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    type: ChartType
    title: str = Field(min_length=1, max_length=160)
    dataset_id: str = Field(min_length=1, max_length=32)
    x: str = "label"
    series: list[SeriesSpec] = Field(min_length=1, max_length=7)
    width: Literal["half", "full"] = "half"


class TableSpec(ClosedModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    title: str = Field(min_length=1, max_length=160)
    dataset_id: str
    columns: list[str] = Field(min_length=1, max_length=8)


class InsightSpec(ClosedModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    title: str = Field(min_length=1, max_length=140)
    text: str = Field(min_length=1, max_length=600)
    kind: Literal["positive", "negative", "neutral"]
    priority: int = Field(ge=1, le=5)
    fact_ids: list[str] = Field(min_length=1, max_length=8)
    baseline: str = Field(min_length=3, max_length=250)
    scope: str = Field(min_length=3, max_length=250)


class DashboardSpec(ClosedModel):
    version: Literal["2.0"]
    title: str = Field(min_length=1, max_length=160)
    answer: str = Field(min_length=5, max_length=900)
    layout: list[str] = Field(min_length=1, max_length=30)
    cards: list[CardSpec] = Field(default_factory=list, max_length=10)
    charts: list[ChartSpec] = Field(default_factory=list, max_length=8)
    tables: list[TableSpec] = Field(default_factory=list, max_length=3)
    insights: list[InsightSpec] = Field(default_factory=list, max_length=8)


class Composition(ClosedModel):
    kind: Literal["dashboard", "data_request"]
    spec: DashboardSpec | None = None
    queries: list[DataQuery] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def one_payload(self):
        if self.kind == "dashboard" and (self.spec is None or self.queries):
            raise ValueError("dashboard requires spec only")
        if self.kind == "data_request" and (self.spec is not None or not self.queries):
            raise ValueError("supplement requires queries only")
        return self


CHART_CATALOG = {
    "line": "Ordered monthly time series, at least three nonmissing points; no long-term claims from two quarters.",
    "area": "Same temporal requirements as line; one metric or additive nonnegative series.",
    "bar": "One numerical series compared across categories or periods.",
    "horizontal_bar": "Category ranking; preferred for long Persian labels. One numerical series.",
    "grouped_bar": "At least two comparable series with one unit, including quarter comparisons.",
    "stacked_bar": "Nonnegative additive expense parts only; no totals alongside their own parts.",
    "composed": "Two related metrics, e.g. revenue/profit or shipping/shipping_share. Different units require explicit right axis.",
    "pie": "One nonnegative additive expense breakdown, positive verified total, two to six categories.",
    "donut": "Same verified part-to-whole restrictions as pie.",
    "radial": "Same verified part-to-whole restrictions as pie; no negative values or arbitrary independent totals.",
    "waterfall": "Only backend reconciled bridge dataset: start + signed deltas = end.",
    "radar": "Only normalized dataset: at least three axes, same base index, no raw mixed-unit metrics.",
}


class SpecViolation(ValueError):
    def __init__(self, code: str, message: str, field: str | None = None, details: dict | None = None):
        self.code = code
        self.field = field
        self.details = details or {}
        super().__init__(message)


PLACEHOLDER = re.compile(r"\{\{([a-zA-Z0-9_:.-]+)\}\}")
UNBOUND_NUMBER = re.compile(r"[0-9۰-۹٠-٩%٪]")
NUMBER_WORD = re.compile(r"(?<![\w\u200c])(?:صفر|یک|دو|سه|چهار|پنج|شش|هفت|هشت|نه|ده|یازده|دوازده|سیزده|چهارده|پانزده|شانزده|هفده|هجده|نوزده|بیست|سی|چهل|پنجاه|شصت|هفتاد|هشتاد|نود|صد|هزار)(?:\s+و\s+(?:یک|دو|سه|چهار|پنج|شش|هفت|هشت|نه))?\s*(?:میلیارد|میلیون|هزار|تومان|درصد|برابر)(?!\w)")


def _text(text: str, facts: dict[str, dict], allowed: set[str] | None = None) -> str:
    refs = set(PLACEHOLDER.findall(text))
    if refs - facts.keys() or (allowed is not None and refs - allowed):
        raise SpecViolation("invalid_reference", "ارجاع متنی مدل در دادهٔ معتبر وجود ندارد.")
    stripped = PLACEHOLDER.sub("", text)
    numeric = re.search(r"[0-9۰-۹٠-٩]+(?:[.,٫٬][0-9۰-۹٠-٩]+)*|[%٪]", stripped) or NUMBER_WORD.search(stripped)
    if numeric or "{{" in stripped or "}}" in stripped:
        raise SpecViolation("unbound_numeric_claim", "عدد یا درصد متن باید به یک مقدار تأییدشده ارجاع دهد.",
                            details={"unbound_token": numeric.group(0)[:24] if numeric else "malformed_placeholder"})
    if re.search(r"<[^>]+>|```|javascript:|\b(?:SELECT|INSERT|DROP|eval)\b", text, re.I):
        raise SpecViolation("invalid_spec", "کد اجرایی در متن داشبورد مجاز نیست.")
    for clause in re.split(r"[.!؟؛\n]", text):
        assertion = re.search(r"(?:علت قطعی|دلیل قطعی|قطعاً ناشی|ثابت می‌کند|باید حتما)", clause)
        negated = re.search(r"(?:نمی[‌ ]?کند|نمی[‌ ]?توان|نیست|اثبات نشده|مشخص نمی)", clause)
        if assertion and not negated:
            raise SpecViolation("unsupported_claim", "علت تجاری قطعی از دادهٔ حسابداری قابل اثبات نیست.")
    return PLACEHOLDER.sub(lambda m: facts[m.group(1)]["display"], text)


def validate_dashboard(spec: DashboardSpec, datasets: list[dict], fact_list: list[dict]) -> dict:
    """Validate references, units, arithmetic claims and analytical chart suitability."""
    facts = {f["id"]: f for f in fact_list}
    data = {d["id"]: d for d in datasets}

    def checked_text(value: str, path: str, allowed: set[str] | None = None) -> str:
        try:
            return _text(value, facts, allowed)
        except SpecViolation as exc:
            exc.field = path
            raise
    components = [*spec.cards, *spec.charts, *spec.tables, *spec.insights]
    ids = [c.id for c in components]
    if len(ids) != len(set(ids)) or len(spec.layout) != len(set(spec.layout)) or set(spec.layout) != set(ids):
        raise SpecViolation("invalid_spec", "چیدمان باید هر جزء معتبر را دقیقاً یک بار ارجاع دهد.", "layout",
                            {"component_ids": ids, "missing_ids": sorted(set(ids) - set(spec.layout)),
                             "unknown_ids": sorted(set(spec.layout) - set(ids)),
                             "duplicate_component_ids": sorted({id for id in ids if ids.count(id) > 1}),
                             "duplicate_layout_ids": sorted({id for id in spec.layout if spec.layout.count(id) > 1})})
    result = spec.model_dump()
    result["title"] = checked_text(spec.title, "title")
    result["answer"] = checked_text(spec.answer, "answer")
    if not PLACEHOLDER.search(spec.answer):
        raise SpecViolation("invalid_reference", "پاسخ باید دست‌کم یک مقدار معتبر داشته باشد.")
    for i, card in enumerate(spec.cards):
        if card.fact_id not in facts or facts[card.fact_id]["value"] is None:
            raise SpecViolation("invalid_reference", "کارت به مقدار ناموجود ارجاع می‌دهد.")
        result["cards"][i]["title"] = checked_text(card.title, f"cards.{i}.title")
    for i, chart in enumerate(spec.charts):
        if chart.dataset_id not in data:
            raise SpecViolation("invalid_reference", "مجموعه‌دادهٔ نمودار موجود نیست.")
        validate_chart(chart, data[chart.dataset_id])
        result["charts"][i]["title"] = checked_text(chart.title, f"charts.{i}.title")
    for i, table in enumerate(spec.tables):
        dataset = data.get(table.dataset_id)
        if dataset is None or not set(table.columns) <= {f["key"] for f in dataset["fields"]}:
            raise SpecViolation("invalid_reference", "ستون جدول در مجموعه‌داده موجود نیست.")
        result["tables"][i]["title"] = checked_text(table.title, f"tables.{i}.title")
    for i, insight in enumerate(spec.insights):
        refs = set(insight.fact_ids)
        if refs - facts.keys() or not refs or any(facts[f]["value"] is None for f in refs):
            raise SpecViolation("invalid_reference", "شواهد بینش موجود یا کامل نیست.")
        bound = set(PLACEHOLDER.findall(insight.text))
        if not bound or not bound <= refs:
            raise SpecViolation("unbound_numeric_claim", "بینش باید مقدار تأییدشده و ارجاع پشتیبان داشته باشد.")
        comparison_refs = {f for f in refs if facts[f].get("comparison")}
        if not comparison_refs or not bound.intersection(comparison_refs):
            raise SpecViolation("invalid_reference", "بینش به مبنای مقایسهٔ تأییدشده نیاز دارد.")
        polarities = {facts[f].get("favorable") for f in bound if facts[f].get("favorable") is not None}
        if ((insight.kind == "positive" and polarities == {False})
                or (insight.kind == "negative" and polarities == {True})):
            raise SpecViolation("unsupported_claim", "جهت مثبت یا منفی بینش با تغییر معتبر سازگار نیست.")
        for field in ("title", "text", "baseline", "scope"):
            result["insights"][i][field] = checked_text(getattr(insight, field), f"insights.{i}.{field}", refs)
    return result


def validate_chart(chart: ChartSpec, dataset: dict) -> None:
    fields = {f["key"]: f for f in dataset["fields"]}
    if chart.x not in fields or fields[chart.x]["role"] != "dimension":
        raise SpecViolation("invalid_chart", "محور دسته‌بندی نمودار معتبر نیست.")
    keys = [s.field for s in chart.series]
    if len(keys) != len(set(keys)) or any(k not in fields or fields[k]["role"] != "measure" for k in keys):
        raise SpecViolation("invalid_chart", "سری نمودار معتبر نیست.")
    rows = dataset["rows"]
    if dataset["coverage"] != "complete" or not rows or any(r.get(k) is None for r in rows for k in keys):
        raise SpecViolation("insufficient_data", "دادهٔ کافی برای این نمودار موجود نیست.")
    units = {fields[k]["unit"] for k in keys}
    if chart.type != "composed" and (len(units) > 1 or any(s.axis != "left" for s in chart.series)):
        raise SpecViolation("invalid_chart", "واحدهای ناسازگار یا محور دوم برای این نمودار مجاز نیست.")
    if chart.type in {"line", "area"}:
        periods = [r["period"] for r in rows]
        if dataset["kind"] != "time_series" or len(rows) < 3 or len(set(periods)) != len(periods) or periods != sorted(periods):
            raise SpecViolation("invalid_chart", "خط و مساحت به حداقل سه ماه مرتب نیاز دارند.")
        if chart.type == "area" and len(keys) > 1 and not _additive(keys):
            raise SpecViolation("invalid_chart", "مساحت چندسری فقط برای اجزای جمع‌شونده مجاز است.")
        if chart.type == "area" and any(r[k] < 0 for r in rows for k in keys):
            raise SpecViolation("invalid_chart", "مساحت برای سری منفی مجاز نیست؛ نمودار خطی مناسب‌تر است.")
    if chart.type in {"bar", "horizontal_bar"} and len(keys) != 1:
        raise SpecViolation("invalid_chart", "ستون ساده فقط یک سری می‌پذیرد.")
    if chart.type == "grouped_bar" and len(keys) < 2:
        raise SpecViolation("invalid_chart", "ستون گروهی به چند سری قابل مقایسه نیاز دارد.")
    if chart.type == "stacked_bar":
        if len(keys) < 2 or not _additive(keys) or any(r[k] < 0 for r in rows for k in keys):
            raise SpecViolation("invalid_chart", "انباشته فقط برای اجزای هزینهٔ غیرمنفی و جمع‌شونده معتبر است.")
    if chart.type in {"pie", "donut", "radial"}:
        total = dataset.get("total")
        if (dataset["kind"] != "breakdown" or len(keys) != 1 or not 2 <= len(rows) <= 6
                or total is None or total <= 0 or any(r[keys[0]] < 0 for r in rows)
                or abs(sum(Decimal(str(r[keys[0]])) for r in rows) - Decimal(str(total))) > Decimal("0.000001")):
            raise SpecViolation("invalid_chart", "سهم از کل به اجزای غیرمنفی و کل معتبر نیاز دارد.")
    if chart.type == "composed":
        metrics = {fields[k].get("metric", k) for k in keys}
        related = [{"revenue", "operating_profit"}, {"shipping", "shipping_share"}, {"opex", "shipping"}]
        if len(keys) != 2 or metrics not in related:
            raise SpecViolation("invalid_chart", "ترکیب متریک‌ها معنای تحلیلی تأییدشده ندارد.")
        axes = {s.axis for s in chart.series}
        if (len(units) > 1 and axes != {"left", "right"}) or (len(units) == 1 and axes != {"left"}):
            raise SpecViolation("invalid_chart", "محور دوم باید واحد متفاوت و صریح داشته باشد.")
    if chart.type == "radar" and (dataset["kind"] != "normalized" or len(rows) < 3 or units != {"شاخص؛ مبنا صد"}):
        raise SpecViolation("invalid_chart", "رادار فقط شاخص‌های نرمال‌شدهٔ هم‌مبنا را می‌پذیرد.")
    if chart.type == "waterfall":
        if dataset["kind"] != "bridge" or keys != ["value"] or len(rows) < 3:
            raise SpecViolation("invalid_chart", "پل تغییر فقط مجموعه‌دادهٔ تطبیق‌یافته را می‌پذیرد.")
        if (rows[0].get("role") != "start" or rows[-1].get("role") != "end"
                or any(r.get("role") != "delta" for r in rows[1:-1])
                or sum(Decimal(str(r["value"])) for r in rows[:-1]) != Decimal(str(rows[-1]["value"]))):
            raise SpecViolation("invalid_chart", "اجزای پل با ابتدا و انتها تطبیق ندارند.")


def _additive(keys: list[str]) -> bool:
    return set(keys) <= {"payroll", "shipping", "admin"}
