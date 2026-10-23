"""YAML configuration, rendered with Jinja so values can come from environment variables."""

from __future__ import annotations

import json
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
    # Executables CLI migration scripts (.cli.yml) may run.
    cli_allowed_commands: list[str] = field(default_factory=lambda: ["bq", "gcloud", "gsutil"])

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

    @property
    def secrets(self) -> set[str]:
        from bqchange.secrets import collect_secrets

        return collect_secrets(self.vars)

    @property
    def variables(self) -> dict[str, Any]:
        """Everything available to scripts."""
        return {
            "project": self.project,
            "location": self.location,
            "layers": self.layers,
            **self.vars,
        }


# CLI flag / environment variable / YAML key, in this order of precedence.
OVERRIDABLE = {
    "project": "BQCHANGE_PROJECT",
    "location": "BQCHANGE_LOCATION",
    "root-folder": "BQCHANGE_ROOT_FOLDER",
    "modules-folder": "BQCHANGE_MODULES_FOLDER",
    "change-history-table": "BQCHANGE_CHANGE_HISTORY_TABLE",
    "maximum-bytes-billed": "BQCHANGE_MAXIMUM_BYTES_BILLED",
}


def load_config(
    path: Path,
    environ: Mapping[str, str] | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> Config:
    """Load the configuration.

    Precedence: overrides (CLI flags) > BQCHANGE_* environment variables > YAML.
    environ overrides os.environ (e.g. to resolve another BQ_ENV). The YAML file
    is optional when the required values come from flags or the environment.
    """
    env = {**os.environ, **(environ or {})}

    def lookup(name: str, default: str | None = None) -> str:
        return env_var(name, default, env)

    raw: dict[str, Any] = {}
    if path.is_file():
        template = jinja2.Template(path.read_text(), undefined=jinja2.StrictUndefined)
        raw = yaml.safe_load(template.render(env_var=lookup)) or {}
    for key, variable in OVERRIDABLE.items():
        if env.get(variable):
            raw[key] = env[variable]
    raw["vars"] = {**(raw.get("vars") or {}), **json.loads(env.get("BQCHANGE_VARS") or "{}")}
    for key, value in (overrides or {}).items():
        if value is None:
            continue
        if key == "vars":
            raw["vars"] = {**raw["vars"], **value}
        else:
            raw[key] = value
    missing = [key for key in ("project", "change-history-table") if not raw.get(key)]
    if missing:
        raise ValueError(
            f"Missing configuration: {missing}. Set them in {path}, with CLI flags "
            f"or with BQCHANGE_* environment variables."
        )
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
        maximum_bytes_billed=(
            int(raw["maximum-bytes-billed"]) if raw.get("maximum-bytes-billed") else None
        ),
        labels={str(k): str(v) for k, v in (raw.get("labels") or {}).items()},
        vars=raw.get("vars") or {},
        layers=layers,
        schema_log_layers=schema_log_layers,
        pr_clone_layers=pr_clone_layers,
        cli_allowed_commands=[
            str(c) for c in raw.get("cli-allowed-commands") or ["bq", "gcloud", "gsutil"]
        ],
    )
