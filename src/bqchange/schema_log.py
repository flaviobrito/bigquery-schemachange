"""Schema change log: records how the structure of every layer evolves.

Migrations own BRONZE and are recorded in the change history table. dbt owns
SILVER and GOLD and rebuilds them, so there is no script to record. Instead,
after each step of a deployment, bqchange takes a snapshot of the columns of
the monitored datasets, compares it with the previous snapshot and writes one
event per added, removed or retyped column, attributed to its source:

    migration   changes made by bqchange scripts
    dbt         changes made by dbt models
    manual      changes found before any step ran: made outside the pipeline
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import StrEnum

from bqchange.executor import Executor

SOURCES = ("migration", "dbt", "manual")


class ChangeType(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    TYPE_CHANGED = "type_changed"
    BASELINE = "baseline"


@dataclass(frozen=True, order=True)
class ColumnState:
    """One column, identified by layer (not dataset) so clones compare with their source."""

    layer: str
    table_name: str
    column_name: str
    data_type: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.layer, self.table_name, self.column_name)


@dataclass(frozen=True)
class SchemaChange:
    change_type: ChangeType
    layer: str
    table_name: str
    column_name: str
    old_data_type: str | None
    new_data_type: str | None


def diff(previous: list[ColumnState] | None, current: list[ColumnState]) -> list[SchemaChange]:
    """Column-level changes between two snapshots. No previous snapshot = baseline."""
    if previous is None:
        return [
            SchemaChange(
                ChangeType.BASELINE, c.layer, c.table_name, c.column_name, None, c.data_type
            )
            for c in sorted(current)
        ]
    before = {c.key: c for c in previous}
    after = {c.key: c for c in current}
    changes = []
    for key in sorted(after.keys() - before.keys()):
        c = after[key]
        changes.append(SchemaChange(ChangeType.ADDED, *key, None, c.data_type))
    for key in sorted(before.keys() - after.keys()):
        c = before[key]
        changes.append(SchemaChange(ChangeType.REMOVED, *key, c.data_type, None))
    for key in sorted(before.keys() & after.keys()):
        if before[key].data_type != after[key].data_type:
            changes.append(
                SchemaChange(
                    ChangeType.TYPE_CHANGED, *key, before[key].data_type, after[key].data_type
                )
            )
    return changes


def layer_of(dataset: str) -> str:
    """dev_bronze, prod_bronze and pr_7_bronze are all the BRONZE layer."""
    return dataset.rsplit("_", 1)[-1]


def run_context() -> dict[str, str | None]:
    """Where a change came from, taken from GitHub Actions variables when available."""
    server, repository = os.environ.get("GITHUB_SERVER_URL"), os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    ref = os.environ.get("GITHUB_REF", "")
    pull_request = (
        ref.split("/")[2] if ref.startswith("refs/pull/") else os.environ.get("PR_NUMBER")
    )
    return {
        "git_sha": os.environ.get("GITHUB_SHA"),
        "pull_request": pull_request,
        "workflow": os.environ.get("GITHUB_WORKFLOW"),
        "run_url": f"{server}/{repository}/actions/runs/{run_id}" if run_id else None,
        "actor": os.environ.get("GITHUB_ACTOR"),
    }


class SchemaLog:
    def __init__(self, executor: Executor, project: str, meta_dataset: str, datasets: list[str]):
        self._executor = executor
        self._project = project
        self._meta = f"{project}.{meta_dataset}"
        self._datasets = datasets
        self._dataset_of_layer = {layer_of(d): d for d in datasets}

    @property
    def log_table(self) -> str:
        return f"{self._meta}.schema_change_log"

    @property
    def state_table(self) -> str:
        return f"{self._meta}.schema_state"

    def ensure(self) -> None:
        self._executor.ensure_dataset(self._meta)
        self._executor.execute(
            f"""
            create table if not exists `{self.log_table}` (
                changed_at timestamp not null,
                source string not null,
                change_type string not null,
                layer string,
                dataset string not null,
                table_name string not null,
                column_name string not null,
                old_data_type string,
                new_data_type string,
                git_sha string,
                pull_request string,
                workflow string,
                run_url string,
                actor string
            )
            partition by date(changed_at)
            options (description = 'Column-level schema changes of every layer, by source.')
            """
        )

    def capture(self) -> list[ColumnState]:
        """Columns of every monitored dataset that exists (a fresh environment has none)."""
        columns: list[ColumnState] = []
        for dataset in self._datasets:
            try:
                rows = self._executor.query(
                    f"""
                    select table_name, column_name, data_type
                    from `{self._project}.{dataset}.INFORMATION_SCHEMA.COLUMNS`
                    where not regexp_contains(table_name, r'__dbt_(tmp|backup)')
                    """
                )
            except Exception as error:
                if "Not found" not in str(error):
                    raise
                continue
            columns += [ColumnState(layer=layer_of(dataset), **row) for row in rows]
        return columns

    def previous(self) -> list[ColumnState] | None:
        try:
            rows = self._executor.query(f"select * from `{self.state_table}`")
        except Exception:
            return None
        # States written before layers were introduced store the dataset name.
        return [
            ColumnState(
                layer=row.get("layer") or layer_of(row["dataset"]),
                table_name=row["table_name"],
                column_name=row["column_name"],
                data_type=row["data_type"],
            )
            for row in rows
        ]

    def record(self, source: str) -> list[SchemaChange]:
        """Snapshot the monitored datasets, log the differences, store the new state."""
        if source not in SOURCES:
            raise ValueError(f"Unknown source {source!r}: expected one of {SOURCES}")
        self.ensure()
        current = self.capture()
        changes = diff(self.previous(), current)
        if changes:
            # One job for all changes: rows travel as a JSON array parameter.
            payload = json.dumps(
                [
                    {
                        "change_type": c.change_type.value,
                        "layer": c.layer,
                        "dataset": self._dataset_of_layer.get(c.layer, c.layer),
                        "table_name": c.table_name,
                        "column_name": c.column_name,
                        "old_data_type": c.old_data_type,
                        "new_data_type": c.new_data_type,
                    }
                    for c in changes
                ]
            )
            self._executor.execute(
                f"""
                insert into `{self.log_table}`
                select
                    current_timestamp(),
                    @source,
                    json_value(item, '$.change_type'),
                    json_value(item, '$.layer'),
                    json_value(item, '$.dataset'),
                    json_value(item, '$.table_name'),
                    json_value(item, '$.column_name'),
                    json_value(item, '$.old_data_type'),
                    json_value(item, '$.new_data_type'),
                    @git_sha, @pull_request, @workflow, @run_url, @actor
                from unnest(json_query_array(@payload)) as item
                """,
                params={"source": source, "payload": payload, **run_context()},
            )
        state = json.dumps([c.__dict__ for c in current])
        self._executor.execute(
            f"""
            create or replace table `{self.state_table}`
            options (description = 'Latest column snapshot used by the schema change log.')
            as
            select
                json_value(item, '$.layer') as layer,
                json_value(item, '$.table_name') as table_name,
                json_value(item, '$.column_name') as column_name,
                json_value(item, '$.data_type') as data_type
            from unnest(json_query_array(@state)) as item
            """,
            params={"state": state},
        )
        return changes
