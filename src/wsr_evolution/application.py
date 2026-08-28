from typing import Protocol

from wsr_evolution.api.models import ComputeRequest, ComputeResponse


class UpstreamUnavailable(RuntimeError):
    """A retryable Evidence transport or availability failure."""


class UpstreamContractMismatch(RuntimeError):
    """A non-retryable incompatible Evidence response."""


class ComputeService(Protocol):
    async def compute(self, request: ComputeRequest) -> ComputeResponse: ...
