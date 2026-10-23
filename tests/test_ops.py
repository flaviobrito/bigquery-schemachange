from datetime import UTC, datetime

import pytest

from ops.check_schema_drift import Drift, build_message
from ops.environment import dataset_id, validate_environment
from ops.generate_sample_data import generate, write_csv
from ops.load_sample_data import to_json_rows
from ops.manage_environment import clone_environment, drop_environment


def test_message_lists_every_drifted_column(monkeypatch):
    monkeypatch.delenv("GITHUB_RUN_URL", raising=False)
    message = build_message(
        "prod",
        [
            Drift("customers", "loyalty_tier", "undeclared_in_dbt", "STRING", None),
            Drift("orders", "amount", "type_mismatch", "STRING", "NUMERIC"),
        ],
    )
    assert message.splitlines() == [
        "Schema drift detected in prod_bronze (2 column(s))",
        "- customers.loyalty_tier: exists in BigQuery but is not declared in dbt sources",
        "- orders.amount: data type differs between BigQuery and dbt (STRING vs NUMERIC)",
    ]


@pytest.mark.parametrize("name", ["dev", "prod", "pr_1", "pr_123"])
def test_valid_environments(name):
    assert validate_environment(name) == name


@pytest.mark.parametrize("name", ["billing_export", "pr_", "pr_x", "prod; drop", "DEV"])
def test_invalid_environments_are_rejected(name):
    with pytest.raises(ValueError):
        validate_environment(name)


def test_dataset_id_only_accepts_known_layers():
    assert dataset_id("p", "pr_7", "bronze") == "p.pr_7_bronze"
    with pytest.raises(ValueError):
        dataset_id("p", "dev", "billing")


@pytest.mark.parametrize("target", ["dev", "prod"])
def test_clone_and_drop_never_touch_long_lived_environments(target):
    with pytest.raises(ValueError, match="Refusing"):
        drop_environment(target, bq=object())
    with pytest.raises(ValueError, match="Refusing"):
        clone_environment("dev", target, bq=object())


def test_loader_adds_lineage_and_converts_booleans(tmp_path):
    data = generate(customers=5, products=3, orders=5, seed=1, now=datetime(2026, 1, 1))
    write_csv(data, tmp_path, "t")
    loaded_at = datetime(2026, 1, 2, tzinfo=UTC)
    rows = to_json_rows(tmp_path / "customers" / "customers_t.csv", loaded_at)

    assert rows[0]["_source_file"] == "customers_t.csv"
    assert [row["_source_row_number"] for row in rows] == list(range(1, len(rows) + 1))
    assert rows[0]["_loaded_at"] == "2026-01-02T00:00:00+00:00"
    assert all(isinstance(row["marketing_opt_in"], bool) for row in rows)


@pytest.mark.parametrize(
    ("layer", "table_id", "table_type", "expected"),
    [
        ("bronze", "customers", "TABLE", True),
        ("meta", "change_history", "TABLE", True),
        ("audit", "audit_schema_snapshots", "TABLE", True),
        ("audit", "load_log", "TABLE", True),
        ("audit", "dbt_expectations_expect_table_abc", "TABLE", False),
        ("audit", "deployment_history", "VIEW", False),
    ],
)
def test_clone_selection(layer, table_id, table_type, expected):
    from ops.manage_environment import should_clone

    assert should_clone(layer, table_id, table_type) is expected
