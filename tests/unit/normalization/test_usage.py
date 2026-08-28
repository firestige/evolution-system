from datetime import UTC, datetime

from wsr_evolution.domain.ports import FactReading
from wsr_evolution.normalization.usage import normalize_reported_usage


def usage(fact_id: str, value: int | float, *, kind: str = "money") -> FactReading:
    return FactReading(
        fact_id=fact_id,
        kind="EVENT_CONTRIBUTION",
        source_identity=f"event:{fact_id}",
        recorded_at=datetime(2026, 8, 28, tzinfo=UTC),
        accepted_digest=fact_id[0] * 64,
        event_name="usage",
        completeness="FINAL",
        availability="AVAILABLE",
        expiry="ACTIVE",
        fields=(
            ("C42", kind),
            ("C43", "USD"),
            ("C44", "provider"),
            ("C45", "invoice"),
            ("C46", value),
        ),
        compatibility=(("C42", kind), ("C43", "USD"), ("C44", "provider"), ("C45", "invoice")),
    )


def test_usage_normalization_preserves_exact_reported_dimensions_and_integer_value() -> None:
    units = normalize_reported_usage("delivery-a", (usage("a-usage", 25.0),))
    assert len(units) == 1
    assert units[0].compatibility == ("money", "USD", "provider", "invoice")
    assert units[0].value == 25
    assert units[0].delivery_id == "delivery-a"


def test_non_integral_usage_is_not_rounded_or_estimated() -> None:
    assert normalize_reported_usage("delivery-a", (usage("a-usage", 25.5),)) == ()
