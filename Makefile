PY := uv run python
SEASON ?= 2025-26

.PHONY: all setup data possessions validate test0 stabilize test lint clean-processed

all: data possessions validate test0 stabilize

setup:
	uv sync

data:
	$(PY) -m src.ingest --seasons $(SEASON)

possessions:
	$(PY) -m src.possessions --season $(SEASON)

validate:
	$(PY) -m src.validate --season $(SEASON)

test0:
	$(PY) -m src.analysis.test0_baseline

stabilize:
	$(PY) -m src.stabilize

test:
	uv run pytest -q

lint:
	uv run ruff check src tests

# Derived data only; data/raw is the cache and is never deleted by make.
clean-processed:
	rm -rf data/processed/* reports/results reports/figures
