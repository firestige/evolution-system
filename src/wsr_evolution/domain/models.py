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
