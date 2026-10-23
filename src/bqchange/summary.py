"""Markdown run summary, appended to the GitHub Actions job summary when available."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SummaryRow:
    script: str
    script_type: str
    reason: str
    outcome: str
    diff: str | None = None


def render_summary(title: str, environment: str, rows: list[SummaryRow]) -> str:
    lines = [f"### {title} · `{environment}`", ""]
    if not rows:
        lines.append("Nothing to deploy: the environment is up to date.")
        return "\n".join(lines) + "\n"
    lines += ["| Script | Type | Reason | Outcome |", "| --- | --- | --- | --- |"]
    labels = {"V": "versioned", "R": "repeatable", "A": "always"}
    for row in rows:
        lines.append(
            f"| `{row.script}` | {labels.get(row.script_type, row.script_type)} "
            f"| {row.reason} | {row.outcome} |"
        )
    # What changed in each edited file, collapsed so the table stays readable.
    for row in rows:
        if row.diff:
            lines += [
                "",
                f"<details><summary>View changes in <code>{row.script}</code></summary>",
                "",
                "```diff",
                row.diff,
                "```",
                "",
                "</details>",
            ]
    return "\n".join(lines) + "\n"


def write_summary(markdown: str) -> None:
    """Append to $GITHUB_STEP_SUMMARY; no-op outside GitHub Actions."""
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(path).open("a", encoding="utf-8") as handle:
            handle.write(markdown + "\n")


def render_schema_changes(source: str, environment: str, changes: list) -> str:
    """Markdown table of the schema changes recorded by `bqchange record-schema`."""
    title = f"### Schema changes recorded ({source}) · `{environment}`"
    if not changes:
        return f"{title}\n\nNo schema change.\n"
    if all(c.change_type.value == "baseline" for c in changes):
        return f"{title}\n\nBaseline snapshot of {len(changes)} columns recorded.\n"
    labels = {
        "added": "added",
        "removed": "removed",
        "type_changed": "type changed",
        "property_added": "property added",
        "property_removed": "property removed",
        "property_changed": "property changed",
    }
    lines = [
        title,
        "",
        "| Layer | Table | Column | Change | Property | Before | After |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for c in changes:
        layer = c.layer.upper()
        change = labels.get(c.change_type.value, c.change_type.value)
        before = c.old_value if c.property else c.old_data_type
        after = c.new_value if c.property else c.new_data_type
        lines.append(
            f"| {layer} | {c.table_name} | `{c.column_name}` | {change} | {c.property or ''} "
            f"| {_cell(before)} | {_cell(after)} |"
        )
    return "\n".join(lines) + "\n"


def _cell(value: str | None, limit: int = 80) -> str:
    """Short, table-safe rendering of a property value."""
    if value is None:
        return ""
    text = value.replace("|", "\\|").replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"
