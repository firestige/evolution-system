import json
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
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


CanonicalDecimal = Annotated[
    str,
    StringConstraints(pattern=r"^(?:0|[1-9][0-9]*|-[1-9][0-9]*)(?:\.[0-9]+)?$"),
]
Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
TruthState = Literal[
    "AVAILABLE",
    "LOWER_BOUND",
    "NOT_APPLICABLE",
    "UNAVAILABLE",
    "EXPIRED",
    "INCOMPATIBLE",
]
WithholdingReason = Literal[
    "SAMPLE_INSUFFICIENT",
    "MISSING_INPUT",
    "NO_APPLICABLE_POPULATION",
    "OPEN_TASK",
    "MIXED_TASK_OUTCOMES",
    "EXPIRED_INPUT",
    "INCOMPATIBLE_INPUT",
]


def _sorted_mapping(value: dict[str, str]) -> dict[str, str]:
    return dict(sorted(value.items(), key=lambda item: item[0].encode("utf-8")))


class Coverage(ClosedModel):
    numerator: StrictInt = Field(ge=0)
    denominator: StrictInt = Field(ge=0)
    raw_ratio: CanonicalDecimal
    state: Literal["NO_POPULATION", "NO_COVERAGE", "PARTIAL", "FULL"]
    alert: StrictBool

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.numerator > self.denominator:
            raise ValueError("coverage numerator cannot exceed denominator")
        return self


class ExactValue(ClosedModel):
    kind: Literal["COUNT", "RATIO", "MONEY", "DURATION_MS", "BOOLEAN"]
    value: StrictInt | StrictBool | CanonicalDecimal
    unit: str = Field(min_length=1, max_length=64)
    precision: StrictInt | None = Field(default=None, ge=0, le=18)
    rounding: Literal["ROUND_HALF_EVEN", "ROUND_HALF_UP"] | None = None

    @model_validator(mode="after")
    def validate_representation(self) -> Self:
        if self.kind == "RATIO":
            if not isinstance(self.value, str) or self.precision is None or self.rounding is None:
                raise ValueError("ratio values require canonical decimal, precision and rounding")
        elif self.kind == "BOOLEAN":
            if not isinstance(self.value, bool):
                raise ValueError("boolean values require a strict boolean")
        elif isinstance(self.value, bool) or not isinstance(self.value, int):
            raise ValueError("count, money and duration values require exact integers")
        elif self.precision is not None or self.rounding is not None:
            raise ValueError("integer values do not declare decimal precision or rounding")
        return self


class MetricSlice(ClosedModel):
    slice_key: dict[str, str]
    state: TruthState
    value: ExactValue | None = None
    withholding_reason: WithholdingReason | None = None
    measures: dict[str, StrictInt | CanonicalDecimal] = Field(default_factory=dict)
    numerator: StrictInt | None = Field(default=None, ge=0)
    denominator: StrictInt | None = Field(default=None, ge=0)
    contributing_count: StrictInt | None = Field(default=None, ge=0)
    coverage: Coverage
    compatibility: dict[str, str] = Field(default_factory=dict)
    exclusions: tuple[str, ...] = ()
    missing_inputs: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()
    reading: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def canonicalize_and_validate_truth(self) -> Self:
        object.__setattr__(self, "slice_key", _sorted_mapping(self.slice_key))
        object.__setattr__(self, "compatibility", _sorted_mapping(self.compatibility))
        object.__setattr__(self, "measures", dict(sorted(self.measures.items())))
        object.__setattr__(self, "exclusions", tuple(sorted(self.exclusions)))
        object.__setattr__(self, "missing_inputs", tuple(sorted(self.missing_inputs)))
        object.__setattr__(self, "provenance_refs", tuple(sorted(self.provenance_refs)))
        has_value = self.value is not None
        if self.state in {"AVAILABLE", "LOWER_BOUND"}:
            if not has_value or self.withholding_reason is not None:
                raise ValueError("available and lower-bound states require value without withholding")
        elif has_value or self.withholding_reason is None:
            raise ValueError("withheld truth states forbid value and require a reason")
        return self


class MetricResult(ClosedModel):
    metric_id: str = Field(min_length=1, max_length=128)
    metric_version: Literal["1.0.0"]
    slices: tuple[MetricSlice, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def canonicalize_slices(self) -> Self:
        def key(item: MetricSlice) -> bytes:
            encoded = json.dumps(item.slice_key, sort_keys=True, separators=(",", ":"))
            return encoded.encode("utf-8")

        ordered = tuple(sorted(self.slices, key=key))
        keys = [key(item) for item in ordered]
        if len(set(keys)) != len(keys):
            raise ValueError("slice keys must be unique")
        if b"{}" in keys and len(keys) != 1:
            raise ValueError("a scalar empty slice key cannot coexist with dimensional slices")
        object.__setattr__(self, "slices", ordered)
        return self


class TaskPopulationEntry(ClosedModel):
    task_id: TaskId
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    delivery_ids: tuple[str, ...]
    cohort_coordinates: dict[str, str] = Field(default_factory=dict)
    terminal_reading: str | None = None

    @model_validator(mode="after")
    def canonicalize_entry(self) -> Self:
        if len(set(self.delivery_ids)) != len(self.delivery_ids):
            raise ValueError("delivery_ids must be duplicate-free")
        object.__setattr__(self, "delivery_ids", tuple(sorted(self.delivery_ids)))
        object.__setattr__(self, "cohort_coordinates", _sorted_mapping(self.cohort_coordinates))
        return self


class CatalogBinding(ClosedModel):
    catalog_id: Literal["agentops.evaluation.metric-catalog"]
    version: Literal["1.0.0"]
    semantic_digest: Digest
    observation_profile: Literal["1.0.0"]


class EvidenceBinding(ClosedModel):
    route: Literal["/v1/evidence/tasks", "/v1/evidence/facts", "/v1/evidence/traces"]
    canonical_filter: dict[str, str]
    route_snapshot: str = Field(min_length=1, max_length=512)
    completion_state: Literal["COMPLETE", "PARTIAL", "EXPIRED"]
    error_state: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def canonicalize_filter(self) -> Self:
        object.__setattr__(self, "canonical_filter", _sorted_mapping(self.canonical_filter))
        if self.completion_state == "COMPLETE" and self.error_state is not None:
            raise ValueError("complete Evidence traversal cannot carry an error")
        if self.completion_state != "COMPLETE" and self.error_state is None:
            raise ValueError("partial or expired Evidence traversal requires an error")
        return self


class InputReference(ClosedModel):
    kind: Literal["FACT", "TRACE_NODE"]
    identity: str = Field(min_length=1, max_length=512)


class ResolvedEvaluationContext(ClosedModel):
    context_version: Literal[1]
    selection: EvaluationSelection
    as_of: datetime
    resolved_at: datetime
    task_population: tuple[TaskPopulationEntry, ...]
    catalog: CatalogBinding
    evidence_bindings: tuple[EvidenceBinding, ...]
    input_refs: tuple[InputReference, ...]
    population_state: Literal["COMPLETE", "PARTIAL", "OPEN", "MIXED", "EXPIRED"]

    @model_validator(mode="after")
    def canonicalize_receipt(self) -> Self:
        if self.as_of.tzinfo is None or self.resolved_at.tzinfo is None:
            raise ValueError("receipt timestamps must include an offset")
        population = tuple(sorted(self.task_population, key=lambda item: item.task_id.encode()))
        bindings = tuple(
            sorted(
                self.evidence_bindings,
                key=lambda item: (
                    item.route.encode(),
                    json.dumps(item.canonical_filter, sort_keys=True).encode(),
                ),
            )
        )
        references = tuple(sorted(self.input_refs, key=lambda item: item.identity.encode()))
        object.__setattr__(self, "task_population", population)
        object.__setattr__(self, "evidence_bindings", bindings)
        object.__setattr__(self, "input_refs", references)
        return self
