from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient, Response

from wsr_evolution.api.models import (
    CatalogBinding,
    Coverage,
    EvaluationSelection,
    EvidenceBinding,
    MetricResult,
    MetricSlice,
    ResolvedEvaluationContext,
    SideResult,
    SingleRequest,
    SingleResponse,
    TaskPopulationEntry,
)
from wsr_evolution.app import create_app
from wsr_evolution.application import UpstreamContractMismatch, UpstreamUnavailable
from wsr_evolution.catalog import CATALOG_COORDINATES


def fixed_response() -> SingleResponse:
    context = ResolvedEvaluationContext(
        context_version=1,
        selection=EvaluationSelection(selection_version=1, task_ids=("task-a",)),
        as_of=datetime(2026, 8, 28, 1, 0, tzinfo=UTC),
        resolved_at=datetime(2026, 8, 28, 1, 1, tzinfo=UTC),
        task_population=(
            TaskPopulationEntry(
                task_id="task-a",
                memberships=(),
                exclusions=("UNDEFINED_TASK_MEMBERSHIP",),
            ),
        ),
        catalog=CatalogBinding(
            catalog_id="agentops.evaluation.metric-catalog",
            version="1.0.0",
            semantic_digest="6dbb4375507a3a2eebbe5e86bb6f0a40ebf811790f55ee841b15c6942e1f159d",
            observation_profile="1.0.0",
        ),
        evidence_bindings=(
            EvidenceBinding(
                route="/v1/evidence/tasks",
                canonical_filter={
                    "task_id": "task-a",
                    "as_of": "2026-08-28T01:00:00.000000Z",
                },
                contract_revision="1.0.0",
                observation_profile="2.0.0",
                read_model_revision="2.0.0",
                route_snapshot="task-snapshot-a",
                completion_state="COMPLETE",
            ),
        ),
        input_refs=(),
        population_state="OPEN",
    )
    results = tuple(
        MetricResult(
            metric_id=coordinate.rsplit("@", 1)[0],
            metric_version="1.0.0",
            slices=(
                MetricSlice(
                    slice_key={},
                    state="UNAVAILABLE",
                    withholding_reason="MISSING_INPUT",
                    coverage=Coverage(
                        numerator=0,
                        denominator=0,
                        raw_ratio=None,
                        state="NO_POPULATION",
                        alert=None,
                    ),
                ),
            ),
        )
        for coordinate in CATALOG_COORDINATES
    )
    return SingleResponse(
        api_version=1,
        mode="SINGLE",
        result=SideResult(tag="SIDE_RESULT", receipt=context, metric_results=results),
    )


class FixedService:
    async def compute(self, request: SingleRequest) -> SingleResponse:
        assert request.selection.task_ids == ("task-a",)
        return fixed_response()


class UnavailableService:
    async def compute(self, request: SingleRequest) -> SingleResponse:
        raise UpstreamUnavailable("Evidence timed out")


class MismatchService:
    async def compute(self, request: SingleRequest) -> SingleResponse:
        raise UpstreamContractMismatch("Evidence returned an unknown revision")


async def post(service: object, payload: dict[str, object]) -> Response:
    async with AsyncClient(
        transport=ASGITransport(app=create_app(service)),
        base_url="http://evolution.test",
    ) as client:
        return await client.post("/api/evolution/v1/evaluations:compute", json=payload)


@pytest.mark.asyncio
async def test_compute_returns_exact_response_without_creating_resource() -> None:
    payload = {
        "api_version": 1,
        "mode": "SINGLE",
        "selection": {"selection_version": 1, "task_ids": ["task-a"]},
    }

    first = await post(FixedService(), payload)
    second = await post(FixedService(), payload)

    assert first.status_code == 200
    assert first.json() == second.json()
    assert len(first.json()["result"]["metric_results"]) == 14
    assert "location" not in first.headers


@pytest.mark.asyncio
async def test_request_validation_is_bounded_400() -> None:
    response = await post(
        FixedService(),
        {
            "api_version": 1,
            "mode": "SINGLE",
            "selection": {
                "selection_version": 1,
                "task_ids": ["task-a"],
                "display_name": "forbidden",
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert response.json()["error"]["retryable"] is False
    assert len(response.json()["error"]["details"]) <= 16


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("service", "status", "code", "retryable"),
    [
        (UnavailableService(), 503, "UPSTREAM_UNAVAILABLE", True),
        (MismatchService(), 502, "UPSTREAM_INCOMPATIBLE", False),
    ],
)
async def test_upstream_failures_never_become_metric_unavailable(
    service: object,
    status: int,
    code: str,
    retryable: bool,
) -> None:
    response = await post(
        service,
        {
            "api_version": 1,
            "mode": "SINGLE",
            "selection": {"selection_version": 1, "task_ids": ["task-a"]},
        },
    )

    assert response.status_code == status
    assert response.json() == {
        "error": {
            "code": code,
            "retryable": retryable,
            "detail": response.json()["error"]["detail"],
        }
    }
    assert "result" not in response.json()
