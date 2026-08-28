from dataclasses import replace
from datetime import UTC, datetime
from typing import Literal, cast

import pytest

from wsr_evolution.api.models import (
    CompareRequest,
    CompareResponse,
    EvaluationSelection,
    EvidenceBinding,
    SideError,
    SingleRequest,
    SingleResponse,
    TaskMembershipReference,
    TaskPopulationEntry,
    WorkflowResolutionAttempt,
    WorkflowResolutionEntry,
)
from wsr_evolution.application import UpstreamContractMismatch, UpstreamUnavailable
from wsr_evolution.catalog import CATALOG_COORDINATES, CATALOG_SEMANTIC_DIGEST
from wsr_evolution.compute import EvolutionComputeService
from wsr_evolution.domain.ports import FactReading, TraceNodeReading
from wsr_evolution.resolution.service import (
    ResolvedDeliveryObservation,
    ResolvedSelectionPopulation,
)

NOW = datetime(2026, 8, 28, 1, tzinfo=UTC)


class PopulationStub:
    async def resolve(
        self, selection: EvaluationSelection, *, as_of: datetime
    ) -> ResolvedSelectionPopulation:
        assert as_of == NOW
        return ResolvedSelectionPopulation(
            task_population=(
                TaskPopulationEntry(
                    task_id=selection.task_ids[0],
                    memberships=(
                        TaskMembershipReference(
                            delivery_id="delivery-a",
                            manifest_digest="a" * 64,
                            accepted_digest="b" * 64,
                            profile_version="2.0.0",
                            source_identity="event:membership",
                            recorded_at=NOW,
                        ),
                    ),
                ),
            ),
            evidence_bindings=(
                EvidenceBinding(
                    route="/v1/evidence/tasks",
                    canonical_filter={
                        "task_id": selection.task_ids[0],
                        "as_of": "2026-08-28T01:00:00.000000Z",
                    },
                    contract_revision="1.0.0",
                    observation_profile="2.0.0",
                    read_model_revision="2.0.0",
                    route_snapshot="tasks-a",
                    completion_state="COMPLETE",
                ),
            ),
            input_refs=(),
            workflow_resolutions=(
                WorkflowResolutionEntry(
                    manifest_digest="a" * 64,
                    manifest_projection_digest="f" * 64,
                    accepted_digest="b" * 64,
                    profile_version="2.0.0",
                    source_identity="event:membership",
                    package_name="implementation",
                    exact_package_version="2.0.0",
                    package_digest=f"sha256:{'1' * 64}",
                    workflow_id="workflow.implementation",
                    workflow_version="2.0.0",
                    snapshot_id="snapshot.implementation.2",
                    snapshot_digest=f"sha256:{'2' * 64}",
                    state="NOT_FOUND",
                    attempts=(
                        WorkflowResolutionAttempt(
                            source_id="official", source_index=0, code="NOT_FOUND"
                        ),
                    ),
                ),
            ),
        )


def delivery_summary() -> FactReading:
    return FactReading(
        fact_id="fact-summary",
        kind="EVENT_CONTRIBUTION",
        source_identity="event:summary",
        recorded_at=NOW,
        accepted_digest="c" * 64,
        event_name="delivery.summary",
        completeness="FINAL",
        availability="AVAILABLE",
        expiry="ACTIVE",
        fields=(("C10", "SUCCEEDED"), ("C55", 10), ("C56", "review")),
        compatibility=(),
    )


def model_node() -> TraceNodeReading:
    return TraceNodeReading(
        resource_id="node-a",
        trace_id="d" * 32,
        span_id="e" * 16,
        source_identity=f"span:{'d' * 32}/{'e' * 16}",
        recorded_at=NOW,
        availability="AVAILABLE",
        expiry="ACTIVE",
        start_time_unix_nano=0,
        end_time_unix_nano=2_000_000,
        span_status="OK",
        fields=(
            ("gen_ai.provider.name", "openai"),
            ("C57", "gpt-5"),
            ("C30", "writer"),
            ("C06", "dsh"),
            ("gen_ai.usage.input_tokens", 5),
        ),
    )


class ObservationStub:
    async def resolve(self, *, delivery_id: str) -> ResolvedDeliveryObservation:
        assert delivery_id == "delivery-a"
        return ResolvedDeliveryObservation(
            delivery_id=delivery_id,
            facts=(delivery_summary(),),
            trace_nodes=(model_node(),),
            trace_state="AVAILABLE",
            evidence_bindings=tuple(
                EvidenceBinding(
                    route=cast(
                        Literal[
                            "/v1/evidence/tasks",
                            "/v1/evidence/facts",
                            "/v1/evidence/traces",
                        ],
                        route,
                    ),
                    canonical_filter={"delivery_id": delivery_id},
                    contract_revision="0.1.0",
                    observation_profile="1.0.0",
                    read_model_revision="1.0.0",
                    route_snapshot=snapshot,
                    completion_state="COMPLETE",
                )
                for route, snapshot in (
                    ("/v1/evidence/facts", "facts-a"),
                    ("/v1/evidence/traces", "traces-a"),
                )
            ),
            input_refs=(),
        )


class AdvancingObservationStub(ObservationStub):
    def __init__(self) -> None:
        self.calls = 0

    async def resolve(self, *, delivery_id: str) -> ResolvedDeliveryObservation:
        resolved = await super().resolve(delivery_id=delivery_id)
        self.calls += 1
        node = replace(
            resolved.trace_nodes[0],
            end_time_unix_nano=2_000_000 if self.calls == 1 else 4_000_000,
        )
        return replace(resolved, trace_nodes=(node,))


class ConflictingObservationStub(ObservationStub):
    async def resolve(self, *, delivery_id: str) -> ResolvedDeliveryObservation:
        resolved = await super().resolve(delivery_id=delivery_id)
        conflicting = replace(
            delivery_summary(),
            fact_id="fact-conflict",
            fields=(("C10", "FAILED"),),
        )
        return ResolvedDeliveryObservation(
            delivery_id=resolved.delivery_id,
            facts=(*resolved.facts, conflicting),
            trace_nodes=resolved.trace_nodes,
            trace_state=resolved.trace_state,
            evidence_bindings=resolved.evidence_bindings,
            input_refs=resolved.input_refs,
        )


@pytest.mark.asyncio
async def test_single_compute_orchestrates_resolved_evidence_into_all_twelve_results() -> None:
    response = await EvolutionComputeService(
        PopulationStub(), ObservationStub(), now=lambda: NOW
    ).compute(
        SingleRequest(
            api_version=1,
            mode="SINGLE",
            selection=EvaluationSelection(selection_version=1, task_ids=("task-a",)),
        )
    )

    assert isinstance(response, SingleResponse)
    assert response.mode == "SINGLE"
    assert response.result.receipt.catalog.version == "2.0.0"
    assert response.result.receipt.catalog.semantic_digest == CATALOG_SEMANTIC_DIGEST
    assert (
        tuple(f"{item.metric_id}@{item.metric_version}" for item in response.result.metric_results)
        == CATALOG_COORDINATES
    )
    by_id = {item.metric_id: item for item in response.result.metric_results}
    terminal = by_id["delivery-terminal-outcome-rate"].slices[0].value
    cycle = by_id["delivery-cycle-time-ms"].slices[0].value
    latency = by_id["operational-latency-ms"].slices[0].value
    assert terminal is not None and terminal.value == "1"
    assert cycle is not None and cycle.value == 10
    assert latency is not None and latency.value == 2
    assert by_id["operational-attributable-cost"].slices[0].value is None
    assert len(response.result.receipt.evidence_bindings) == 3
    task = response.result.receipt.task_population[0]
    assert task.terminal_reading == "SUCCEEDED"
    assert task.exclusions == ()


@pytest.mark.asyncio
async def test_full_compare_aligns_exact_slices_and_computes_exact_deltas() -> None:
    selection = EvaluationSelection(selection_version=1, task_ids=("task-a",))
    response = await EvolutionComputeService(
        PopulationStub(), ObservationStub(), now=lambda: NOW
    ).compute(
        CompareRequest(
            api_version=1,
            mode="COMPARE",
            left=selection,
            right=selection,
        )
    )

    assert isinstance(response, CompareResponse)
    assert response.mode == "COMPARE"
    assert response.status == "FULL_COMPARE"
    assert response.left.tag == "SIDE_RESULT"
    assert response.right.tag == "SIDE_RESULT"
    assert any(entry.state == "AVAILABLE" for entry in response.deltas)
    assert all(
        entry.direction == "NO_CHANGE" for entry in response.deltas if entry.state == "AVAILABLE"
    )


@pytest.mark.asyncio
async def test_full_compare_subtracts_after_minus_before_in_authoritative_unit() -> None:
    selection = EvaluationSelection(selection_version=1, task_ids=("task-a",))
    response = await EvolutionComputeService(
        PopulationStub(), AdvancingObservationStub(), now=lambda: NOW
    ).compute(
        CompareRequest(
            api_version=1,
            mode="COMPARE",
            left=selection,
            right=selection,
        )
    )

    assert isinstance(response, CompareResponse)
    latency = next(
        entry
        for entry in response.deltas
        if entry.metric_coordinate == "operational-latency-ms@2.0.0"
    )
    assert latency.state == "AVAILABLE"
    assert latency.value is not None
    assert latency.value.kind == "DURATION_MS"
    assert latency.value.unit == "milliseconds"
    assert latency.value.value == 2
    assert latency.direction == "INCREASE"


class PartiallyUnavailablePopulation(PopulationStub):
    async def resolve(
        self, selection: EvaluationSelection, *, as_of: datetime
    ) -> ResolvedSelectionPopulation:
        if selection.task_ids == ("task-b",):
            raise UpstreamUnavailable("task-b Evidence unavailable")
        return await super().resolve(selection, as_of=as_of)


@pytest.mark.asyncio
async def test_partial_compare_preserves_successful_side_and_withholds_all_deltas() -> None:
    response = await EvolutionComputeService(
        PartiallyUnavailablePopulation(), ObservationStub(), now=lambda: NOW
    ).compute(
        CompareRequest(
            api_version=1,
            mode="COMPARE",
            left=EvaluationSelection(selection_version=1, task_ids=("task-a",)),
            right=EvaluationSelection(selection_version=1, task_ids=("task-b",)),
        )
    )

    assert isinstance(response, CompareResponse)
    assert response.status == "PARTIAL_COMPARE"
    assert response.left.tag == "SIDE_RESULT"
    assert isinstance(response.right, SideError)
    assert response.right.retryable is True
    assert all(entry.state == "SIDE_UNRESOLVED" for entry in response.deltas)


@pytest.mark.asyncio
async def test_conflicting_evidence_reading_is_a_typed_upstream_mismatch() -> None:
    with pytest.raises(UpstreamContractMismatch, match="normalization"):
        await EvolutionComputeService(
            PopulationStub(), ConflictingObservationStub(), now=lambda: NOW
        ).compute(
            SingleRequest(
                api_version=1,
                mode="SINGLE",
                selection=EvaluationSelection(selection_version=1, task_ids=("task-a",)),
            )
        )
