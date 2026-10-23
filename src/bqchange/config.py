"""YAML configuration, rendered with Jinja so values can come from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jinja2
import yaml


def env_var(name: str, default: str | None = None) -> str:
    """Jinja helper available in the config file and in every script."""
    value = os.environ.get(name, default)
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
    schema_log_datasets: list[str] = field(default_factory=list)

    @property
    def change_history_dataset(self) -> str:
        return self.change_history_table.rsplit(".", 1)[0]


def load_config(path: Path) -> Config:
    template = jinja2.Template(path.read_text(), undefined=jinja2.StrictUndefined)
    raw = yaml.safe_load(template.render(env_var=env_var)) or {}
    base = path.parent

    def resolve(folder: str | None) -> Path | None:
        if folder is None:
            return None
        candidate = Path(folder)
        return candidate if candidate.is_absolute() else (base / candidate).resolve()

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
        schema_log_datasets=[str(d) for d in raw.get("schema-log-datasets") or []],
    )
