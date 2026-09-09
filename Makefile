# Developer shortcuts. Assumes a virtualenv at .venv (see README setup).
PY := .venv/bin/python
PIP := $(PY) -m pip

.PHONY: help venv install test lint format check listener run demo clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

venv:  ## Create the virtualenv
	python3 -m venv .venv

install:  ## Install runtime + dev dependencies (editable)
	$(PIP) install -U pip
	$(PIP) install -e ".[dev]"

test:  ## Run the test suite
	$(PY) -m pytest

lint:  ## Lint with ruff
	$(PY) -m ruff check src tests tools

format:  ## Auto-format with black + ruff --fix
	$(PY) -m black src tests tools
	$(PY) -m ruff check --fix src tests tools

check: lint test  ## Lint then test (what CI would run)
	$(PY) -m black --check src tests tools

listener:  ## Run the local CoT listener (TCP :4242 + folium map)
	$(PY) tools/cot_listener.py --tcp 127.0.0.1:4242 --map cot_map.html

run:  ## Run the bot (reads .env)
	$(PY) -m signal_atak

clean:  ## Remove caches and local artifacts
	rm -rf .pytest_cache .ruff_cache **/__pycache__ src/*.egg-info cot_map.html
