from wsr_evolution.domain.models import OperationalCallUnit
from wsr_evolution.domain.ports import Scalar, TraceNodeReading


def _text(fields: dict[str, Scalar], name: str) -> str | None:
    value = fields.get(name)
    return value if isinstance(value, str) and value else None


def _nonnegative_integer(fields: dict[str, Scalar], name: str) -> int | None:
    value = fields.get(name)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def normalize_model_calls(
    nodes: tuple[TraceNodeReading, ...]
) -> tuple[OperationalCallUnit, ...]:
    calls = []
    for node in nodes:
        fields = node.field_map
        provider = _text(fields, "gen_ai.provider.name")
        model = _text(fields, "C57")
        if provider is None and model is None:
            continue
        duration = (
            node.end_time_unix_nano - node.start_time_unix_nano
            if node.availability == "AVAILABLE"
            and node.expiry == "ACTIVE"
            and node.end_time_unix_nano >= node.start_time_unix_nano
            else None
        )
        calls.append(
            OperationalCallUnit(
                call_identity=f"{node.trace_id}/{node.span_id}",
                provider=provider,
                model=model,
                role=_text(fields, "C30"),
                runtime=_text(fields, "C06"),
                duration_ns=duration,
                input_tokens=_nonnegative_integer(fields, "gen_ai.usage.input_tokens"),
                output_tokens=_nonnegative_integer(fields, "gen_ai.usage.output_tokens"),
                provenance_refs=(node.resource_id,),
            )
        )
    return tuple(sorted(calls, key=lambda item: item.call_identity.encode()))
