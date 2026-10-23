"""Schema change log: records how the structure of every monitored dataset evolves.

The change history table records what bqchange *applied*. This log records what
bqchange *observes* in BigQuery's catalog, for every table and view of the
monitored datasets, whoever created it (migrations, dbt or a person). After
each step of a deployment it snapshots the monitored datasets, compares the
snapshot with the previous one and writes one event per change:

    columns     added, removed, type changed
    properties  partitioning, clustering, table type, table options
                (description, labels, expiration...) and column descriptions,
                for tables that exist in both snapshots

Each event is attributed to its source:

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
    PROPERTY_ADDED = "property_added"
    PROPERTY_REMOVED = "property_removed"
    PROPERTY_CHANGED = "property_changed"


# column_name used for table-level properties.
TABLE_LEVEL = "(table)"
# Options whose value is environment-specific and changes on every rebuild
# (an absolute timestamp set by dataset defaults), so they are not schema decisions.
IGNORED_OPTIONS = ("expiration_timestamp",)


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


@dataclass(frozen=True, order=True)
class PropertyState:
    """A table or column property: partitioning, clustering, options, descriptions."""

    layer: str
    table_name: str
    column_name: str
    property: str
    value: str | None

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (self.layer, self.table_name, self.column_name, self.property)


@dataclass(frozen=True)
class SchemaChange:
    change_type: ChangeType
    layer: str
    table_name: str
    column_name: str
    old_data_type: str | None
    new_data_type: str | None
    property: str | None = None
    old_value: str | None = None
    new_value: str | None = None


def diff(
    previous: list[ColumnState] | None,
    current: list[ColumnState],
    ignore_missing_tables: bool = False,
) -> list[SchemaChange]:
    """Column-level changes between two snapshots. No previous snapshot = baseline.

    With ignore_missing_tables, tables absent from the current snapshot are not
    reported as removed: in a pull request environment only modified models are
    built, the others are read from DEV.
    """
    if previous is None:
        return [
            SchemaChange(
                ChangeType.BASELINE, c.layer, c.table_name, c.column_name, None, c.data_type
            )
            for c in sorted(current)
        ]
    if ignore_missing_tables:
        present = {(c.layer, c.table_name) for c in current}
        previous = [c for c in previous if (c.layer, c.table_name) in present]
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


def diff_properties(
    previous: list[PropertyState] | None,
    current: list[PropertyState],
    ignore_missing_tables: bool = False,
) -> list[SchemaChange]:
    """Property changes of tables present in both snapshots.

    The first snapshot only establishes the state. Properties of tables that were
    created or dropped are not listed: the column changes already describe those.
    """
    if previous is None:
        return []
    before_tables = {(p.layer, p.table_name) for p in previous}
    after_tables = {(p.layer, p.table_name) for p in current}
    if ignore_missing_tables:
        before_tables &= after_tables
    common = before_tables & after_tables
    before = {p.key: p for p in previous if (p.layer, p.table_name) in common}
    after = {p.key: p for p in current if (p.layer, p.table_name) in common}
    changes = []
    for key in sorted(before.keys() | after.keys()):
        old, new = before.get(key), after.get(key)
        if old and new and old.value == new.value:
            continue
        change_type = (
            ChangeType.PROPERTY_ADDED
            if old is None
            else ChangeType.PROPERTY_REMOVED
            if new is None
            else ChangeType.PROPERTY_CHANGED
        )
        layer, table_name, column_name, prop = key
        changes.append(
            SchemaChange(
                change_type,
                layer,
                table_name,
                column_name,
                None,
                None,
                prop,
                old.value if old else None,
                new.value if new else None,
            )
        )
    return changes


def legacy_layer_of(dataset: str) -> str:
    """Layer of a dataset name in states written before explicit layer maps."""
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
    def __init__(self, executor: Executor, project: str, meta_dataset: str, layers: dict[str, str]):
        """layers maps each logical layer to its dataset, e.g. {"bronze": "dev_bronze"}."""
        self._executor = executor
        self._project = project
        self._meta = f"{project}.{meta_dataset}"
        self._layers = layers
        self._layer_of_dataset = {dataset: layer for layer, dataset in layers.items()}

    @property
    def log_table(self) -> str:
        return f"{self._meta}.schema_change_log"

    @property
    def state_table(self) -> str:
        return f"{self._meta}.schema_state"

    @property
    def property_state_table(self) -> str:
        return f"{self._meta}.schema_state_properties"

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
        self._executor.execute(
            f"""
            alter table `{self.log_table}`
            add column if not exists property string,
            add column if not exists old_value string,
            add column if not exists new_value string
            """
        )

    def capture(self) -> list[ColumnState]:
        """Columns of every monitored dataset that exists (a fresh environment has none)."""
        columns: list[ColumnState] = []
        for layer, dataset in self._layers.items():
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
            columns += [ColumnState(layer=layer, **row) for row in rows]
        return columns

    def capture_properties(self) -> list[PropertyState]:
        """Table and column properties of every monitored dataset that exists."""
        properties: list[PropertyState] = []
        for layer, dataset in self._layers.items():
            schema = f"`{self._project}.{dataset}.INFORMATION_SCHEMA"
            not_transient = r"not regexp_contains(table_name, r'__dbt_(tmp|backup)')"
            ignored_options = ", ".join(f"'{name}'" for name in IGNORED_OPTIONS)
            try:
                rows = self._executor.query(
                    f"""
                    -- bqchange: table and column properties
                    select table_name, '{TABLE_LEVEL}' as column_name,
                        'table_type' as property,
                        -- A zero-copy clone (pull request environments) is still a table.
                        if(table_type = 'CLONE', 'BASE TABLE', table_type) as value
                    from {schema}.TABLES`
                    where {not_transient}
                    union all
                    select table_name, '{TABLE_LEVEL}', concat('option:', option_name), option_value
                    from {schema}.TABLE_OPTIONS`
                    where {not_transient}
                        and option_name not in ({ignored_options})
                    union all
                    select table_name, '{TABLE_LEVEL}', 'partitioning', column_name
                    from {schema}.COLUMNS`
                    where is_partitioning_column = 'YES' and {not_transient}
                    union all
                    select table_name, '{TABLE_LEVEL}', 'clustering',
                        string_agg(column_name, ', ' order by clustering_ordinal_position)
                    from {schema}.COLUMNS`
                    where clustering_ordinal_position is not null and {not_transient}
                    group by table_name
                    union all
                    select table_name, column_name, 'description', description
                    from {schema}.COLUMN_FIELD_PATHS`
                    where field_path = column_name and description is not null
                        and {not_transient}
                    """
                )
            except Exception as error:
                if "Not found" not in str(error):
                    raise
                continue
            properties += [PropertyState(layer=layer, **row) for row in rows]
        return properties

    def previous_properties(self) -> list[PropertyState] | None:
        try:
            rows = self._executor.query(f"select * from `{self.property_state_table}`")
        except Exception:
            return None
        return [PropertyState(**row) for row in rows]

    def previous(self) -> list[ColumnState] | None:
        try:
            rows = self._executor.query(f"select * from `{self.state_table}`")
        except Exception:
            return None
        # States written before layers were introduced store the dataset name.
        return [
            ColumnState(
                layer=row.get("layer")
                or self._layer_of_dataset.get(row["dataset"])
                or legacy_layer_of(row["dataset"]),
                table_name=row["table_name"],
                column_name=row["column_name"],
                data_type=row["data_type"],
            )
            for row in rows
        ]

    def record(self, source: str, ignore_missing_tables: bool = False) -> list[SchemaChange]:
        """Snapshot the monitored datasets, log the differences, store the new state."""
        if source not in SOURCES:
            raise ValueError(f"Unknown source {source!r}: expected one of {SOURCES}")
        self.ensure()
        current = self.capture()
        previous = self.previous()
        current_properties = self.capture_properties()
        previous_properties = self.previous_properties()
        changes = diff(previous, current, ignore_missing_tables) + diff_properties(
            previous_properties, current_properties, ignore_missing_tables
        )
        state_columns, state_properties = current, current_properties
        if ignore_missing_tables:
            # Keep the inherited (DEV) version of tables not built here, so the
            # next step still compares each model with its DEV counterpart.
            present = {(c.layer, c.table_name) for c in current}
            state_columns = current + [
                c for c in previous or [] if (c.layer, c.table_name) not in present
            ]
            state_properties = current_properties + [
                p for p in previous_properties or [] if (p.layer, p.table_name) not in present
            ]
        if changes:
            # One job for all changes: rows travel as a JSON array parameter.
            payload = json.dumps(
                [
                    {
                        "change_type": c.change_type.value,
                        "layer": c.layer,
                        "dataset": self._layers.get(c.layer, c.layer),
                        "table_name": c.table_name,
                        "column_name": c.column_name,
                        "old_data_type": c.old_data_type,
                        "new_data_type": c.new_data_type,
                        "property": c.property,
                        "old_value": c.old_value,
                        "new_value": c.new_value,
                    }
                    for c in changes
                ]
            )
            self._executor.execute(
                f"""
                insert into `{self.log_table}` (
                    changed_at, source, change_type, layer, dataset, table_name,
                    column_name, old_data_type, new_data_type, git_sha, pull_request,
                    workflow, run_url, actor, property, old_value, new_value
                )
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
                    @git_sha, @pull_request, @workflow, @run_url, @actor,
                    json_value(item, '$.property'),
                    json_value(item, '$.old_value'),
                    json_value(item, '$.new_value')
                from unnest(json_query_array(@payload)) as item
                """,
                params={"source": source, "payload": payload, **run_context()},
            )
        state = json.dumps([c.__dict__ for c in state_columns])
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
        self._executor.execute(
            f"""
            create or replace table `{self.property_state_table}`
            options (description = 'Latest property snapshot used by the schema change log.')
            as
            select
                json_value(item, '$.layer') as layer,
                json_value(item, '$.table_name') as table_name,
                json_value(item, '$.column_name') as column_name,
                json_value(item, '$.property') as property,
                json_value(item, '$.value') as value
            from unnest(json_query_array(@state)) as item
            """,
            params={"state": json.dumps([p.__dict__ for p in state_properties])},
        )
        return changes
