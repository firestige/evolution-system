from fractions import Fraction

from wsr_evolution.api.models import ExactValue, MetricResult, MetricSlice
from wsr_evolution.domain.models import DeliveryMetricUnit

from .common import coverage, rational, unavailable
from .protocol import CalculatorSlot

SLOT = CalculatorSlot("delivery-cycle-time-ms@2.0.0", __name__)


def calculate(units: tuple[DeliveryMetricUnit, ...]) -> MetricResult:
    terminal = tuple(unit for unit in units if unit.terminal_outcome is not None)
    covered = tuple(unit for unit in terminal if unit.elapsed_time_ms is not None)
    metric_coverage = coverage(len(covered), len(terminal))
    if not covered:
        return unavailable("delivery-cycle-time-ms", metric_coverage=metric_coverage)
    total = sum(unit.elapsed_time_ms for unit in covered if unit.elapsed_time_ms is not None)
    average = Fraction(total, len(covered))
    value: int | str = average.numerator if average.denominator == 1 else rational(average)
    missing = tuple(
        sorted(
            f"delivery.elapsed_time_ms:{unit.delivery_id}"
            for unit in terminal
            if unit.elapsed_time_ms is None
        )
    )
    return MetricResult(
        metric_id="delivery-cycle-time-ms",
        metric_version="2.0.0",
        slices=(
            MetricSlice(
                slice_key={},
                state="AVAILABLE",
                value=ExactValue(kind="DURATION_MS", value=value, unit="milliseconds"),
                measures={"sum_ms": total},
                contributing_count=len(covered),
                coverage=metric_coverage,
                missing_inputs=missing,
                provenance_refs=tuple(
                    sorted({ref for unit in covered for ref in unit.provenance_refs})
                ),
            ),
        ),
    )
