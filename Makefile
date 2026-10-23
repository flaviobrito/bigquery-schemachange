# Local developer workflow. Every target mirrors a CI step.
SHELL := /bin/bash
ifneq (,$(wildcard .env))
include .env
export
endif

DBT := uv run dbt
DBT_ARGS := --project-dir dbt --profiles-dir dbt
# Placeholders so parsing works without a project or credentials (nothing is called).
OFFLINE_ENV := GCP_PROJECT_ID=$${GCP_PROJECT_ID:-offline-project} BQ_ENV=$${BQ_ENV:-dev}

.DEFAULT_GOAL := help

.PHONY: help
help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: ## Install Python and dbt dependencies
	uv sync --frozen
	$(DBT) deps $(DBT_ARGS)
	uv run pre-commit install

.PHONY: lint
lint: ## Ruff, sqlfluff and dbt parse
	uv run ruff check .
	uv run ruff format --check .
	uv run sqlfluff lint dbt/models dbt/tests
	$(OFFLINE_ENV) $(DBT) parse $(DBT_ARGS)

.PHONY: test-python
test-python: ## Unit tests for bqchange and ops tooling
	uv run pytest

.PHONY: migrate-plan
migrate-plan: ## bqchange dry run against $BQ_ENV
	uv run bqchange deploy --dry-run

.PHONY: migrate
migrate: ## Apply pending migrations to $BQ_ENV and record schema changes
	uv run bqchange record-schema --source manual
	uv run bqchange deploy
	uv run bqchange record-schema --source migration

.PHONY: sample-data
sample-data: ## Generate and load synthetic data into BRONZE
	uv run python -m ops.generate_sample_data --output-dir data/sample
	uv run python -m ops.load_sample_data --input-dir data/sample

.PHONY: build
build: ## dbt build (models, data tests, unit tests) and record schema changes
	$(DBT) build $(DBT_ARGS)
	uv run bqchange record-schema --source dbt

.PHONY: freshness
freshness: ## dbt source freshness
	$(DBT) source freshness $(DBT_ARGS)

.PHONY: drift
drift: ## Refresh schema audit and report drift
	$(DBT) run $(DBT_ARGS) --select tag:schema_audit
	uv run python -m ops.check_schema_drift

.PHONY: docs
docs: ## Generate and serve dbt docs locally
	$(DBT) docs generate $(DBT_ARGS)
	$(DBT) docs serve $(DBT_ARGS)
