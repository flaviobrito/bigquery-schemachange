from datetime import datetime

from ops.report import dbt_section, drift_section, markdown_table, migrations_section

WHEN = datetime(2026, 1, 2, 3, 4, 5)


def test_markdown_table_escapes_pipes_and_newlines():
    table = markdown_table(["A"], [["x|y\nz"]])
    assert table.splitlines()[-1] == "| x\\|y z |"


def test_migrations_section_lists_versions():
    section = migrations_section(
        [
            {
                "installed_on": WHEN,
                "version": "1.4.0",
                "script": "V1.4.0__x.sql",
                "script_type": "V",
                "execution_time_ms": 12,
            }
        ]
    )
    assert "| 2026-01-02 03:04:05 | 1.4.0 | `V1.4.0__x.sql` | V | 12 |" in section


def test_drift_section_reports_alignment_and_problems():
    assert "✅" in drift_section([])
    section = drift_section(
        [
            {
                "table_name": "customers",
                "column_name": "loyalty_tier",
                "drift_status": "undeclared_in_dbt",
                "physical_data_type": "STRING",
                "declared_data_type": None,
            }
        ]
    )
    assert "| customers | `loyalty_tier` | ❌ undeclared_in_dbt | STRING |  |" in section


def test_dbt_section_counts_statuses_and_lists_failures():
    section = dbt_section(
        {
            "args": {"which": "build"},
            "results": [
                {"status": "pass", "unique_id": "test.ecommerce.a"},
                {
                    "status": "fail",
                    "unique_id": "test.ecommerce.assert_no_bronze_schema_drift",
                    "failures": 1,
                    "message": "Got 1 result",
                },
            ],
        }
    )
    assert "❌ fail: 1" in section
    assert "`assert_no_bronze_schema_drift`" in section


def test_failed_queries_are_never_reported_as_success():
    from ops.report import migrations_section, schema_section

    for section in (drift_section(None), migrations_section(None), schema_section(None)):
        assert "⚠️ Not available" in section
        assert "✅" not in section


def test_dbt_messages_are_stripped_of_terminal_colours():
    section = dbt_section(
        {
            "results": [
                {
                    "status": "fail",
                    "unique_id": "unit_test.ecommerce.x.y",
                    "message": "\x1b[32mactual\x1b[0m differs from \x1b[31mexpected\x1b[0m",
                }
            ]
        }
    )
    assert "actual differs from expected" in section
    assert "\x1b" not in section
