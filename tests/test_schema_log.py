import json

import pytest

from bqchange.schema_log import (
    ChangeType,
    ColumnState,
    PropertyState,
    SchemaLog,
    diff,
    diff_properties,
    run_context,
)
from bqchange.summary import render_schema_changes

BASE = [
    ColumnState("bronze", "customers", "customer_id", "STRING"),
    ColumnState("gold", "dim_customers", "lifetime_revenue", "NUMERIC"),
    ColumnState("gold", "dim_customers", "email", "STRING"),
]


def test_first_snapshot_is_a_baseline():
    changes = diff(None, BASE)
    assert {c.change_type for c in changes} == {ChangeType.BASELINE}
    assert len(changes) == 3


def test_added_removed_and_retyped_columns_are_detected():
    current = [
        ColumnState("bronze", "customers", "customer_id", "STRING"),
        ColumnState("bronze", "customers", "loyalty_tier", "STRING"),
        ColumnState("gold", "dim_customers", "lifetime_revenue", "NUMERIC(18, 2)"),
    ]
    changes = {(c.change_type, c.table_name, c.column_name): c for c in diff(BASE, current)}

    assert (ChangeType.ADDED, "customers", "loyalty_tier") in changes
    assert (ChangeType.REMOVED, "dim_customers", "email") in changes
    retyped = changes[(ChangeType.TYPE_CHANGED, "dim_customers", "lifetime_revenue")]
    assert (retyped.old_data_type, retyped.new_data_type) == ("NUMERIC", "NUMERIC(18, 2)")


def test_identical_snapshots_have_no_changes():
    assert diff(BASE, list(reversed(BASE))) == []


def test_run_context_reads_github_variables(monkeypatch):
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "org/repo")
    monkeypatch.setenv("GITHUB_RUN_ID", "42")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/7/merge")
    monkeypatch.setenv("GITHUB_SHA", "abc123")
    context = run_context()
    assert context["run_url"] == "https://github.com/org/repo/actions/runs/42"
    assert context["pull_request"] == "7"
    assert context["git_sha"] == "abc123"


class FakeExecutor:
    def __init__(self, previous, current, previous_properties=None, current_properties=()):
        self.previous, self.current = previous, current
        self.previous_properties = previous_properties
        self.current_properties = list(current_properties)
        self.statements: list[tuple[str, dict | None]] = []
        self.datasets: list[str] = []

    def ensure_dataset(self, dataset_id):
        self.datasets.append(dataset_id)

    def execute(self, sql, params=None):
        self.statements.append((sql, params))

    def query(self, sql):
        if "schema_state_properties" in sql:
            if self.previous_properties is None:
                raise RuntimeError("Not found: schema_state_properties")
            return [p.__dict__ for p in self.previous_properties]
        if "bqchange: table and column properties" in sql:
            dataset = sql.split("`")[1].split(".")[1]
            if dataset == "missing":
                raise RuntimeError("Not found: Dataset p:missing")
            layer = dataset.rsplit("_", 1)[-1]
            return [
                {k: v for k, v in p.__dict__.items() if k != "layer"}
                for p in self.current_properties
                if p.layer == layer
            ]
        if "schema_state" in sql:
            if self.previous is None:
                raise RuntimeError("Not found: schema_state")
            return [c.__dict__ for c in self.previous]
        dataset = sql.split("`")[1].split(".")[1]
        if dataset == "missing":
            raise RuntimeError("Not found: Dataset p:missing")
        layer = dataset.rsplit("_", 1)[-1]
        return [
            {k: v for k, v in c.__dict__.items() if k != "layer"}
            for c in self.current
            if c.layer == layer
        ]


def test_record_logs_all_changes_in_one_insert_and_stores_state():
    current = [*BASE, ColumnState("gold", "dim_customers", "manual_note", "STRING")]
    executor = FakeExecutor(BASE, current)
    log = SchemaLog(executor, "p", "dev_meta", {"bronze": "dev_bronze", "gold": "dev_gold"})

    changes = log.record("manual")

    assert [(c.change_type, c.column_name) for c in changes] == [(ChangeType.ADDED, "manual_note")]
    inserts = [p for sql, p in executor.statements if sql.strip().startswith("insert")]
    assert len(inserts) == 1
    assert inserts[0]["source"] == "manual"
    assert json.loads(inserts[0]["payload"])[0]["column_name"] == "manual_note"
    assert any(
        "create or replace table `p.dev_meta.schema_state`" in sql for sql, _ in executor.statements
    )


def test_record_without_changes_does_not_insert():
    executor = FakeExecutor(BASE, BASE)
    SchemaLog(executor, "p", "dev_meta", {"bronze": "dev_bronze", "gold": "dev_gold"}).record("dbt")
    assert not any(sql.strip().startswith("insert") for sql, _ in executor.statements)


def test_record_rejects_unknown_sources():
    with pytest.raises(ValueError):
        SchemaLog(FakeExecutor(BASE, BASE), "p", "m", {}).record("somebody")


def test_summary_tables_changes_and_condenses_baseline():
    assert "Baseline snapshot of 3 columns" in render_schema_changes("dbt", "dev", diff(None, BASE))
    current = [*BASE, ColumnState("silver", "stg_x", "new_col", "INT64")]
    table = render_schema_changes("dbt", "dev", diff(BASE, current))
    assert "| SILVER | stg_x | `new_col` | added |  |  | INT64 |" in table


def test_a_pull_request_clone_compares_by_layer_not_dataset_name():
    """The clone inherits DEV's state (dev_*) but captures pr_7_* datasets."""
    executor = FakeExecutor(BASE, BASE)
    log = SchemaLog(executor, "p", "pr_7_meta", {"bronze": "pr_7_bronze", "gold": "pr_7_gold"})
    assert log.record("manual") == []


def test_legacy_state_with_dataset_names_is_still_understood():
    class Legacy(FakeExecutor):
        def query(self, sql):
            if "schema_state" in sql and "schema_state_properties" not in sql:
                return [
                    {
                        "dataset": "dev_" + c.layer,
                        "table_name": c.table_name,
                        "column_name": c.column_name,
                        "data_type": c.data_type,
                    }
                    for c in self.previous
                ]
            return super().query(sql)

    log = SchemaLog(
        Legacy(BASE, BASE), "p", "dev_meta", {"bronze": "dev_bronze", "gold": "dev_gold"}
    )
    assert log.record("dbt") == []


def test_pull_request_mode_ignores_tables_that_were_not_built():
    current = [ColumnState("bronze", "customers", "customer_id", "STRING")]
    assert diff(BASE, current, ignore_missing_tables=True) == []
    assert {c.change_type for c in diff(BASE, current)} == {ChangeType.REMOVED}


def test_pull_request_mode_still_reports_changes_in_built_tables():
    current = [
        ColumnState("bronze", "customers", "customer_id", "STRING"),
        ColumnState("gold", "dim_customers", "lifetime_revenue", "NUMERIC"),
    ]
    changes = diff(BASE, current, ignore_missing_tables=True)
    assert [(c.change_type, c.column_name) for c in changes] == [(ChangeType.REMOVED, "email")]


def test_pull_request_state_keeps_unbuilt_tables_for_the_next_step():
    """After migrations (BRONZE only) the GOLD state must survive for the dbt step."""
    bronze_only = [ColumnState("bronze", "customers", "customer_id", "STRING")]
    executor = FakeExecutor(BASE, bronze_only)
    log = SchemaLog(executor, "p", "pr_7_meta", {"bronze": "pr_7_bronze", "gold": "pr_7_gold"})
    assert log.record("migration", ignore_missing_tables=True) == []

    state = next(p for sql, p in executor.statements if "schema_state" in sql and p)
    stored = {(c["layer"], c["table_name"], c["column_name"]) for c in json.loads(state["state"])}
    assert ("gold", "dim_customers", "email") in stored


def test_layers_can_have_any_name_including_underscores():
    """Not tied to medallion naming: a Data Vault layout works the same way."""
    vault = [
        ColumnState("raw_vault", "hub_customer", "customer_hk", "BYTES"),
        ColumnState("marts", "dim_customer", "customer_id", "STRING"),
    ]
    executor = FakeExecutor(None, [])
    executor.query = lambda sql: (
        (_ for _ in ()).throw(RuntimeError("Not found: schema_state"))
        if "schema_state" in sql
        else [
            {k: v for k, v in c.__dict__.items() if k != "layer"}
            for c in vault
            if ("dev_raw_vault" in sql) == (c.layer == "raw_vault")
        ]
    )
    log = SchemaLog(executor, "p", "dev_meta", {"raw_vault": "dev_raw_vault", "marts": "dev_marts"})
    assert sorted(log.capture()) == sorted(vault)


def test_capture_skips_datasets_that_do_not_exist_yet():
    executor = FakeExecutor(None, BASE)
    log = SchemaLog(
        executor, "p", "dev_meta", {"bronze": "dev_bronze", "x": "missing", "gold": "dev_gold"}
    )
    assert len(log.capture()) == 3


PROPS = [
    PropertyState("bronze", "customers", "(table)", "partitioning", "_loaded_at"),
    PropertyState("bronze", "customers", "(table)", "clustering", "customer_id"),
    PropertyState("bronze", "customers", "(table)", "option:description", '"Customers."'),
    PropertyState("gold", "dim_customers", "email", "description", "Raw email"),
]


def test_first_property_snapshot_only_sets_the_state():
    assert diff_properties(None, PROPS) == []


def test_property_changes_are_detected():
    current = [
        PropertyState("bronze", "customers", "(table)", "partitioning", "_loaded_at"),
        PropertyState("bronze", "customers", "(table)", "clustering", "customer_id, country_code"),
        PropertyState("bronze", "customers", "(table)", "option:labels", '[STRUCT("pii", "yes")]'),
        PropertyState("gold", "dim_customers", "email", "description", "Raw email"),
    ]
    changes = {(c.change_type, c.property): c for c in diff_properties(PROPS, current)}
    clustering = changes[(ChangeType.PROPERTY_CHANGED, "clustering")]
    assert (clustering.old_value, clustering.new_value) == (
        "customer_id",
        "customer_id, country_code",
    )
    assert (ChangeType.PROPERTY_ADDED, "option:labels") in changes
    assert (ChangeType.PROPERTY_REMOVED, "option:description") in changes
    assert len(changes) == 3


def test_properties_of_new_or_dropped_tables_are_not_listed():
    current = [
        *PROPS[:3],
        PropertyState("gold", "dim_customers_v2", "(table)", "table_type", "BASE TABLE"),
    ]
    assert diff_properties(PROPS, current) == []


def test_record_logs_property_changes_with_values():
    changed = [*PROPS[:3], PropertyState("gold", "dim_customers", "email", "description", "PII")]
    executor = FakeExecutor(BASE, BASE, PROPS, changed)
    log = SchemaLog(executor, "p", "dev_meta", {"bronze": "dev_bronze", "gold": "dev_gold"})

    changes = log.record("manual")

    assert [(c.change_type, c.column_name, c.property) for c in changes] == [
        (ChangeType.PROPERTY_CHANGED, "email", "description")
    ]
    payload = next(p for sql, p in executor.statements if sql.strip().startswith("insert"))
    row = json.loads(payload["payload"])[0]
    assert (row["property"], row["old_value"], row["new_value"]) == (
        "description",
        "Raw email",
        "PII",
    )
    stored = next(p for sql, p in executor.statements if "schema_state_properties" in sql and p)
    assert len(json.loads(stored["state"])) == 4


def test_summary_shows_property_changes():
    change = diff_properties(
        PROPS, [*PROPS[:3], PropertyState("gold", "dim_customers", "email", "description", "PII")]
    )
    table = render_schema_changes("manual", "dev", change)
    assert (
        "| GOLD | dim_customers | `email` | property changed | description | Raw email | PII |"
        in table
    )


def test_property_capture_ignores_volatile_options_and_clone_type():
    executor = FakeExecutor(None, [])
    executor.query = lambda sql: executor.statements.append((sql, None)) or []
    SchemaLog(executor, "p", "pr_7_meta", {"bronze": "pr_7_bronze"}).capture_properties()
    sql = next(q for q, _ in executor.statements if "table and column properties" in q)
    assert "option_name not in ('expiration_timestamp')" in sql
    assert "if(table_type = 'CLONE', 'BASE TABLE', table_type)" in sql
