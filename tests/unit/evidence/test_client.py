from datetime import UTC, datetime

import httpx
import pytest

from wsr_evolution.application import UpstreamContractMismatch, UpstreamUnavailable
from wsr_evolution.evidence.client import EvidenceHttpClient


def task_response(*, revision: str = "1.0.0") -> dict[str, object]:
    return {
        "contract": {"name": "evidence.query", "revision": revision},
        "observation_profile": "2.0.0",
        "read_model_revision": "2.0.0",
        "snapshot": "task-snapshot-a",
        "items": [
            {
                "task_id": "task-a",
                "delivery_id": "delivery-a",
                "manifest_digest": "a" * 64,
                "recorded_at": "2026-08-28T00:59:00.000000Z",
                "provenance": {
                    "accepted_digest": "b" * 64,
                    "profile_version": "2.0.0",
                    "source": {"kind": "EVENT", "event_id": "task-event-a"},
                },
            }
        ],
        "next_cursor": "cursor-next",
    }


@pytest.mark.asyncio
async def test_task_client_sends_normalized_cutoff_and_decodes_exact_provenance() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/evidence/tasks"
        assert dict(request.url.params) == {
            "task_id": "task-a",
            "as_of": "2026-08-28T01:00:00.000000Z",
            "limit": "200",
            "cursor": "cursor-current",
        }
        return httpx.Response(200, json=task_response())

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://evidence.test"
    ) as transport:
        page = await EvidenceHttpClient(transport).resolve_membership(
            task_id="task-a",
            as_of=datetime(2026, 8, 28, 1, tzinfo=UTC),
            limit=200,
            cursor="cursor-current",
        )

    assert page.route_snapshot == "task-snapshot-a"
    assert page.next_cursor == "cursor-next"
    assert page.memberships[0].source_identity == "event:task-event-a"
    assert page.memberships[0].accepted_digest == "b" * 64


@pytest.mark.asyncio
async def test_task_client_rejects_unknown_evidence_coordinates() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=task_response(revision="1.1.0"))

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://evidence.test"
    ) as transport:
        with pytest.raises(UpstreamContractMismatch):
            await EvidenceHttpClient(transport).resolve_membership(
                task_id="task-a",
                as_of=datetime(2026, 8, 28, 1, tzinfo=UTC),
                limit=200,
                cursor=None,
            )


@pytest.mark.asyncio
async def test_task_client_maps_retryable_query_failure_without_fabricating_a_page() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json={"error": {"code": "QUERY_UNAVAILABLE", "message": "try later"}},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://evidence.test"
    ) as transport:
        with pytest.raises(UpstreamUnavailable):
            await EvidenceHttpClient(transport).resolve_membership(
                task_id="task-a",
                as_of=datetime(2026, 8, 28, 1, tzinfo=UTC),
                limit=200,
                cursor=None,
            )
