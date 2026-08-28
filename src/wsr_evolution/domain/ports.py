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
class TaskMembership:
    task_id: str
    delivery_ids: tuple[str, ...]
    as_of: datetime
    route_snapshot: str


class EvidenceTaskReader(Protocol):
    async def list_tasks(self, *, limit: int, cursor: str | None) -> TaskPage: ...

    async def resolve_membership(self, *, task_id: str, as_of: datetime) -> TaskMembership: ...
