"""Shared settings: every tool reads the same variables as bqchange and dbt."""

from __future__ import annotations

import os
import re
from pathlib import Path

from google.cloud import bigquery

from bqchange.config import Config, load_config

CONFIG_PATH = Path("migrations/bqchange.yml")
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


def environment_config(environment: str) -> Config:
    """bqchange configuration resolved for another environment (e.g. pr_42)."""
    return load_config(
        CONFIG_PATH,
        environ={
            "BQ_ENV": validate_environment(environment),
            "GCP_PROJECT_ID": os.environ.get("GCP_PROJECT_ID", "unset"),
        },
    )


def environment_datasets(environment: str) -> dict[str, str]:
    """Every dataset of an environment, by layer: the layers map plus bqchange's meta."""
    config = environment_config(environment)
    return {**config.layers, "meta": config.meta_dataset}


def dataset_id(project: str, environment: str, layer: str) -> str:
    datasets = environment_datasets(environment)
    if layer not in datasets:
        raise ValueError(f"Unknown layer {layer!r}: declared layers are {sorted(datasets)}")
    return f"{project}.{datasets[layer]}"
