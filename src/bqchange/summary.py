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
    return "\n".join(lines) + "\n"


def write_summary(markdown: str) -> None:
    """Append to $GITHUB_STEP_SUMMARY; no-op outside GitHub Actions."""
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(path).open("a", encoding="utf-8") as handle:
            handle.write(markdown + "\n")
