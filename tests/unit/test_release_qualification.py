from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).parents[2]
VALIDATOR = ROOT / "release" / "validate_image_qualification.py"
COMMIT = "a" * 40
AUTHORITY = "b" * 40
PUBLISHER = "c" * 40
DIGEST = "sha256:" + "d" * 64


def qualification() -> dict[str, object]:
    return {
        "schemaVersion": "wsr.evolution-image-qualification@1.0.0",
        "candidateTag": "0.1.0-rc.1",
        "version": "0.1.0",
        "commit": COMMIT,
        "authority": {
            "repository": "firestige/workflow-self-recursive",
            "revision": AUTHORITY,
        },
        "publisherRevision": PUBLISHER,
        "image": f"ghcr.io/firestige/wsr-evolution:0.1.0-rc.1@{DIGEST}",
        "ociDigest": DIGEST,
        "source": "https://github.com/firestige/evolution-system",
        "platforms": ["linux/amd64", "linux/arm64"],
        "provenance": {"mode": "max", "status": "PASS"},
        "sbom": {"requested": True},
    }


def invoke(tmp_path: Path, value: dict[str, object]) -> subprocess.CompletedProcess[str]:
    source = tmp_path / "release-qualification.json"
    source.write_text(json.dumps(value), encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            str(source),
            "--candidate-tag",
            "0.1.0-rc.1",
            "--final-tag",
            "0.1.0",
            "--commit",
            COMMIT,
        ],
        capture_output=True,
        text=True,
    )


def test_exact_candidate_qualification_is_accepted(tmp_path: Path) -> None:
    completed = invoke(tmp_path, qualification())

    assert completed.returncode == 0
    assert json.loads(completed.stdout) == {
        "authorityRevision": AUTHORITY,
        "ociDigest": DIGEST,
        "status": "PASS",
    }


def test_candidate_qualification_rejects_any_open_or_mutable_input(tmp_path: Path) -> None:
    mutations: dict[str, Callable[[dict[str, object]], None]] = {
        "unknown-key": lambda value: value.update({"extra": True}),
        "mutable-image": lambda value: value.update(
            {"image": "ghcr.io/firestige/wsr-evolution:latest"}
        ),
        "wrong-platforms": lambda value: value.update({"platforms": ["linux/amd64"]}),
        "unqualified-provenance": lambda value: value.update(
            {"provenance": {"mode": "min", "status": "PASS"}}
        ),
        "wrong-product": lambda value: value.update({"commit": "e" * 40}),
    }
    for name, mutate in mutations.items():
        value = qualification()
        mutate(value)
        completed = invoke(tmp_path, value)
        assert completed.returncode != 0, name
