from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class TaskSummary:
    task_id: str
    display_name: str | None


@dataclass(frozen=True, slots=True)
class TaskPage:
    tasks: tuple[TaskSummary, ...]
    next_cursor: str | None
    route_snapshot: str


@dataclass(frozen=True, slots=True)
class TaskMembershipSummary:
    task_id: str
    delivery_id: str
    manifest_digest: str
    accepted_digest: str
    profile_version: str


@dataclass(frozen=True, slots=True)
class TaskMembershipPage:
    memberships: tuple[TaskMembershipSummary, ...]
    as_of: datetime
    next_cursor: str | None
    route_snapshot: str


class EvidenceTaskReader(Protocol):
    async def list_tasks(self, *, limit: int, cursor: str | None) -> TaskPage: ...

    async def resolve_membership(
        self,
        *,
        task_id: str,
        as_of: datetime,
        limit: int,
        cursor: str | None,
    ) -> TaskMembershipPage: ...
