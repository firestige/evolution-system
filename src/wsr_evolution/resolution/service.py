from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from wsr_evolution.api.models import (
    EvaluationSelection,
    EvidenceBinding,
    InputReference,
    TaskMembershipReference,
    TaskPopulationEntry,
    WorkflowResolutionAttempt,
    WorkflowResolutionEntry,
)
from wsr_evolution.application import UpstreamContractMismatch
from wsr_evolution.domain.ports import (
    DeliveryManifestReading,
    TaskMembershipPage,
)
from wsr_evolution.workflow_sources.resolution import WorkflowResolution


class SelectionEvidenceReader(Protocol):
    async def resolve_membership(
        self,
        *,
        task_id: str,
        as_of: datetime,
        limit: int,
        cursor: str | None,
    ) -> TaskMembershipPage: ...

    async def resolve_manifest(self, *, manifest_digest: str) -> DeliveryManifestReading: ...


class ManifestWorkflowResolver(Protocol):
    async def resolve(self, reading: DeliveryManifestReading) -> WorkflowResolution: ...


@dataclass(frozen=True, slots=True)
class ResolvedSelectionPopulation:
    task_population: tuple[TaskPopulationEntry, ...]
    evidence_bindings: tuple[EvidenceBinding, ...]
    input_refs: tuple[InputReference, ...]
    workflow_resolutions: tuple[WorkflowResolutionEntry, ...]


def _normalized_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("selection cutoff must include an offset")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _workflow_entry(
    reading: DeliveryManifestReading, resolution: WorkflowResolution
) -> WorkflowResolutionEntry:
    candidate = resolution.candidate
    attempts = tuple(
        WorkflowResolutionAttempt(
            source_id=attempt.source_id,
            source_index=attempt.source_index,
            code=attempt.code,
            omitted_count=attempt.omitted_count,
        )
        for attempt in resolution.attempts
    )
    return WorkflowResolutionEntry(
        manifest_digest=reading.manifest_digest,
        manifest_projection_digest=reading.projection_digest,
        accepted_digest=reading.accepted_digest,
        profile_version="2.0.0",
        source_identity=reading.source_identity,
        package_name=reading.workflow.package_name,
        exact_package_version=reading.workflow.exact_package_version,
        package_digest=reading.workflow.package_digest,
        workflow_id=reading.workflow.workflow_id,
        workflow_version=reading.workflow.workflow_version,
        snapshot_id=reading.workflow.snapshot_id,
        snapshot_digest=reading.workflow.snapshot_digest,
        state=resolution.state,
        matched_source_id=resolution.matched_source_id,
        matched_source_index=resolution.matched_source_index,
        matched_repository=resolution.matched_repository,
        validated_archive_digest=None if candidate is None else candidate.archive_digest,
        validated_package_digest=None if candidate is None else candidate.package_digest,
        validated_snapshot_digest=None if candidate is None else candidate.snapshot_digest,
        attempts=attempts,
    )


class SelectionPopulationResolver:
    def __init__(
        self,
        evidence: SelectionEvidenceReader,
        workflows: ManifestWorkflowResolver,
    ) -> None:
        self._evidence = evidence
        self._workflows = workflows

    async def resolve(
        self, selection: EvaluationSelection, *, as_of: datetime
    ) -> ResolvedSelectionPopulation:
        cutoff = _normalized_utc(as_of)
        populations: list[TaskPopulationEntry] = []
        bindings: list[EvidenceBinding] = []
        references: list[InputReference] = []
        all_memberships: list[tuple[str, TaskMembershipReference]] = []
        for task_id in selection.task_ids:
            cursor: str | None = None
            route_snapshot: str | None = None
            memberships: list[TaskMembershipReference] = []
            while True:
                page = await self._evidence.resolve_membership(
                    task_id=task_id,
                    as_of=as_of,
                    limit=200,
                    cursor=cursor,
                )
                if page.as_of != as_of or (
                    route_snapshot is not None and page.route_snapshot != route_snapshot
                ):
                    raise UpstreamContractMismatch("Evidence Task traversal coordinate drift")
                route_snapshot = page.route_snapshot
                for item in page.memberships:
                    if item.task_id != task_id or item.recorded_at > as_of:
                        raise UpstreamContractMismatch("Evidence Task membership mismatch")
                    reference = TaskMembershipReference(
                        delivery_id=item.delivery_id,
                        manifest_digest=item.manifest_digest,
                        accepted_digest=item.accepted_digest,
                        profile_version="2.0.0",
                        source_identity=item.source_identity,
                        recorded_at=item.recorded_at,
                    )
                    memberships.append(reference)
                    references.append(
                        InputReference(
                            kind="TASK_MEMBERSHIP",
                            identity=f"{task_id}/{item.delivery_id}",
                            provenance_ref=item.source_identity,
                        )
                    )
                cursor = page.next_cursor
                if cursor is None:
                    break
            delivery_ids = [item.delivery_id for item in memberships]
            if len(set(delivery_ids)) != len(delivery_ids) or route_snapshot is None:
                raise UpstreamContractMismatch("Evidence Task traversal is inconsistent")
            ordered = tuple(sorted(memberships, key=lambda item: item.delivery_id.encode()))
            populations.append(
                TaskPopulationEntry(
                    task_id=task_id,
                    memberships=ordered,
                    exclusions=() if ordered else ("UNDEFINED_TASK_MEMBERSHIP",),
                )
            )
            all_memberships.extend((task_id, item) for item in ordered)
            bindings.append(
                EvidenceBinding(
                    route="/v1/evidence/tasks",
                    canonical_filter={"task_id": task_id, "as_of": cutoff},
                    contract_revision="1.0.0",
                    observation_profile="2.0.0",
                    read_model_revision="2.0.0",
                    route_snapshot=route_snapshot,
                    completion_state="COMPLETE",
                )
            )

        readings: dict[str, DeliveryManifestReading] = {}
        membership_by_digest = sorted(
            all_memberships, key=lambda item: item[1].manifest_digest.encode()
        )
        for task_id, membership in membership_by_digest:
            reading = readings.get(membership.manifest_digest)
            if reading is None:
                reading = await self._evidence.resolve_manifest(
                    manifest_digest=membership.manifest_digest
                )
                readings[membership.manifest_digest] = reading
            if (
                reading.task_id != task_id
                or reading.delivery_id != membership.delivery_id
                or reading.manifest_digest != membership.manifest_digest
                or reading.accepted_digest != membership.accepted_digest
                or reading.profile_version != membership.profile_version
                or reading.source_identity != membership.source_identity
            ):
                raise UpstreamContractMismatch(
                    "Evidence Manifest projection conflicts with Task membership"
                )
        workflow_entries = []
        for digest, reading in sorted(readings.items()):
            resolution = await self._workflows.resolve(reading)
            if resolution.manifest_digest != digest:
                raise UpstreamContractMismatch("Workflow resolution selected another Manifest")
            workflow_entries.append(_workflow_entry(reading, resolution))
        return ResolvedSelectionPopulation(
            task_population=tuple(populations),
            evidence_bindings=tuple(bindings),
            input_refs=tuple(sorted(references, key=lambda item: item.identity.encode())),
            workflow_resolutions=tuple(workflow_entries),
        )
