"""Post the schema changes of the current workflow run as a pull request comment.

Reads the rows this run wrote to <env>_meta.schema_change_log and keeps one
comment per pull request and environment up to date (edited, not duplicated),
so reviewers see schema changes in the pull request conversation instead of
opening the Actions run.

Examples (in GitHub Actions):
    python -m ops.schema_comment --title "Schema changes in this pull request"
    python -m ops.schema_comment --title "Deployed to PROD" --pull-request "$PR_NUMBER"
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys

from ops.environment import client, current_environment, dataset_id
from ops.report import markdown_table

logger = logging.getLogger(__name__)

LABELS = {
    "added": "column added",
    "removed": "column removed",
    "type_changed": "type changed",
    "property_added": "property added",
    "property_removed": "property removed",
    "property_changed": "property changed",
}


def run_url() -> str | None:
    run_id = os.environ.get("GITHUB_RUN_ID")
    if not run_id:
        return None
    return (
        f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{run_id}"
    )


def fetch_changes(environment: str, url: str) -> list[dict]:
    bq = client()
    log = f"{dataset_id(bq.project, environment, 'meta')}.schema_change_log"
    rows = bq.query(
        f"""
        select source, change_type, layer, table_name, column_name, property,
            coalesce(old_data_type, old_value) as old_value,
            coalesce(new_data_type, new_value) as new_value
        from `{log}`
        where run_url = '{url}' and change_type != 'baseline'
        order by changed_at, layer, table_name, column_name
        """
    ).result()
    return [dict(row.items()) for row in rows]


def short(value: object, limit: int = 60) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def build_comment(title: str, environment: str, changes: list[dict], url: str | None) -> str:
    marker = f"<!-- bqchange-schema-changes:{environment} -->"
    lines = [marker, f"### {title} · `{environment}`", ""]
    if not changes:
        lines.append("No schema change.")
    else:
        lines.append(
            markdown_table(
                ["Source", "Layer", "Table", "Column", "Change", "Before", "After"],
                (
                    [
                        c["source"],
                        (c.get("layer") or "").upper(),
                        c["table_name"],
                        f"`{c['column_name']}`",
                        LABELS.get(c["change_type"], c["change_type"])
                        + (f" ({c['property']})" if c.get("property") else ""),
                        short(c.get("old_value")),
                        short(c.get("new_value")),
                    ]
                    for c in changes
                ),
            )
        )
    if url:
        lines += ["", f"Recorded by bqchange in [this run]({url})."]
    return "\n".join(lines) + "\n"


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def upsert_comment(pull_request: str, body: str) -> None:
    """Edit this environment's previous comment if there is one, otherwise create it."""
    repo = os.environ["GITHUB_REPOSITORY"]
    marker = body.splitlines()[0]
    comments = json.loads(gh("api", f"repos/{repo}/issues/{pull_request}/comments", "--paginate"))
    existing = next((c for c in comments if c["body"].startswith(marker)), None)
    if existing:
        gh(
            "api",
            "-X",
            "PATCH",
            f"repos/{repo}/issues/comments/{existing['id']}",
            "-f",
            f"body={body}",
        )
        logger.info("Updated comment %s on pull request #%s", existing["id"], pull_request)
    else:
        gh("api", f"repos/{repo}/issues/{pull_request}/comments", "-f", f"body={body}")
        logger.info("Commented on pull request #%s", pull_request)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", default="Schema changes")
    parser.add_argument(
        "--pull-request",
        default=os.environ.get("PR_NUMBER") or os.environ.get("GITHUB_PR_NUMBER"),
        help="Pull request number (defaults to PR_NUMBER)",
    )
    args = parser.parse_args()

    url = run_url()
    if not url:
        logger.error("GITHUB_RUN_ID is not set: run this inside GitHub Actions")
        return 1
    environment = current_environment()
    body = build_comment(args.title, environment, fetch_changes(environment, url), url)
    print(body)
    if args.pull_request:
        upsert_comment(args.pull_request, body)
    else:
        logger.info("No pull request for this commit: nothing to comment")
    return 0


if __name__ == "__main__":
    sys.exit(main())
