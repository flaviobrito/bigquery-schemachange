"""YAML configuration, rendered with Jinja so values can come from environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jinja2
import yaml


def env_var(name: str, default: str | None = None, environ: Mapping[str, str] | None = None) -> str:
    """Jinja helper available in the config file and in every script."""
    value = (os.environ if environ is None else environ).get(name, default)
    if value is None:
        raise ValueError(f"Environment variable {name} is not set and has no default")
    return value


@dataclass(frozen=True)
class Config:
    project: str
    location: str
    root_folder: Path
    change_history_table: str
    modules_folder: Path | None = None
    create_change_history_table: bool = True
    maximum_bytes_billed: int | None = None
    labels: dict[str, str] = field(default_factory=dict)
    vars: dict[str, Any] = field(default_factory=dict)
    # Logical layer -> dataset of this environment, e.g. {"bronze": "dev_bronze"}.
    layers: dict[str, str] = field(default_factory=dict)
    schema_log_layers: list[str] = field(default_factory=list)
    pr_clone_layers: list[str] = field(default_factory=list)

    @property
    def change_history_dataset(self) -> str:
        return self.change_history_table.rsplit(".", 1)[0]

    @property
    def meta_dataset(self) -> str:
        """Dataset holding bqchange's own tables, without the project."""
        return self.change_history_dataset.split(".", 1)[1]

    @property
    def schema_log_datasets(self) -> dict[str, str]:
        return {layer: self.layers[layer] for layer in self.schema_log_layers}


def load_config(path: Path, environ: Mapping[str, str] | None = None) -> Config:
    """Load the config; environ overrides os.environ (e.g. to resolve another BQ_ENV)."""
    template = jinja2.Template(path.read_text(), undefined=jinja2.StrictUndefined)

    def lookup(name: str, default: str | None = None) -> str:
        return env_var(name, default, {**os.environ, **(environ or {})})

    raw = yaml.safe_load(template.render(env_var=lookup)) or {}
    base = path.parent

    def resolve(folder: str | None) -> Path | None:
        if folder is None:
            return None
        candidate = Path(folder)
        return candidate if candidate.is_absolute() else (base / candidate).resolve()

    layers = {str(k): str(v) for k, v in (raw.get("layers") or {}).items()}
    schema_log_layers = [str(layer) for layer in raw.get("schema-log-layers") or []]
    pr_clone_layers = [str(layer) for layer in raw.get("pr-clone-layers") or []]
    for key, selected in (
        ("schema-log-layers", schema_log_layers),
        ("pr-clone-layers", pr_clone_layers),
    ):
        if unknown := sorted(set(selected) - layers.keys()):
            raise ValueError(f"{key} not declared in layers: {unknown}")

    project = raw["project"]
    history = raw["change-history-table"]
    if history.count(".") == 1:
        history = f"{project}.{history}"

    return Config(
        project=project,
        location=raw.get("location", "US"),
        root_folder=resolve(raw.get("root-folder", "scripts")),
        modules_folder=resolve(raw.get("modules-folder")),
        change_history_table=history,
        create_change_history_table=bool(raw.get("create-change-history-table", True)),
        maximum_bytes_billed=raw.get("maximum-bytes-billed"),
        labels={str(k): str(v) for k, v in (raw.get("labels") or {}).items()},
        vars=raw.get("vars") or {},
        layers=layers,
        schema_log_layers=schema_log_layers,
        pr_clone_layers=pr_clone_layers,
    )
