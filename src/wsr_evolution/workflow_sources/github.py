from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from wsr_evolution.workflow_sources.resolution import (
    SourceFailure,
    WorkflowCandidate,
    WorkflowSourceConfig,
)

MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_RELEASE_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_DESCRIPTOR_BYTES = 64 * 1024
PAGE_SIZE = 100
MAX_RELEASE_PAGES = 10


class WorkflowArchiveValidator(Protocol):
    async def validate(
        self,
        *,
        archive: bytes,
        archive_digest: str,
        package_name: str,
        exact_version: str,
    ) -> WorkflowCandidate: ...


@dataclass(frozen=True, slots=True)
class _Asset:
    name: str
    url: str


@dataclass(frozen=True, slots=True)
class _Release:
    tag: str
    draft: bool
    assets: tuple[_Asset, ...]


@dataclass(frozen=True, slots=True)
class _Descriptor:
    package_digest: str
    archive_digest: str
    archive_bytes: int


def _strict_json(body: bytes) -> Any:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON member")
            result[key] = value
        return result

    return json.loads(body, object_pairs_hook=object_pairs)


def _https_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return None
    return value


def _release(value: object) -> _Release | None:
    if not isinstance(value, dict):
        return None
    tag = value.get("tag_name")
    draft = value.get("draft")
    assets = value.get("assets")
    if not isinstance(tag, str) or not isinstance(draft, bool) or not isinstance(assets, list):
        return None
    parsed_assets: list[_Asset] = []
    for item in assets:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            return None
        url = _https_url(item.get("browser_download_url"))
        if url is None:
            return None
        parsed_assets.append(_Asset(item["name"], url))
    return _Release(tag=tag, draft=draft, assets=tuple(parsed_assets))


def _one_asset(assets: tuple[_Asset, ...], name: str) -> _Asset | None:
    matches = tuple(item for item in assets if item.name == name)
    return matches[0] if len(matches) == 1 else None


def _object(value: object, keys: set[str]) -> dict[str, Any] | None:
    return value if isinstance(value, dict) and set(value) == keys else None


def _descriptor(
    body: bytes,
    *,
    package_name: str,
    exact_version: str,
    archive_name: str,
    checksum_name: str,
) -> _Descriptor | None:
    try:
        value = _strict_json(body)
    except (ValueError, UnicodeError, json.JSONDecodeError):
        return None
    root = _object(
        value,
        {"schemaVersion", "revision", "tag", "package", "archive", "checksum"},
    )
    if root is None:
        return None
    package = _object(root["package"], {"name", "version", "digest"})
    archive = _object(root["archive"], {"name", "sha256", "bytes"})
    checksum = _object(root["checksum"], {"name"})

    def digest_pattern(item: object) -> bool:
        return (
            isinstance(item, str)
            and len(item) == 71
            and item.startswith("sha256:")
            and all(character in "0123456789abcdef" for character in item[7:])
        )

    valid = (
        root["schemaVersion"] == "workflow-package.package-release@1.0.0"
        and root["tag"] == f"workflow-package/{package_name}/v{exact_version}"
        and isinstance(root["revision"], str)
        and len(root["revision"]) == 40
        and all(character in "0123456789abcdef" for character in root["revision"])
        and package is not None
        and package["name"] == package_name
        and package["version"] == exact_version
        and digest_pattern(package["digest"])
        and archive is not None
        and archive["name"] == archive_name
        and digest_pattern(archive["sha256"])
        and isinstance(archive["bytes"], int)
        and not isinstance(archive["bytes"], bool)
        and 1 <= archive["bytes"] <= MAX_ARCHIVE_BYTES
        and checksum is not None
        and checksum["name"] == checksum_name
    )
    if not valid or package is None or archive is None:
        return None
    return _Descriptor(package["digest"], archive["sha256"], archive["bytes"])


class GitHubWorkflowSource:
    def __init__(
        self,
        configuration: WorkflowSourceConfig,
        transport: httpx.AsyncClient,
        validator: WorkflowArchiveValidator,
    ) -> None:
        self._configuration = configuration
        self._transport = transport
        self._validator = validator

    async def _bytes(self, url: str, *, limit: int, timeout_seconds: float) -> bytes:
        try:
            async with self._transport.stream("GET", url, timeout=timeout_seconds) as response:
                if not 200 <= response.status_code < 300:
                    raise SourceFailure("SOURCE_UNAVAILABLE")
                chunks: list[bytes] = []
                length = 0
                async for chunk in response.aiter_bytes():
                    length += len(chunk)
                    if length > limit:
                        raise ValueError("bounded response exceeded")
                    chunks.append(chunk)
                return b"".join(chunks)
        except SourceFailure:
            raise
        except httpx.HTTPError as error:
            raise SourceFailure("SOURCE_UNAVAILABLE") from error

    async def fetch_exact(
        self, *, package_name: str, exact_version: str, timeout_seconds: float
    ) -> WorkflowCandidate:
        releases: list[_Release] = []
        base = f"https://api.github.com/repos/{self._configuration.repository}/releases"
        for page in range(1, MAX_RELEASE_PAGES + 1):
            try:
                body = await self._bytes(
                    f"{base}?per_page={PAGE_SIZE}&page={page}",
                    limit=MAX_RELEASE_RESPONSE_BYTES,
                    timeout_seconds=timeout_seconds,
                )
                values = _strict_json(body)
            except SourceFailure:
                raise
            except (ValueError, UnicodeError, json.JSONDecodeError) as error:
                raise SourceFailure("INVALID_DESCRIPTOR") from error
            if not isinstance(values, list):
                raise SourceFailure("INVALID_DESCRIPTOR")
            parsed = tuple(_release(value) for value in values)
            if any(value is None for value in parsed):
                raise SourceFailure("INVALID_DESCRIPTOR")
            releases.extend(value for value in parsed if value is not None and not value.draft)
            if len(values) < PAGE_SIZE:
                break
            if page == MAX_RELEASE_PAGES:
                raise SourceFailure("SOURCE_UNAVAILABLE")

        tag = f"workflow-package/{package_name}/v{exact_version}"
        matches = tuple(item for item in releases if item.tag == tag)
        if not matches:
            raise SourceFailure("NOT_FOUND")
        if len(matches) != 1 or len(matches[0].assets) != 3:
            raise SourceFailure("INVALID_DESCRIPTOR")
        selected = matches[0]
        archive_name = f"workflow-package-{package_name}-{exact_version}.tar.gz"
        descriptor_name = f"workflow-package-{package_name}-{exact_version}.json"
        checksum_name = f"{archive_name}.sha256"
        archive_asset = _one_asset(selected.assets, archive_name)
        descriptor_asset = _one_asset(selected.assets, descriptor_name)
        checksum_asset = _one_asset(selected.assets, checksum_name)
        if archive_asset is None or descriptor_asset is None or checksum_asset is None:
            raise SourceFailure("INVALID_DESCRIPTOR")
        try:
            descriptor_body = await self._bytes(
                descriptor_asset.url,
                limit=MAX_DESCRIPTOR_BYTES,
                timeout_seconds=timeout_seconds,
            )
        except ValueError as error:
            raise SourceFailure("INVALID_DESCRIPTOR") from error
        metadata = _descriptor(
            descriptor_body,
            package_name=package_name,
            exact_version=exact_version,
            archive_name=archive_name,
            checksum_name=checksum_name,
        )
        if metadata is None:
            raise SourceFailure("INVALID_DESCRIPTOR")
        try:
            checksum = await self._bytes(
                checksum_asset.url, limit=1024, timeout_seconds=timeout_seconds
            )
        except ValueError as error:
            raise SourceFailure("CHECKSUM_MISMATCH") from error
        expected_checksum = f"{metadata.archive_digest[7:]}  {archive_name}\n".encode()
        if checksum != expected_checksum:
            raise SourceFailure("CHECKSUM_MISMATCH")
        try:
            archive = await self._bytes(
                archive_asset.url,
                limit=MAX_ARCHIVE_BYTES,
                timeout_seconds=timeout_seconds,
            )
        except ValueError as error:
            raise SourceFailure("INVALID_ARCHIVE") from error
        actual_digest = "sha256:" + sha256(archive).hexdigest()
        if (
            not archive
            or len(archive) != metadata.archive_bytes
            or actual_digest != metadata.archive_digest
        ):
            raise SourceFailure("INVALID_ARCHIVE")
        try:
            candidate = await self._validator.validate(
                archive=archive,
                archive_digest=actual_digest,
                package_name=package_name,
                exact_version=exact_version,
            )
        except SourceFailure:
            raise
        except Exception as error:
            raise SourceFailure("INVALID_WORKFLOW") from error
        if candidate.package_digest != metadata.package_digest:
            raise SourceFailure("INVALID_DESCRIPTOR")
        return candidate
