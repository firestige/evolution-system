#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

TOP_LEVEL_KEYS = {
    "authority",
    "candidateTag",
    "commit",
    "image",
    "ociDigest",
    "platforms",
    "provenance",
    "publisherRevision",
    "sbom",
    "schemaVersion",
    "source",
    "version",
}
COMMIT = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
VERSION = re.compile(r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$")
PROVENANCE_PLATFORMS = {"linux/amd64", "linux/arm64"}
PROVENANCE_BUILD_TYPE = (
    "https://github.com/moby/buildkit/blob/master/docs/attestations/slsa-definitions.md"
)
PROVENANCE_SOURCE = "https://github.com/firestige/workflow-self-recursive"


class QualificationError(RuntimeError):
    pass


def validate(
    value: dict[str, Any], *, candidate_tag: str, final_tag: str, commit: str
) -> dict[str, str]:
    authority = value.get("authority")
    provenance = value.get("provenance")
    sbom = value.get("sbom")
    digest = value.get("ociDigest")
    if (
        set(value) != TOP_LEVEL_KEYS
        or value.get("schemaVersion") != "wsr.evolution-image-qualification@1.0.0"
        or VERSION.fullmatch(final_tag) is None
        or value.get("version") != final_tag
        or re.fullmatch(re.escape(final_tag) + r"-rc\.[1-9]\d*", candidate_tag) is None
        or value.get("candidateTag") != candidate_tag
        or COMMIT.fullmatch(commit) is None
        or value.get("commit") != commit
        or value.get("source") != "https://github.com/firestige/evolution-system"
        or value.get("platforms") != ["linux/amd64", "linux/arm64"]
        or provenance != {"mode": "max", "status": "PASS"}
        or sbom != {"requested": True}
        or not isinstance(authority, dict)
        or set(authority) != {"repository", "revision"}
        or authority.get("repository") != "firestige/workflow-self-recursive"
        or not isinstance(authority.get("revision"), str)
        or COMMIT.fullmatch(authority["revision"]) is None
        or not isinstance(value.get("publisherRevision"), str)
        or COMMIT.fullmatch(value["publisherRevision"]) is None
        or not isinstance(digest, str)
        or DIGEST.fullmatch(digest) is None
        or value.get("image") != f"ghcr.io/firestige/wsr-evolution:{candidate_tag}@{digest}"
    ):
        raise QualificationError("EVOLUTION_IMAGE_QUALIFICATION_INVALID")
    return {"authorityRevision": authority["revision"], "ociDigest": digest, "status": "PASS"}


def validate_provenance(
    value: dict[str, Any], *, authority_revision: str, product_commit: str
) -> None:
    try:
        if set(value) != PROVENANCE_PLATFORMS:
            raise QualificationError("EVOLUTION_IMAGE_PROVENANCE_INVALID")
        for platform in sorted(PROVENANCE_PLATFORMS):
            build = value[platform]["SLSA"]["buildDefinition"]
            arguments = build["externalParameters"]["request"]["root"]["request"]["args"]
            if (
                build["buildType"] != PROVENANCE_BUILD_TYPE
                or arguments["vcs:source"] != PROVENANCE_SOURCE
                or arguments["vcs:revision"] != authority_revision
                or arguments["build-arg:WSR_RELEASE_REVISION"] != product_commit
            ):
                raise QualificationError("EVOLUTION_IMAGE_PROVENANCE_INVALID")
    except (KeyError, TypeError) as error:
        raise QualificationError("EVOLUTION_IMAGE_PROVENANCE_INVALID") from error


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("qualification", type=Path)
    parser.add_argument("--candidate-tag", required=True)
    parser.add_argument("--final-tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--provenance", type=Path)
    args = parser.parse_args()
    try:
        value = json.loads(args.qualification.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise QualificationError("EVOLUTION_IMAGE_QUALIFICATION_INVALID")
        result = validate(
            value,
            candidate_tag=args.candidate_tag,
            final_tag=args.final_tag,
            commit=args.commit,
        )
        if args.provenance is not None:
            provenance = json.loads(args.provenance.read_text(encoding="utf-8"))
            if not isinstance(provenance, dict):
                raise QualificationError("EVOLUTION_IMAGE_PROVENANCE_INVALID")
            validate_provenance(
                provenance,
                authority_revision=result["authorityRevision"],
                product_commit=args.commit,
            )
    except (OSError, json.JSONDecodeError, QualificationError) as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
