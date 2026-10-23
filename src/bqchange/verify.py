"""`bqchange verify`: check configuration, credentials and permissions before deploying."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from bqchange.config import Config
from bqchange.secrets import Redactor


@dataclass(frozen=True)
class Check:
    name: str
    status: str  # "ok", "warn" or "fail"
    detail: str


class VerifyClient(Protocol):
    def principal(self) -> str: ...

    def can_run_jobs(self) -> tuple[bool, str]: ...

    def dataset_exists(self, dataset_id: str) -> bool: ...

    def table_exists(self, table_id: str) -> bool: ...


def configuration_lines(config: Config, redact: Redactor) -> list[tuple[str, Any]]:
    """Resolved configuration, with secret values masked."""
    return [
        ("project", config.project),
        ("location", config.location),
        ("root-folder", config.root_folder),
        ("modules-folder", config.modules_folder),
        ("change-history-table", config.change_history_table),
        ("maximum-bytes-billed", config.maximum_bytes_billed),
        ("layers", config.layers),
        ("schema-log-layers", config.schema_log_layers),
        ("cli-allowed-commands", config.cli_allowed_commands),
        ("vars", redact(config.vars)),
    ]


def run_checks(config: Config, client: VerifyClient) -> list[Check]:
    checks = []
    try:
        checks.append(Check("credentials", "ok", client.principal()))
    except Exception as error:
        checks.append(
            Check("credentials", "fail", f"{error}. Run `gcloud auth application-default login`")
        )
        return checks

    ok, detail = client.can_run_jobs()
    checks.append(Check("run jobs", "ok" if ok else "fail", detail))
    if not config.root_folder.is_dir():
        checks.append(Check("root-folder", "fail", f"{config.root_folder} does not exist"))
    else:
        checks.append(Check("root-folder", "ok", str(config.root_folder)))
    for layer, dataset in config.layers.items():
        exists = client.dataset_exists(f"{config.project}.{dataset}")
        checks.append(
            Check(
                f"layer {layer}",
                "ok" if exists else "warn",
                dataset if exists else f"{dataset} does not exist yet (a migration may create it)",
            )
        )
    history = client.table_exists(config.change_history_table)
    checks.append(
        Check(
            "change history",
            "ok" if history else "warn",
            config.change_history_table
            if history
            else f"{config.change_history_table} will be created by the first deploy",
        )
    )
    return checks


def format_report(config: Config, checks: list[Check], redact: Redactor) -> str:
    icons = {"ok": "✅", "warn": "⚠️", "fail": "❌"}
    lines = ["Configuration"]
    lines += [f"  {key:<22} {value}" for key, value in configuration_lines(config, redact)]
    lines += ["", "Checks"]
    lines += [f"  {icons[c.status]} {c.name:<20} {redact(c.detail)}" for c in checks]
    return "\n".join(lines)
