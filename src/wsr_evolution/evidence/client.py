import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Annotated, Literal, Self

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from wsr_evolution.api.models import Digest, TaskId
from wsr_evolution.application import UpstreamContractMismatch, UpstreamUnavailable
from wsr_evolution.domain.ports import (
    DeliveryManifestReading,
    ManifestRoleBinding,
    ManifestWorkflow,
    TaskMembershipPage,
    TaskMembershipSummary,
    TaskPage,
    TaskSummary,
)

Sha256Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[a-f0-9]{64}$")]


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Contract(_ClosedModel):
    name: Literal["evidence.query"]
    revision: Literal["1.0.0"]


class _EventSource(_ClosedModel):
    kind: Literal["EVENT"]
    event_id: str = Field(min_length=1, max_length=512)


class _SpanSource(_ClosedModel):
    kind: Literal["SPAN"]
    trace_id: str = Field(min_length=1, max_length=128)
    span_id: str = Field(min_length=1, max_length=128)


_Source = Annotated[_EventSource | _SpanSource, Field(discriminator="kind")]


class _TaskProvenance(_ClosedModel):
    accepted_digest: Digest
    profile_version: Literal["2.0.0"]
    source: _Source


class _TaskMembership(_ClosedModel):
    task_id: TaskId
    delivery_id: str = Field(min_length=1, max_length=256)
    manifest_digest: Digest
    recorded_at: datetime
    provenance: _TaskProvenance


class _TaskListProvenance(_TaskProvenance):
    recorded_at: datetime


class _TaskListItem(_ClosedModel):
    task_id: TaskId
    display_name: str | None = Field(default=None, min_length=1, max_length=160)
    provenance: _TaskListProvenance


class _TaskMembershipEnvelope(_ClosedModel):
    contract: _Contract
    observation_profile: Literal["2.0.0"]
    read_model_revision: Literal["2.0.0"]
    snapshot: str = Field(min_length=1, max_length=512)
    items: tuple[_TaskMembership, ...]
    next_cursor: str | None


class _TaskListEnvelope(_ClosedModel):
    contract: _Contract
    observation_profile: Literal["2.0.0"]
    read_model_revision: Literal["2.0.0"]
    snapshot: str = Field(min_length=1, max_length=512)
    items: tuple[_TaskListItem, ...]
    next_cursor: str | None


class _ManifestWorkflow(_ClosedModel):
    package_name: str = Field(min_length=1, max_length=128)
    exact_package_version: str = Field(
        pattern=r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
    )
    package_digest: Sha256Digest
    workflow_id: str = Field(min_length=1, max_length=128)
    workflow_version: str = Field(pattern=r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
    snapshot_id: str = Field(min_length=1, max_length=128)
    snapshot_digest: Sha256Digest


class _RepositoryBindings(_ClosedModel):
    document_state: Literal["ABSENT", "PRESENT"]
    document_digest: Sha256Digest | None = None
    resolved_map_digest: Sha256Digest

    @model_validator(mode="after")
    def exact_document_state(self) -> Self:
        if (self.document_state == "PRESENT") != (self.document_digest is not None):
            raise ValueError("repository document digest applicability mismatch")
        return self


class _ManifestRole(_ClosedModel):
    role_id: str = Field(min_length=1, max_length=128)
    role_prompt_identity: str = Field(min_length=1, max_length=128)
    role_prompt_digest: Sha256Digest
    agent_provider_id: str = Field(min_length=1, max_length=128)
    model_provider_id: str = Field(min_length=1, max_length=128)
    model_id: str = Field(min_length=1, max_length=128)
    resolution_source: Literal["REPOSITORY", "EXECUTION_DEFAULT"]


class _ManifestProjection(_ClosedModel):
    schema_version: Literal["execution.delivery-manifest-projection@1.0.0"]
    delivery_id: str = Field(min_length=1, max_length=256)
    task_id: TaskId
    manifest_digest: Digest
    workflow: _ManifestWorkflow
    repository_model_bindings: _RepositoryBindings
    roles: tuple[_ManifestRole, ...] = Field(max_length=128)

    @model_validator(mode="after")
    def exact_role_map(self) -> Self:
        role_ids = tuple(role.role_id for role in self.roles)
        if role_ids != tuple(sorted(set(role_ids), key=lambda value: value.encode())):
            raise ValueError("Manifest Roles must be unique and bytewise sorted")
        resolved = [
            {
                "roleId": role.role_id,
                "rolePromptIdentity": role.role_prompt_identity,
                "rolePromptDigest": role.role_prompt_digest,
                "agentProviderId": role.agent_provider_id,
                "modelProviderId": role.model_provider_id,
                "modelId": role.model_id,
                "resolutionSource": role.resolution_source,
            }
            for role in self.roles
        ]
        digest = (
            "sha256:"
            + sha256(
                json.dumps(
                    resolved, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
        )
        if digest != self.repository_model_bindings.resolved_map_digest:
            raise ValueError("resolved Role map digest mismatch")
        return self


class _ManifestEnvelope(_ClosedModel):
    contract: _Contract
    observation_profile: Literal["2.0.0"]
    read_model_revision: Literal["2.0.0"]
    manifest: _ManifestProjection
    manifest_projection_digest: Digest
    provenance: _TaskProvenance


def _normalized_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Evidence cutoff must include an offset")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _source_identity(source: _Source) -> str:
    if source.kind == "EVENT":
        return f"event:{source.event_id}"
    return f"span:{source.trace_id}/{source.span_id}"


class EvidenceHttpClient:
    def __init__(self, transport: httpx.AsyncClient) -> None:
        self._transport = transport

    async def list_tasks(self, *, limit: int, cursor: str | None) -> TaskPage:
        payload = await self._get(
            "/v1/evidence/tasks",
            params={"limit": str(limit), **({"cursor": cursor} if cursor else {})},
        )
        try:
            envelope = _TaskListEnvelope.model_validate(payload)
        except ValidationError as error:
            raise UpstreamContractMismatch("Evidence Task list contract mismatch") from error
        return TaskPage(
            tasks=tuple(
                TaskSummary(task_id=item.task_id, display_name=item.display_name)
                for item in envelope.items
            ),
            next_cursor=envelope.next_cursor,
            route_snapshot=envelope.snapshot,
        )

    async def resolve_membership(
        self,
        *,
        task_id: str,
        as_of: datetime,
        limit: int,
        cursor: str | None,
    ) -> TaskMembershipPage:
        payload = await self._get(
            "/v1/evidence/tasks",
            params={
                "task_id": task_id,
                "as_of": _normalized_utc(as_of),
                "limit": str(limit),
                **({"cursor": cursor} if cursor else {}),
            },
        )
        try:
            envelope = _TaskMembershipEnvelope.model_validate(payload)
        except ValidationError as error:
            raise UpstreamContractMismatch("Evidence Task membership contract mismatch") from error
        return TaskMembershipPage(
            memberships=tuple(
                TaskMembershipSummary(
                    task_id=item.task_id,
                    delivery_id=item.delivery_id,
                    manifest_digest=item.manifest_digest,
                    accepted_digest=item.provenance.accepted_digest,
                    profile_version=item.provenance.profile_version,
                    source_identity=_source_identity(item.provenance.source),
                    recorded_at=item.recorded_at,
                )
                for item in envelope.items
            ),
            as_of=as_of,
            next_cursor=envelope.next_cursor,
            route_snapshot=envelope.snapshot,
        )

    async def resolve_manifest(self, *, manifest_digest: str) -> DeliveryManifestReading:
        payload = await self._get(
            "/v1/evidence/manifests", params={"manifest_digest": manifest_digest}
        )
        try:
            envelope = _ManifestEnvelope.model_validate(payload)
            canonical = json.dumps(
                envelope.manifest.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            if (
                envelope.manifest.manifest_digest != manifest_digest
                or sha256(canonical.encode()).hexdigest() != envelope.manifest_projection_digest
            ):
                raise ValueError("Manifest projection identity or digest mismatch")
        except (ValidationError, ValueError) as error:
            raise UpstreamContractMismatch("Evidence Manifest contract mismatch") from error
        manifest = envelope.manifest
        repository = manifest.repository_model_bindings
        return DeliveryManifestReading(
            delivery_id=manifest.delivery_id,
            task_id=manifest.task_id,
            manifest_digest=manifest.manifest_digest,
            projection_digest=envelope.manifest_projection_digest,
            workflow=ManifestWorkflow(**manifest.workflow.model_dump()),
            repository_document_state=repository.document_state,
            repository_document_digest=repository.document_digest,
            resolved_map_digest=repository.resolved_map_digest,
            roles=tuple(ManifestRoleBinding(**role.model_dump()) for role in manifest.roles),
            accepted_digest=envelope.provenance.accepted_digest,
            profile_version=envelope.provenance.profile_version,
            source_identity=_source_identity(envelope.provenance.source),
        )

    async def _get(self, path: str, *, params: dict[str, str]) -> object:
        try:
            response = await self._transport.get(
                path,
                params=params,
                headers={"accept": "application/json"},
            )
        except httpx.HTTPError as error:
            raise UpstreamUnavailable("Evidence transport failed") from error
        if response.status_code == 200:
            try:
                return response.json()
            except ValueError as error:
                raise UpstreamContractMismatch("Evidence returned malformed JSON") from error
        if response.status_code in {408, 410, 429, 503, 504}:
            raise UpstreamUnavailable(f"Evidence query failed with HTTP {response.status_code}")
        raise UpstreamContractMismatch(
            f"Evidence query failed incompatibly with HTTP {response.status_code}"
        )
