"""Independent contract checks for misleading, unbound, or malformed model output."""

from copy import deepcopy
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.demo_finance.dashboard_schema import (
    ChartSpec,
    DashboardSpec,
    DataPlan,
    SpecViolation,
    validate_chart,
    validate_dashboard,
)


def dataset(kind="time_series"):
    return {
        "id": "monthly",
        "kind": kind,
        "coverage": "complete",
        "fields": [
            {"key": "label", "role": "dimension"},
            {"key": "period", "role": "dimension"},
            *[
                {"key": key, "role": "measure", "unit": "تومان", "metric": key}
                for key in ("revenue", "operating_profit", "payroll", "shipping", "admin")
            ],
            {"key": "shipping_share", "role": "measure", "unit": "درصد", "metric": "shipping_share"},
        ],
        "rows": [
            {"label": "آوریل", "period": "2026-04", "revenue": 38,
             "operating_profit": 7, "payroll": 3, "shipping": 1, "admin": 1,
             "shipping_share": 20},
            {"label": "مه", "period": "2026-05", "revenue": 40,
             "operating_profit": 6, "payroll": 3, "shipping": 2, "admin": 1,
             "shipping_share": Decimal("33.333333")},
            {"label": "ژوئن", "period": "2026-06", "revenue": 42,
             "operating_profit": 5, "payroll": 4, "shipping": 2, "admin": 1,
             "shipping_share": Decimal("28.571429")},
        ],
    }


def chart(kind="line", *series):
    return ChartSpec.model_validate({
        "id": "chart", "type": kind, "title": "نمای داده",
        "dataset_id": "monthly", "x": "label",
        "series": [{"field": field} for field in (series or ("revenue",))],
    })


FACTS = [
    {"id": "revenue_current", "value": "135000000000", "display": "۱۳۵ میلیارد تومان",
     "metric": "revenue", "period": "q3", "comparison": None},
    {"id": "revenue_change", "value": "15000000000", "display": "۱۵ میلیارد تومان",
     "metric": "revenue", "period": "q3", "comparison": "q2", "favorable": True},
]


def dashboard(**changes):
    payload = {
        "version": "2.0", "title": "گزارش درآمد",
        "answer": "درآمد فصل سوم برابر {{revenue_current}} است.",
        "layout": ["current"],
        "cards": [{"id": "current", "title": "درآمد", "fact_id": "revenue_current"}],
    }
    payload.update(changes)
    return DashboardSpec.model_validate(payload)


@pytest.mark.parametrize("unbound", ["123", "۱۲۳", "١٢٣", "٪", "%", "۱e۳"])
def test_all_common_numeric_scripts_must_use_fact_placeholders(unbound):
    with pytest.raises(SpecViolation, match="عدد") as error:
        validate_dashboard(dashboard(answer="درآمد {{revenue_current}} و " + unbound), [], FACTS)
    assert error.value.code == "unbound_numeric_claim"


def test_fact_substitution_preserves_trusted_backend_display():
    result = validate_dashboard(dashboard(), [], FACTS)
    assert result["answer"] == "درآمد فصل سوم برابر ۱۳۵ میلیارد تومان است."
    assert result["cards"][0]["fact_id"] == "revenue_current"


@pytest.mark.parametrize("claim", ["ده میلیارد تومان", "بیست درصد", "سه برابر"])
def test_numeric_words_cannot_bypass_verified_fact_references(claim):
    with pytest.raises(SpecViolation) as error:
        validate_dashboard(dashboard(answer="درآمد {{revenue_current}} و " + claim + " گزارش شد."), [], FACTS)
    assert error.value.code == "unbound_numeric_claim"


@pytest.mark.parametrize("prose", [
    "تغییر ثبت‌شده برابر {{revenue_change}} است.",
    "در بازهٔ ثبت‌شده برابر {{revenue_current}} گزارش شد.",
    "داده برابر {{revenue_current}} است.",
])
def test_number_word_guard_does_not_match_suffix_of_persian_words(prose):
    result = validate_dashboard(dashboard(answer=prose), [], FACTS)
    assert "{{" not in result["answer"]


@pytest.mark.parametrize("fragment", ["{{missing}}", "{{revenue_current", "revenue_current}}"])
def test_unknown_and_unclosed_fact_references_are_rejected(fragment):
    with pytest.raises(SpecViolation):
        validate_dashboard(dashboard(answer=f"درآمد برابر {fragment} است."), [], FACTS)


@pytest.mark.parametrize("fragment", ["<script>alert('x')</script>", "javascript:alert('x')", "SELECT secret", "```js"])
def test_model_text_cannot_smuggle_executable_content(fragment):
    with pytest.raises(SpecViolation) as error:
        validate_dashboard(dashboard(answer="مقدار {{revenue_current}} " + fragment), [], FACTS)
    assert error.value.code == "invalid_spec"


def test_comparison_fact_cannot_be_declared_but_not_observed():
    insight = {
        "id": "finding", "title": "تغییر درآمد", "kind": "positive", "priority": 1,
        "text": "درآمد برابر {{revenue_current}} است.",
        "fact_ids": ["revenue_current", "revenue_change"],
        "baseline": "مقایسه با فصل دوم", "scope": "دادهٔ نمایشی ثبت‌شده",
    }
    with pytest.raises(SpecViolation):
        validate_dashboard(dashboard(layout=["current", "finding"], insights=[insight]), [], FACTS)


def test_causal_claim_in_summary_is_rejected_too():
    with pytest.raises(SpecViolation) as error:
        validate_dashboard(dashboard(answer="درآمد {{revenue_current}} علت قطعی کاهش سود است."), [], FACTS)
    assert error.value.code == "unsupported_claim"


def test_explicit_causal_limitation_is_allowed():
    value = "درآمد {{revenue_current}} است. این داده علت قطعی افت سود را مشخص نمی‌کند."
    result = validate_dashboard(dashboard(answer=value), [], FACTS)
    assert "مشخص نمی‌کند" in result["answer"]


def test_positive_change_cannot_be_reported_as_a_negative_finding():
    insight = {
        "id": "finding", "title": "افزایش درآمد", "kind": "negative", "priority": 1,
        "text": "تغییر درآمد برابر {{revenue_change}} است.",
        "fact_ids": ["revenue_change"], "baseline": "مقایسه با فصل دوم",
        "scope": "دادهٔ نمایشی ثبت‌شده",
    }
    with pytest.raises(SpecViolation):
        validate_dashboard(dashboard(layout=["current", "finding"], insights=[insight]), [], FACTS)


def test_temporal_chart_requires_distinct_periods_not_just_three_rows():
    source = dataset()
    for row in source["rows"]:
        row["period"] = "2026-04"
    with pytest.raises(SpecViolation):
        validate_chart(chart(), source)


def test_additive_area_rejects_negative_component():
    source = dataset()
    source["rows"][0]["shipping"] = -1
    with pytest.raises(SpecViolation):
        validate_chart(chart("area", "payroll", "shipping", "admin"), source)


def test_distinct_units_need_distinct_composed_axes():
    value = chart("composed", "shipping", "shipping_share")
    with pytest.raises(SpecViolation):
        validate_chart(value, dataset())
    value.series[1].axis = "right"
    validate_chart(value, dataset())


def test_additive_stack_excludes_total_and_its_own_parts():
    with pytest.raises(SpecViolation):
        validate_chart(chart("stacked_bar", "revenue", "payroll", "shipping"), dataset())


@pytest.mark.parametrize("kind", ["pie", "donut", "radial"])
def test_verified_part_whole_total_must_reconcile_exactly(kind):
    source = dataset("breakdown")
    source["total"] = 999
    with pytest.raises(SpecViolation):
        validate_chart(chart(kind, "shipping"), source)
    source["total"] = 5
    validate_chart(chart(kind, "shipping"), source)
    source["rows"][0]["shipping"] = -1
    source["total"] = 3
    with pytest.raises(SpecViolation):
        validate_chart(chart(kind, "shipping"), source)


def test_bridge_does_not_accept_arbitrary_row_roles_with_matching_sum():
    source = {
        "id": "bridge", "kind": "bridge", "coverage": "complete",
        "fields": [{"key": "label", "role": "dimension"},
                   {"key": "value", "role": "measure", "unit": "تومان"}],
        "rows": [{"label": "ابتدا", "role": "start", "value": 18},
                 {"label": "تغییر", "role": "end", "value": -8},
                 {"label": "انتها", "role": "end", "value": 10}],
    }
    with pytest.raises(SpecViolation):
        validate_chart(chart("waterfall", "value"), source)


def test_model_never_adds_raw_renderer_options_or_free_sql():
    value = chart().model_dump()
    value["option"] = {"tooltip": {"formatter": "alert(document.cookie)"}}
    with pytest.raises(ValidationError):
        ChartSpec.model_validate(value)
    with pytest.raises(ValidationError):
        DataPlan.model_validate({"scope": "finance", "queries": [
            {"id": "unsafe", "metrics": ["revenue"], "periods": ["q3"],
             "sql": "SELECT * FROM unrelated"},
        ]})


def test_missing_value_cannot_become_zero_card():
    facts = deepcopy(FACTS)
    facts[0]["value"] = None
    with pytest.raises(SpecViolation):
        validate_dashboard(dashboard(), [], facts)
