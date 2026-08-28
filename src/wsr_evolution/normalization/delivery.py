from wsr_evolution.domain.models import DeliveryMetricUnit
from wsr_evolution.domain.ports import FactReading


def normalize_delivery(
    delivery_id: str, facts: tuple[FactReading, ...]
) -> DeliveryMetricUnit:
    summaries = tuple(
        fact
        for fact in facts
        if fact.kind == "EVENT_CONTRIBUTION"
        and fact.event_name == "delivery.summary"
        and fact.availability == "AVAILABLE"
        and fact.expiry == "ACTIVE"
    )
    outcomes = {
        value
        for fact in summaries
        if isinstance((value := fact.field_map.get("C10")), str) and value
    }
    if len(outcomes) > 1:
        raise ValueError("conflicting terminal outcome facts")
    elapsed_values = {
        value
        for fact in summaries
        if isinstance((value := fact.field_map.get("C55")), int)
        and not isinstance(value, bool)
        and value >= 0
    }
    if len(elapsed_values) > 1:
        raise ValueError("conflicting Delivery elapsed-time facts")
    stages = {
        value
        for fact in summaries
        if isinstance((value := fact.field_map.get("C56")), str) and value
    }
    return DeliveryMetricUnit(
        delivery_id=delivery_id,
        terminal_outcome=next(iter(outcomes), None),
        elapsed_time_ms=next(iter(elapsed_values), None),
        reached_stages=tuple(sorted(stages, key=str.encode)),
        provenance_refs=tuple(
            sorted({fact.accepted_digest for fact in summaries}, key=str.encode)
        ),
    )
