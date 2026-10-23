import json

import pytest

from bqchange.schema_log import ChangeType, ColumnState, SchemaLog, diff, run_context
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
    def __init__(self, previous, current):
        self.previous, self.current = previous, current
        self.statements: list[tuple[str, dict | None]] = []
        self.datasets: list[str] = []

    def ensure_dataset(self, dataset_id):
        self.datasets.append(dataset_id)

    def execute(self, sql, params=None):
        self.statements.append((sql, params))

    def query(self, sql):
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
    log = SchemaLog(executor, "p", "dev_meta", ["dev_bronze", "dev_gold"])

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
    SchemaLog(executor, "p", "dev_meta", ["dev_bronze", "dev_gold"]).record("dbt")
    assert not any(sql.strip().startswith("insert") for sql, _ in executor.statements)


def test_record_rejects_unknown_sources():
    with pytest.raises(ValueError):
        SchemaLog(FakeExecutor(BASE, BASE), "p", "m", []).record("somebody")


def test_summary_tables_changes_and_condenses_baseline():
    assert "Baseline snapshot of 3 columns" in render_schema_changes("dbt", "dev", diff(None, BASE))
    current = [*BASE, ColumnState("silver", "stg_x", "new_col", "INT64")]
    table = render_schema_changes("dbt", "dev", diff(BASE, current))
    assert "| SILVER | stg_x | `new_col` | added |  | INT64 |" in table


def test_a_pull_request_clone_compares_by_layer_not_dataset_name():
    """The clone inherits DEV's state (dev_*) but captures pr_7_* datasets."""
    executor = FakeExecutor(BASE, BASE)
    log = SchemaLog(executor, "p", "pr_7_meta", ["pr_7_bronze", "pr_7_gold"])
    assert log.record("manual") == []


def test_legacy_state_with_dataset_names_is_still_understood():
    class Legacy(FakeExecutor):
        def query(self, sql):
            if "schema_state" in sql:
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

    log = SchemaLog(Legacy(BASE, BASE), "p", "dev_meta", ["dev_bronze", "dev_gold"])
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
