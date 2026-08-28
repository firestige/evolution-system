from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CalculatorSlot:
    coordinate: str
    module: str
