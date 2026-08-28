from datetime import UTC, datetime
from typing import Annotated, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from wsr_evolution.api.models import Digest, TaskId
from wsr_evolution.application import UpstreamContractMismatch, UpstreamUnavailable
from wsr_evolution.domain.ports import (
    TaskMembershipPage,
    TaskMembershipSummary,
    TaskPage,
    TaskSummary,
)


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
