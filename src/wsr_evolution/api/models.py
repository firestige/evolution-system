from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)


TaskId = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/@-]*$",
    ),
]


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvaluationSelection(ClosedModel):
    selection_version: Literal[1]
    task_ids: tuple[TaskId, ...] = Field(min_length=1, max_length=24)

    @model_validator(mode="after")
    def canonicalize_task_ids(self) -> Self:
        if len(set(self.task_ids)) != len(self.task_ids):
            raise ValueError("task_ids must be duplicate-free")
        canonical = tuple(sorted(self.task_ids, key=lambda value: value.encode("utf-8")))
        object.__setattr__(self, "task_ids", canonical)
        return self


class SingleRequest(ClosedModel):
    api_version: Literal[1]
    mode: Literal["SINGLE"]
    selection: EvaluationSelection


class CompareRequest(ClosedModel):
    api_version: Literal[1]
    mode: Literal["COMPARE"]
    left: EvaluationSelection
    right: EvaluationSelection


ComputeRequest = Annotated[SingleRequest | CompareRequest, Field(discriminator="mode")]
