import importlib

from wsr_evolution.calculators.registry import CALCULATOR_SLOTS
from wsr_evolution.catalog import CATALOG_COORDINATES

EXPECTED_COORDINATES = (
    "role-template-rework-rate@1.0.0",
    "role-template-trajectory-partial-cost@1.0.0",
    "role-model-task-outcome-rate@1.0.0",
    "packet-rework-rate@1.0.0",
    "operational-latency-ms@1.0.0",
    "trajectory-partial-cost@1.0.0",
    "task-cohort-comparison-eligibility@1.0.0",
    "delivery-stage-reach@1.0.0",
    "delivery-terminal-outcome-rate@1.0.0",
    "delivery-cycle-time-ms@1.0.0",
    "operational-token-usage@1.0.0",
    "operational-attributable-cost@1.0.0",
    "operational-usage-availability@1.0.0",
    "direct-evidence-basis-rate@1.0.0",
)


def test_registry_has_exact_published_catalog_coordinates() -> None:
    assert CATALOG_COORDINATES == EXPECTED_COORDINATES
    assert tuple(CALCULATOR_SLOTS) == EXPECTED_COORDINATES
    assert len(set(CALCULATOR_SLOTS)) == 14


def test_every_coordinate_has_one_importable_module_slot() -> None:
    modules = []
    for coordinate, slot in CALCULATOR_SLOTS.items():
        module = importlib.import_module(slot.module)
        modules.append(slot.module)
        assert slot == module.SLOT
        assert slot.coordinate == coordinate

    assert len(set(modules)) == 14


def test_slots_expose_no_runtime_engine_or_fallback() -> None:
    for slot in CALCULATOR_SLOTS.values():
        assert not hasattr(slot, "engine")
        assert not hasattr(slot, "fallback")
        assert not hasattr(slot, "selector")
