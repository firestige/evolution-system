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
