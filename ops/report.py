"""Markdown report of schema changes and data quality, for the GitHub Actions job summary.

Sections:
    migrations  latest versioned/repeatable rows of <env>_audit.deployment_history
    schema      newest BRONZE columns from <env>_audit.audit_schema_snapshots
    drift       non-aligned rows of <env>_audit.audit_schema_drift
    dbt         results of the last dbt invocation (dbt/target/run_results.json)

Example:
    python -m ops.report --sections migrations,schema,drift,dbt
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from ops.environment import client, current_environment, dataset_id

logger = logging.getLogger(__name__)

UNAVAILABLE = "⚠️ Not available: the query failed (see the step log)."
# dbt colours unit test diffs; terminal escape codes are noise in Markdown.
ANSI_ESCAPES = re.compile(r"\x1b\[[0-9;]*m")
# dbt appends a 10-character hash to long generic test names.
TEST_HASH = re.compile(r"\.[0-9a-f]{10}$")

STATUS_ICONS = {
    "success": "✅",
    "pass": "✅",
    "warn": "⚠️",
    "error": "❌",
    "fail": "❌",
    "skipped": "⏭️",
}


def markdown_table(headers: list[str], rows: Iterable[Iterable[object]]) -> str:
    def cell(value: object) -> str:
        return "" if value is None else str(value).replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines += ["| " + " | ".join(cell(value) for value in row) + " |" for row in rows]
    return "\n".join(lines)


def migrations_section(rows: list[dict] | None) -> str:
    if rows is None:
        return f"#### Schema migrations (change history)\n\n{UNAVAILABLE}"
    if not rows:
        return "#### Migrations\n\nNo migrations recorded yet."
    table = markdown_table(
        ["Installed on (UTC)", "Version", "Script", "Type", "Duration (ms)"],
        (
            [
                row["installed_on"].strftime("%Y-%m-%d %H:%M:%S"),
                row["version"] or "-",
                f"`{row['script']}`",
                row["script_type"],
                row["execution_time_ms"],
            ]
            for row in rows
        ),
    )
    return f"#### Schema migrations (change history)\n\n{table}"


def schema_section(rows: list[dict] | None) -> str:
    if rows is None:
        return f"#### BRONZE schema\n\n{UNAVAILABLE}"
    if not rows:
        return "#### BRONZE schema\n\nNo schema snapshot yet: run `dbt build` first."
    table = markdown_table(
        ["Table", "Column", "Type", "First seen (UTC)", "Still present"],
        (
            [
                row["table_name"],
                f"`{row['column_name']}`",
                row["data_type"],
                row["first_seen_at"].strftime("%Y-%m-%d %H:%M:%S"),
                "yes" if row["is_current"] else "**dropped**",
            ]
            for row in rows
        ),
    )
    return f"#### BRONZE schema: most recent columns\n\n{table}"


def drift_section(rows: list[dict] | None) -> str:
    if rows is None:
        return f"#### Schema drift\n\n{UNAVAILABLE}"
    if not rows:
        return "#### Schema drift\n\n✅ BRONZE matches the dbt source declarations."
    table = markdown_table(
        ["Table", "Column", "Status", "BigQuery type", "Declared type"],
        (
            [
                row["table_name"],
                f"`{row['column_name']}`",
                f"❌ {row['drift_status']}",
                row["physical_data_type"],
                row["declared_data_type"],
            ]
            for row in rows
        ),
    )
    return f"#### Schema drift\n\n{table}"


def dbt_section(run_results: dict) -> str:
    results = run_results.get("results", [])
    if not results:
        return "#### dbt\n\nNo dbt results found."
    counts = Counter(result["status"] for result in results)
    totals = " · ".join(
        f"{STATUS_ICONS.get(status, '')} {status}: {count}"
        for status, count in sorted(counts.items())
    )
    problems = [r for r in results if r["status"] in {"warn", "error", "fail"}]
    section = f"#### dbt ({run_results.get('args', {}).get('which', 'run')})\n\n{totals}"
    if problems:
        table = markdown_table(
            ["Status", "Node", "Failures", "Message"],
            (
                [
                    f"{STATUS_ICONS.get(r['status'], '')} {r['status']}",
                    f"`{TEST_HASH.sub('', r['unique_id'].split('.', 2)[-1])}`",
                    r.get("failures") or "",
                    ANSI_ESCAPES.sub("", r.get("message") or "")[:200],
                ]
                for r in problems
            ),
        )
        section += f"\n\n{table}"
    return section


def build_report(environment: str, sections: list[str], run_results_path: Path) -> str:
    parts = [f"### Schema and data quality report · `{environment}`"]
    bq = client() if set(sections) - {"dbt"} else None
    audit = dataset_id(bq.project, environment, "audit") if bq else ""

    def query(sql: str) -> list[dict] | None:
        """Rows, or None when the query fails (never reported as a success)."""
        try:
            return [dict(row.items()) for row in bq.query(sql).result()]
        except Exception as error:  # audit objects may not exist yet
            logger.warning("Report query failed: %s", error)
            return None

    for section in sections:
        if section == "migrations":
            parts.append(
                migrations_section(
                    query(
                        f"select * from `{audit}.deployment_history` "
                        "where script_type in ('V', 'R') limit 15"
                    )
                )
            )
        elif section == "schema":
            parts.append(
                schema_section(
                    query(
                        f"""
                        select
                            table_name, column_name, data_type, first_seen_at,
                            last_seen_at = max(last_seen_at) over () as is_current
                        from `{audit}.audit_schema_snapshots`
                        order by first_seen_at desc, table_name, ordinal_position desc
                        limit 10
                        """
                    )
                )
            )
        elif section == "drift":
            parts.append(
                drift_section(
                    query(
                        f"select * from `{audit}.audit_schema_drift` "
                        "where drift_status != 'aligned' order by table_name, column_name"
                    )
                )
            )
        elif section == "dbt":
            results = json.loads(run_results_path.read_text()) if run_results_path.exists() else {}
            parts.append(dbt_section(results))
        else:
            raise ValueError(f"Unknown section {section!r}")
    return "\n\n".join(parts) + "\n"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sections", default="migrations,schema,drift,dbt")
    parser.add_argument("--run-results", type=Path, default=Path("dbt/target/run_results.json"))
    args = parser.parse_args()

    report = build_report(current_environment(), args.sections.split(","), args.run_results)
    print(report)
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(path).open("a", encoding="utf-8") as handle:
            handle.write(report + "\n")


if __name__ == "__main__":
    main()
