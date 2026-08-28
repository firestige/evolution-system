from wsr_evolution.calculators.role_template_rework_rate import calculate as rework
from wsr_evolution.calculators.role_template_trajectory_partial_cost import (
    calculate as template_cost,
)
from wsr_evolution.domain.models import RoleTemplateTaskUnit, RoleTemplateUsageUnit


def task(index: int, repaired: bool | None = False) -> RoleTemplateTaskUnit:
    return RoleTemplateTaskUnit(
        task_id=f"task-{index:02d}",
        role_id="writer",
        role_prompt_identity="prompt.writer",
        role_prompt_digest=f"sha256:{'a' * 64}",
        repair_observed=repaired,
        provenance_refs=(f"task:{index:02d}",),
    )


def test_role_template_rework_uses_only_covered_tasks() -> None:
    units = tuple(task(index, repaired=index < 4) for index in range(20)) + (task(20, None),)
    metric_slice = rework(units).slices[0]
    assert metric_slice.value is not None and metric_slice.value.value == "1/5"
    assert metric_slice.numerator == 4
    assert metric_slice.denominator == 20
    assert metric_slice.coverage.raw_ratio == "20/21"
    assert metric_slice.missing_inputs == ("repair_attribution:task-20",)


def test_role_template_cost_keeps_template_and_usage_coordinates_exact() -> None:
    tasks = tuple(task(index) for index in range(21))
    usage = tuple(
        RoleTemplateUsageUnit(
            task_id=item.task_id,
            role_id=item.role_id,
            role_prompt_identity=item.role_prompt_identity,
            role_prompt_digest=item.role_prompt_digest,
            kind="money",
            unit="USD",
            source="provider",
            source_id="invoice",
            value=2,
            provenance_refs=(f"usage:{item.task_id}",),
        )
        for item in tasks[:20]
    )
    metric_slice = template_cost(tasks, usage).slices[0]
    assert metric_slice.value is not None and metric_slice.value.value == 40
    assert metric_slice.coverage.raw_ratio == "20/21"
    assert metric_slice.compatibility["role_prompt_digest"] == f"sha256:{'a' * 64}"
    assert "cost_basis" not in metric_slice.compatibility

