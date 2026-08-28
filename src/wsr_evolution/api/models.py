import json
from datetime import datetime
from decimal import Decimal
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

from wsr_evolution.catalog import CATALOG_COORDINATES

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
                raise ValueError(
                    "available and lower-bound states require value without withholding"
                )
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


class TaskMembershipReference(ClosedModel):
    delivery_id: str = Field(min_length=1, max_length=256)
    manifest_digest: Digest
    accepted_digest: Digest
    profile_version: Literal["2.0.0"]
    source_identity: str = Field(min_length=1, max_length=512)
    recorded_at: datetime


class TaskPopulationEntry(ClosedModel):
    task_id: TaskId
    display_name: str | None = Field(default=None, min_length=1, max_length=160)
    memberships: tuple[TaskMembershipReference, ...]
    cohort_coordinates: dict[str, str] = Field(default_factory=dict)
    exclusions: tuple[str, ...] = ()
    terminal_reading: str | None = None

    @model_validator(mode="after")
    def canonicalize_entry(self) -> Self:
        delivery_ids = [item.delivery_id for item in self.memberships]
        if len(set(delivery_ids)) != len(delivery_ids):
            raise ValueError("Task memberships must be duplicate-free by delivery_id")
        object.__setattr__(
            self,
            "memberships",
            tuple(sorted(self.memberships, key=lambda item: item.delivery_id.encode())),
        )
        object.__setattr__(self, "cohort_coordinates", _sorted_mapping(self.cohort_coordinates))
        object.__setattr__(self, "exclusions", tuple(sorted(self.exclusions)))
        return self


class CatalogBinding(ClosedModel):
    catalog_id: Literal["agentops.evaluation.metric-catalog"]
    version: Literal["1.0.0"]
    semantic_digest: Digest
    observation_profile: Literal["1.0.0"]


class EvidenceBinding(ClosedModel):
    route: Literal["/v1/evidence/tasks", "/v1/evidence/facts", "/v1/evidence/traces"]
    canonical_filter: dict[str, str]
    contract_revision: str = Field(min_length=1, max_length=32)
    observation_profile: str = Field(min_length=1, max_length=32)
    read_model_revision: str = Field(min_length=1, max_length=32)
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
        expected = (
            ("1.0.0", "2.0.0", "2.0.0")
            if self.route == "/v1/evidence/tasks"
            else ("0.1.0", "1.0.0", "1.0.0")
        )
        if (
            self.contract_revision,
            self.observation_profile,
            self.read_model_revision,
        ) != expected:
            raise ValueError("Evidence coordinates are incompatible with the selected route")
        return self


class InputReference(ClosedModel):
    kind: Literal["TASK_MEMBERSHIP", "FACT", "TRACE_NODE"]
    identity: str = Field(min_length=1, max_length=512)
    provenance_ref: str = Field(min_length=1, max_length=512)


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
        references = tuple(
            sorted(self.input_refs, key=lambda item: (item.kind.encode(), item.identity.encode()))
        )
        binding_keys = [
            (item.route, json.dumps(item.canonical_filter, sort_keys=True)) for item in bindings
        ]
        reference_keys = [(item.kind, item.identity) for item in references]
        if len({item.task_id for item in population}) != len(population):
            raise ValueError("task_population must be duplicate-free")
        if {item.task_id for item in population} != set(self.selection.task_ids):
            raise ValueError("task_population must resolve every selected Task exactly once")
        if len(set(binding_keys)) != len(binding_keys):
            raise ValueError("evidence_bindings must be duplicate-free")
        if len(set(reference_keys)) != len(reference_keys):
            raise ValueError("input_refs must be duplicate-free")
        object.__setattr__(self, "task_population", population)
        object.__setattr__(self, "evidence_bindings", bindings)
        object.__setattr__(self, "input_refs", references)
        return self


class SideResult(ClosedModel):
    tag: Literal["SIDE_RESULT"]
    receipt: ResolvedEvaluationContext
    metric_results: tuple[MetricResult, ...]

    @model_validator(mode="after")
    def validate_catalog_completeness(self) -> Self:
        by_coordinate = {
            f"{result.metric_id}@{result.metric_version}": result for result in self.metric_results
        }
        if len(by_coordinate) != len(self.metric_results):
            raise ValueError("metric result coordinates must be unique")
        if set(by_coordinate) != set(CATALOG_COORDINATES):
            raise ValueError("successful side must contain the exact fourteen catalog coordinates")
        object.__setattr__(
            self,
            "metric_results",
            tuple(by_coordinate[coordinate] for coordinate in CATALOG_COORDINATES),
        )
        return self


class SideError(ClosedModel):
    tag: Literal["SIDE_ERROR"]
    code: str = Field(min_length=1, max_length=128)
    retryable: StrictBool
    detail: str = Field(min_length=1, max_length=2048)


class DeltaEntry(ClosedModel):
    metric_coordinate: str
    slice_key: dict[str, str]
    state: Literal["AVAILABLE", "WITHHELD", "SIDE_UNRESOLVED"]
    value: ExactValue | None = None
    withholding_reason: str | None = Field(default=None, max_length=128)
    direction: Literal["INCREASE", "DECREASE", "NO_CHANGE"] | None = None

    @model_validator(mode="after")
    def validate_delta(self) -> Self:
        object.__setattr__(self, "slice_key", _sorted_mapping(self.slice_key))
        if self.metric_coordinate not in CATALOG_COORDINATES:
            raise ValueError("Delta coordinate is not in the bound Evaluation Catalog")
        if self.state == "AVAILABLE":
            if self.value is None or self.withholding_reason is not None or self.direction is None:
                raise ValueError("available Delta requires value without withholding")
            if self.value.kind == "BOOLEAN":
                raise ValueError("boolean values do not have an arithmetic Delta")
            numeric = (
                Decimal(self.value.value)
                if isinstance(self.value.value, str)
                else Decimal(self.value.value)
            )
            expected = "INCREASE" if numeric > 0 else "DECREASE" if numeric < 0 else "NO_CHANGE"
            if self.direction != expected:
                raise ValueError("Delta direction must match the exact value sign")
        elif self.value is not None or self.direction is not None:
            raise ValueError("withheld Delta cannot contain a value or direction")
        elif self.state == "WITHHELD" and self.withholding_reason is None:
            raise ValueError("withheld Delta requires a typed reason")
        return self


SideOutcome = Annotated[SideResult | SideError, Field(discriminator="tag")]


class SingleResponse(ClosedModel):
    api_version: Literal[1]
    mode: Literal["SINGLE"]
    result: SideResult


class CompareResponse(ClosedModel):
    api_version: Literal[1]
    mode: Literal["COMPARE"]
    status: Literal["FULL_COMPARE", "PARTIAL_COMPARE"]
    left: SideOutcome
    right: SideOutcome
    deltas: tuple[DeltaEntry, ...]

    @model_validator(mode="after")
    def validate_compare_shape(self) -> Self:
        def delta_key(entry: DeltaEntry) -> tuple[str, str]:
            return (
                entry.metric_coordinate,
                json.dumps(entry.slice_key, sort_keys=True, separators=(",", ":")),
            )

        by_key = {delta_key(entry): entry for entry in self.deltas}
        if len(by_key) != len(self.deltas):
            raise ValueError("Delta metric/slice identities must be unique")
        results = sum(item.tag == "SIDE_RESULT" for item in (self.left, self.right))
        result_sides = [item for item in (self.left, self.right) if item.tag == "SIDE_RESULT"]
        side_slices = []
        for side in result_sides:
            side_slices.append(
                {
                    (
                        f"{result.metric_id}@{result.metric_version}",
                        json.dumps(metric_slice.slice_key, sort_keys=True, separators=(",", ":")),
                    ): metric_slice
                    for result in side.metric_results
                    for metric_slice in result.slices
                }
            )
        expected = {
            (
                f"{result.metric_id}@{result.metric_version}",
                json.dumps(metric_slice.slice_key, sort_keys=True, separators=(",", ":")),
            )
            for side in result_sides
            for result in side.metric_results
            for metric_slice in result.slices
        }
        if set(by_key) != expected:
            raise ValueError("compare must contain one Delta entry per resolved metric slice")
        if len(side_slices) == 2:
            for key, delta in by_key.items():
                before = side_slices[0].get(key)
                after = side_slices[1].get(key)
                compatible = (
                    before is not None
                    and after is not None
                    and before.value is not None
                    and after.value is not None
                    and before.value.kind == after.value.kind
                    and before.value.unit == after.value.unit
                    and before.compatibility == after.compatibility
                )
                if (delta.state == "AVAILABLE") != compatible:
                    raise ValueError("Delta availability must match paired value compatibility")
        catalog_order = {coordinate: index for index, coordinate in enumerate(CATALOG_COORDINATES)}
        ordered = tuple(
            by_key[key]
            for key in sorted(expected, key=lambda key: (catalog_order[key[0]], key[1].encode()))
        )
        if self.status == "PARTIAL_COMPARE":
            if results != 1 or any(entry.state != "SIDE_UNRESOLVED" for entry in ordered):
                raise ValueError("partial compare requires one side result and unresolved Deltas")
        elif results != 2 or any(entry.state == "SIDE_UNRESOLVED" for entry in ordered):
            raise ValueError(
                "full compare requires two side results and resolved Delta disposition"
            )
        object.__setattr__(self, "deltas", ordered)
        return self


ComputeResponse = SingleResponse | CompareResponse
