from fractions import Fraction

from wsr_evolution.api.models import ExactValue, MetricResult, MetricSlice
from wsr_evolution.domain.models import OperationalCallUnit

from .common import coverage, rational, unavailable
from .protocol import CalculatorSlot

SLOT = CalculatorSlot("operational-latency-ms@2.0.0", __name__)


def calculate(units: tuple[OperationalCallUnit, ...]) -> MetricResult:
    cohorts = sorted({unit.cohort for unit in units if unit.cohort is not None})
    slices = []
    for cohort in cohorts:
        assert cohort is not None
        group = tuple(unit for unit in units if unit.cohort == cohort)
        covered = tuple(unit for unit in group if unit.duration_ns is not None)
        if not covered:
            continue
        total_ns = sum(unit.duration_ns for unit in covered if unit.duration_ns is not None)
        average_ms = Fraction(total_ns, len(covered) * 1_000_000)
        value: int | str = (
            average_ms.numerator if average_ms.denominator == 1 else rational(average_ms)
        )
        provider, model, role, runtime = cohort
        slices.append(
            MetricSlice(
                slice_key={
                    "provider": provider,
                    "model": model,
                    "role": role,
                    "runtime": runtime,
                },
                state="AVAILABLE",
                value=ExactValue(kind="DURATION_MS", value=value, unit="milliseconds"),
                measures={"sum_ns": total_ns},
                contributing_count=len(covered),
                coverage=coverage(len(covered), len(group)),
                compatibility={
                    "provider": provider,
                    "model": model,
                    "role": role,
                    "runtime": runtime,
                },
                missing_inputs=tuple(
                    sorted(
                        f"model_call.duration:{unit.call_identity}"
                        for unit in group
                        if unit.duration_ns is None
                    )
                ),
                provenance_refs=tuple(
                    sorted({ref for unit in covered for ref in unit.provenance_refs})
                ),
            )
        )
    if not slices:
        return unavailable("operational-latency-ms", metric_coverage=coverage(0, len(units)))
    return MetricResult(
        metric_id="operational-latency-ms", metric_version="2.0.0", slices=tuple(slices)
    )
