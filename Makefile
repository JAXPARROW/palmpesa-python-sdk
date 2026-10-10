PY ?= .venv/bin/python

.PHONY: install test cov lint format typecheck check build live clean

install:
	$(PY) -m pip install -e ".[dev]"

test:
	$(PY) -m pytest -q

cov:
	$(PY) -m pytest -q --cov=palmpesa --cov-report=term-missing

lint:
	$(PY) -m ruff check src tests examples
	$(PY) -m black --check src tests examples

format:
	$(PY) -m ruff check --fix src tests examples
	$(PY) -m black src tests examples

typecheck:
	$(PY) -m mypy

check: lint typecheck cov

build: clean
	$(PY) -m build

# Safe live checks (no payment). Requires PALMPESA_API_TOKEN.
live:
	$(PY) examples/live_check.py

clean:
	rm -rf build dist src/*.egg-info .pytest_cache .mypy_cache .coverage htmlcov
