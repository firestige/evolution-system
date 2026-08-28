from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from wsr_evolution.api.models import (
    CatalogBinding,
    CompareResponse,
    Coverage,
    DeltaEntry,
    EvaluationSelection,
    EvidenceBinding,
    ExactValue,
    InputReference,
    MetricResult,
    MetricSlice,
    ResolvedEvaluationContext,
    SideError,
    SideResult,
    SingleResponse,
    TaskPopulationEntry,
)
from wsr_evolution.catalog import CATALOG_COORDINATES


def coverage(*, numerator: int = 1, denominator: int = 1, raw_ratio: str = "1") -> Coverage:
    return Coverage(
        numerator=numerator,
        denominator=denominator,
        raw_ratio=raw_ratio,
        state="FULL",
        alert=False,
    )


def test_receipt_canonicalizes_route_local_read_set_without_global_snapshot() -> None:
    context = ResolvedEvaluationContext(
        context_version=1,
        selection=EvaluationSelection(selection_version=1, task_ids=("task-b", "task-a")),
        as_of=datetime(2026, 8, 28, 1, 0, tzinfo=UTC),
        resolved_at=datetime(2026, 8, 28, 1, 1, tzinfo=UTC),
        task_population=(
            TaskPopulationEntry(task_id="task-b", delivery_ids=("delivery-2",)),
            TaskPopulationEntry(
                task_id="task-a",
                display_name="Readable A",
                delivery_ids=("delivery-3", "delivery-1"),
            ),
        ),
        catalog=CatalogBinding(
            catalog_id="agentops.evaluation.metric-catalog",
            version="1.0.0",
            semantic_digest="6dbb4375507a3a2eebbe5e86bb6f0a40ebf811790f55ee841b15c6942e1f159d",
            observation_profile="1.0.0",
        ),
        evidence_bindings=(
            EvidenceBinding(
                route="/v1/evidence/traces",
                canonical_filter={"delivery_id": "delivery-2"},
                route_snapshot="trace-snapshot-1",
                completion_state="COMPLETE",
            ),
            EvidenceBinding(
                route="/v1/evidence/facts",
                canonical_filter={"task_id": "task-a"},
                route_snapshot="fact-snapshot-1",
                completion_state="PARTIAL",
                error_state="CURSOR_EXPIRED",
            ),
        ),
        input_refs=(
            InputReference(kind="TRACE_NODE", identity="trace-z/span-z"),
            InputReference(kind="FACT", identity="fact-a"),
        ),
        population_state="PARTIAL",
    )

    payload = context.model_dump(mode="json", exclude_none=True)

    assert payload["selection"]["task_ids"] == ["task-a", "task-b"]
    assert [entry["task_id"] for entry in payload["task_population"]] == ["task-a", "task-b"]
    assert payload["task_population"][0]["delivery_ids"] == ["delivery-1", "delivery-3"]
    assert [binding["route"] for binding in payload["evidence_bindings"]] == [
        "/v1/evidence/facts",
        "/v1/evidence/traces",
    ]
    assert [reference["identity"] for reference in payload["input_refs"]] == [
        "fact-a",
        "trace-z/span-z",
    ]
    assert payload["as_of"] != payload["resolved_at"]
    assert "global_snapshot" not in payload
    assert "snapshot_digest" not in payload
    assert "manifest_digest" not in payload


@pytest.mark.parametrize("unknown", ["global_snapshot", "snapshot_digest", "manifest_digest"])
def test_receipt_rejects_global_snapshot_or_manifest_fields(unknown: str) -> None:
    payload = {
        "context_version": 1,
        "selection": {"selection_version": 1, "task_ids": ["task-a"]},
        "as_of": "2026-08-28T01:00:00Z",
        "resolved_at": "2026-08-28T01:01:00Z",
        "task_population": [],
        "catalog": {
            "catalog_id": "agentops.evaluation.metric-catalog",
            "version": "1.0.0",
            "semantic_digest": "6dbb4375507a3a2eebbe5e86bb6f0a40ebf811790f55ee841b15c6942e1f159d",
            "observation_profile": "1.0.0",
        },
        "evidence_bindings": [],
        "input_refs": [],
        "population_state": "COMPLETE",
        unknown: "forbidden",
    }

    with pytest.raises(ValidationError):
        ResolvedEvaluationContext.model_validate(payload)


def test_explicit_zero_and_sample_withholding_are_distinct() -> None:
    available = MetricSlice(
        slice_key={},
        state="AVAILABLE",
        value=ExactValue(kind="COUNT", value=0, unit="count"),
        coverage=coverage(),
    )
    insufficient = MetricSlice(
        slice_key={},
        state="UNAVAILABLE",
        withholding_reason="SAMPLE_INSUFFICIENT",
        coverage=coverage(numerator=9, denominator=20, raw_ratio="0.45"),
    )

    assert available.model_dump(mode="json", exclude_none=True)["value"]["value"] == 0
    assert "value" not in insufficient.model_dump(mode="json", exclude_none=True)
    assert insufficient.coverage.numerator == 9


@pytest.mark.parametrize("value", [0.1, "1e3", "01", "-0", "NaN", "Infinity"])
def test_authoritative_decimal_rejects_float_or_noncanonical_string(value: object) -> None:
    with pytest.raises(ValidationError):
        ExactValue.model_validate(
            {
                "kind": "RATIO",
                "value": value,
                "unit": "ratio",
                "precision": 2,
                "rounding": "ROUND_HALF_EVEN",
            }
        )


def test_metric_result_rejects_duplicate_or_noncanonical_slice_keys() -> None:
    slice_b = MetricSlice(
        slice_key={"outcome": "B"},
        state="UNAVAILABLE",
        withholding_reason="MISSING_INPUT",
        coverage=coverage(),
    )
    slice_a = MetricSlice(
        slice_key={"outcome": "A"},
        state="UNAVAILABLE",
        withholding_reason="MISSING_INPUT",
        coverage=coverage(),
    )
    result = MetricResult(
        metric_id="delivery-terminal-outcome-rate",
        metric_version="1.0.0",
        slices=(slice_b, slice_a),
    )

    assert [item.slice_key["outcome"] for item in result.slices] == ["A", "B"]

    with pytest.raises(ValidationError):
        MetricResult(
            metric_id="delivery-terminal-outcome-rate",
            metric_version="1.0.0",
            slices=(slice_a, slice_a),
        )


@pytest.mark.parametrize(
    ("state", "value", "withholding_reason"),
    [
        ("AVAILABLE", None, None),
        ("UNAVAILABLE", {"kind": "COUNT", "value": 0, "unit": "count"}, None),
        ("UNAVAILABLE", None, None),
        ("AVAILABLE", {"kind": "COUNT", "value": 0, "unit": "count"}, "MISSING_INPUT"),
        ("ERROR", None, "MISSING_INPUT"),
    ],
)
def test_metric_slice_truth_and_value_shape_is_closed(
    state: str,
    value: dict[str, object] | None,
    withholding_reason: str | None,
) -> None:
    with pytest.raises(ValidationError):
        MetricSlice.model_validate(
            {
                "slice_key": {},
                "state": state,
                "value": value,
                "withholding_reason": withholding_reason,
                "coverage": coverage().model_dump(mode="json"),
            }
        )


def minimal_context(task_id: str) -> ResolvedEvaluationContext:
    return ResolvedEvaluationContext(
        context_version=1,
        selection=EvaluationSelection(selection_version=1, task_ids=(task_id,)),
        as_of=datetime(2026, 8, 28, 1, 0, tzinfo=UTC),
        resolved_at=datetime(2026, 8, 28, 1, 1, tzinfo=UTC),
        task_population=(),
        catalog=CatalogBinding(
            catalog_id="agentops.evaluation.metric-catalog",
            version="1.0.0",
            semantic_digest="6dbb4375507a3a2eebbe5e86bb6f0a40ebf811790f55ee841b15c6942e1f159d",
            observation_profile="1.0.0",
        ),
        evidence_bindings=(),
        input_refs=(),
        population_state="COMPLETE",
    )


def unavailable_result(coordinate: str) -> MetricResult:
    metric_id, metric_version = coordinate.rsplit("@", 1)
    return MetricResult(
        metric_id=metric_id,
        metric_version=metric_version,
        slices=(
            MetricSlice(
                slice_key={},
                state="UNAVAILABLE",
                withholding_reason="MISSING_INPUT",
                coverage=Coverage(
                    numerator=0,
                    denominator=0,
                    raw_ratio="0",
                    state="NO_POPULATION",
                    alert=True,
                ),
            ),
        ),
    )


def side_result(task_id: str) -> SideResult:
    return SideResult(
        tag="SIDE_RESULT",
        receipt=minimal_context(task_id),
        metric_results=tuple(unavailable_result(item) for item in CATALOG_COORDINATES),
    )


def test_successful_side_requires_exact_fourteen_catalog_coordinates() -> None:
    response = SingleResponse(api_version=1, mode="SINGLE", result=side_result("task-a"))

    assert len(response.result.metric_results) == 14
    assert tuple(
        f"{result.metric_id}@{result.metric_version}" for result in response.result.metric_results
    ) == CATALOG_COORDINATES

    with pytest.raises(ValidationError):
        SideResult(
            tag="SIDE_RESULT",
            receipt=minimal_context("task-a"),
            metric_results=tuple(
                unavailable_result(item) for item in CATALOG_COORDINATES[:-1]
            ),
        )


def test_partial_compare_retains_successful_side_and_all_unresolved_deltas() -> None:
    response = CompareResponse(
        api_version=1,
        mode="COMPARE",
        status="PARTIAL_COMPARE",
        left=side_result("task-a"),
        right=SideError(
            tag="SIDE_ERROR",
            code="EVIDENCE_UNAVAILABLE",
            retryable=True,
            detail="Evidence did not answer",
        ),
        deltas=tuple(
            DeltaEntry(metric_coordinate=item, state="SIDE_UNRESOLVED")
            for item in CATALOG_COORDINATES
        ),
    )

    assert response.left.tag == "SIDE_RESULT"
    assert response.right.tag == "SIDE_ERROR"
    assert len(response.deltas) == 14

    with pytest.raises(ValidationError):
        CompareResponse(
            api_version=1,
            mode="COMPARE",
            status="PARTIAL_COMPARE",
            left=side_result("task-a"),
            right=response.right,
            deltas=(
                DeltaEntry(metric_coordinate=CATALOG_COORDINATES[0], state="AVAILABLE"),
                *response.deltas[1:],
            ),
        )
