"""Shared settings: every tool reads the same variables as bqchange and dbt."""

from __future__ import annotations

import os
import re

from google.cloud import bigquery

LAYERS = ("bronze", "silver", "gold", "audit", "meta")
_ENVIRONMENT_PATTERN = re.compile(r"^(dev|prod|pr_\d+)$")


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Environment variable {name} is required")
    return value


def validate_environment(name: str) -> str:
    """Only dev, prod and pr_<number> are valid environment prefixes."""
    if not _ENVIRONMENT_PATTERN.match(name):
        raise ValueError(f"Invalid environment {name!r}: expected dev, prod or pr_<number>")
    return name


def current_environment() -> str:
    return validate_environment(require_env("BQ_ENV"))


def client() -> bigquery.Client:
    """BigQuery client using Application Default Credentials."""
    return bigquery.Client(
        project=require_env("GCP_PROJECT_ID"),
        location=os.environ.get("BQ_LOCATION", "US"),
    )


def dataset_id(project: str, environment: str, layer: str) -> str:
    if layer not in LAYERS:
        raise ValueError(f"Unknown layer {layer!r}")
    return f"{project}.{validate_environment(environment)}_{layer}"
