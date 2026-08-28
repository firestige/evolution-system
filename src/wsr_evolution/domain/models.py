from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NormalizedValue:
    name: str
    integer: int | None = None
    decimal: str | None = None
    text: str | None = None
    boolean: bool | None = None

    def __post_init__(self) -> None:
        supplied = sum(
            value is not None for value in (self.integer, self.decimal, self.text, self.boolean)
        )
        if supplied != 1:
            raise ValueError("normalized value requires exactly one typed representation")


@dataclass(frozen=True, slots=True)
class NormalizedMetricInput:
    metric_coordinate: str
    unit_identity: str
    values: tuple[NormalizedValue, ...]


@dataclass(frozen=True, slots=True)
class DeliveryMetricUnit:
    delivery_id: str
    terminal_outcome: str | None
    elapsed_time_ms: int | None
    reached_stages: tuple[str, ...]
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.elapsed_time_ms is not None and self.elapsed_time_ms < 0:
            raise ValueError("Delivery elapsed time must be nonnegative")
        if len(set(self.reached_stages)) != len(self.reached_stages):
            raise ValueError("Delivery reached stages must be unique")


@dataclass(frozen=True, slots=True)
class OperationalCallUnit:
    call_identity: str
    provider: str | None
    model: str | None
    role: str | None
    runtime: str | None
    duration_ns: int | None
    input_tokens: int | None
    output_tokens: int | None
    provenance_refs: tuple[str, ...]

    @property
    def cohort(self) -> tuple[str, str, str, str] | None:
        values = (self.provider, self.model, self.role, self.runtime)
        if any(value is None for value in values):
            return None
        provider, model, role, runtime = values
        assert all(value is not None for value in (provider, model, role, runtime))
        assert provider is not None and model is not None
        assert role is not None and runtime is not None
        return (provider, model, role, runtime)
