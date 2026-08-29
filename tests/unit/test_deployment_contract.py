from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_source_image_bundles_python_service_and_exact_workflow_checker() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert "system-contracts/workflow-dsl-2-candidate" in dockerfile
    assert "evolution-system/uv.lock" in dockerfile
    assert 'CMD ["python", "-m", "wsr_evolution"]' in dockerfile
    assert "EXPOSE 8000" in dockerfile


def test_runtime_dependencies_have_no_database_driver() -> None:
    project = (ROOT / "pyproject.toml").read_text().lower()

    for forbidden in ("psycopg", "asyncpg", "sqlalchemy"):
        assert forbidden not in project


def test_release_image_has_exact_bases_identity_and_multi_platform_provenance() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()
    workflow = (ROOT / ".github" / "workflows" / "release-candidate.yml").read_text()

    assert all(
        line.count("@sha256:") == 1 for line in dockerfile.splitlines() if line.startswith("FROM ")
    )
    assert "org.opencontainers.image.source" in dockerfile
    assert "org.opencontainers.image.revision" in dockerfile
    assert "permissions:\n  contents: read\n  packages: write" in workflow
    assert "--platform linux/amd64,linux/arm64" in workflow
    assert "--provenance=mode=max" in workflow
    assert "--sbom=true" in workflow
    assert "docker buildx imagetools inspect" in workflow
    assert 'index("amd64") != null and index("arm64") != null' in workflow
    assert ".config.Labels" not in workflow


def test_release_image_builds_from_exact_superproject_authority() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release-candidate.yml").read_text()

    assert "repository: firestige/workflow-self-recursive" in workflow
    assert "submodules: recursive" in workflow
    assert "git -C evolution-system rev-parse HEAD" in workflow
    assert 'test "$(git -C evolution-system rev-parse HEAD)" = "$PRODUCT_COMMIT"' in workflow
    assert "--file evolution-system/Dockerfile" in workflow


def test_reusable_release_does_not_confuse_caller_sha_with_product_commit() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release-candidate.yml").read_text()

    assert "product_commit:" in workflow
    assert "PRODUCT_COMMIT: ${{ inputs.product_commit }}" in workflow
    assert "PRODUCT_COMMIT: ${{ github.sha }}" not in workflow


def test_candidate_persists_exact_qualification_for_later_promotion() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release-candidate.yml").read_text()

    assert "release-qualification.json" in workflow
    assert 'gh release create "$CANDIDATE_TAG"' in workflow
    assert "--prerelease" in workflow
    assert "actions/create-github-app-token@" in workflow
    assert '"ociDigest":digest' in workflow
    assert '"platforms":["linux/amd64","linux/arm64"]' in workflow
    assert '"provenance":{"mode":"max","status":"PASS"}' in workflow
    assert "evolution-system/release/validate_image_qualification.py" in workflow
    assert '--provenance "$RUNNER_TEMP/provenance.json"' in workflow
    assert '--image-config "$RUNNER_TEMP/qualified-image-config.json"' in workflow
    assert ".SLSA.buildDefinition" not in workflow


def test_stable_promotion_retags_only_the_exact_qualified_candidate_digest() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release-promote.yml").read_text()

    assert "release-qualification.json" in workflow
    assert "docker buildx build" not in workflow
    assert ":latest" not in workflow
    assert 'CANDIDATE_DIGEST="$(jq -er .ociDigest' in workflow
    assert 'test "$REMOTE_DIGEST" = "$CANDIDATE_DIGEST"' in workflow
    assert ".config.Labels" not in workflow
    assert 'index("amd64") != null and index("arm64") != null' in workflow
    assert "--format '{{json .Provenance}}'" in workflow
    assert "docker buildx imagetools create" in workflow
    assert 'test "$STABLE_DIGEST" = "$CANDIDATE_DIGEST"' in workflow
    assert "stable-qualification.json" in workflow
    assert "actions/create-github-app-token@" in workflow
    assert "release/validate_image_qualification.py" in workflow
    assert '--provenance "$RUNNER_TEMP/candidate-provenance.json"' in workflow
    assert '--image-config "$RUNNER_TEMP/candidate-image.json"' in workflow
    assert ".SLSA.buildDefinition" not in workflow
