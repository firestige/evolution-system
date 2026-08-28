from dataclasses import dataclass
from typing import Protocol

from wsr_evolution.api.models import MetricResult
from wsr_evolution.domain.models import NormalizedMetricInput


class Calculator(Protocol):
    coordinate: str

    def calculate(self, normalized: NormalizedMetricInput) -> MetricResult: ...


@dataclass(frozen=True, slots=True)
class CalculatorSlot:
    coordinate: str
    module: str
