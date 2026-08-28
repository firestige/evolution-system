PYTHON_VERSION ?= 3.14
UV_RUN := uv run --python $(PYTHON_VERSION)

.PHONY: sync format lint unit build check

sync:
	uv sync --locked --python $(PYTHON_VERSION)

format:
	$(UV_RUN) ruff format .

lint:
	$(UV_RUN) ruff format --check .
	$(UV_RUN) ruff check .
	$(UV_RUN) mypy src tests

unit:
	$(UV_RUN) pytest -q tests/unit

build:
	uv build --python $(PYTHON_VERSION)

check: lint unit build
