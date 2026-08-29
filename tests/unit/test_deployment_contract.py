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
    assert 'config.Labels["org.opencontainers.image.source"]' in workflow
    assert 'config.Labels["org.opencontainers.image.revision"]' in workflow


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
