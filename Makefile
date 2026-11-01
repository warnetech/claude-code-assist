.PHONY: help install test lint typecheck check examples clean

PY := packages/python
TS := packages/typescript
AI := packages/aicli

help:                       ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:                    ## Install all packages with dev dependencies
	cd $(PY) && pip install -e ".[dev]"
	cd $(TS) && npm install --no-audit --no-fund
	cd $(AI) && pip install -e ".[dev]"

test:                       ## Run every test in every package
	cd $(PY) && pytest tests -q && pytest --doctest-modules src/llmforge -q
	cd $(TS) && npm test
	cd $(AI) && pytest -q

lint:                       ## Lint Python (llmforge and aicli)
	cd $(PY) && ruff check src tests
	cd $(AI) && ruff check src tests

typecheck:                  ## Typecheck TypeScript
	cd $(TS) && npm run typecheck

examples:                   ## Run the examples offline, with no credentials
	python examples/01_assured_change.py
	python examples/02_gate_catches_a_drive_by.py

check: lint typecheck test examples   ## Everything CI runs

clean:
	rm -rf $(PY)/.pytest_cache $(PY)/.ruff_cache $(AI)/.pytest_cache $(AI)/.ruff_cache $(TS)/dist .llmforge
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
