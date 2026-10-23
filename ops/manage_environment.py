"""Pull request environments: clone an environment's datasets, then drop them when done.

BigQuery has no dataset-level clone, so each table is cloned individually with
CREATE TABLE ... CLONE (copy-on-write: no storage is billed until data changes).
Layers listed in `pr-clone-layers` of migrations/bqchange.yml are cloned, plus
bqchange's meta dataset. dbt-built layers are rebuilt (unmodified models are
deferred to DEV), and stored test failures are recreated by every dbt run.

Examples:
    python -m ops.manage_environment clone --source dev --target pr_42
    python -m ops.manage_environment drop --target pr_42
"""

from __future__ import annotations

import argparse
import logging

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from ops.environment import client, environment_config, environment_datasets, validate_environment

logger = logging.getLogger(__name__)

# AUDIT tables whose history must carry over; the rest are dbt test failures.
STATEFUL_AUDIT_TABLES = {"audit_schema_snapshots", "load_log"}
PULL_REQUEST_EXPIRATION_MS = 7 * 24 * 60 * 60 * 1000


def _require_pull_request(environment: str) -> str:
    validate_environment(environment)
    if not environment.startswith("pr_"):
        raise ValueError(f"Refusing to modify {environment!r}: only pr_<number> environments")
    return environment


def clone_environment(source: str, target: str, bq: bigquery.Client | None = None) -> None:
    validate_environment(source)
    _require_pull_request(target)
    bq = bq or client()

    # Start from a clean copy: tables left by a previous run of the same pull
    # request would otherwise be compared with DEV's state.
    drop_environment(target, bq)
    target_datasets = environment_datasets(target)
    source_datasets = environment_datasets(source)
    for layer, name in target_datasets.items():
        dataset = bigquery.Dataset(f"{bq.project}.{name}")
        dataset.location = bq.location
        dataset.default_table_expiration_ms = PULL_REQUEST_EXPIRATION_MS
        dataset.labels = {"environment": target, "layer": layer, "managed_by": "ci"}
        bq.create_dataset(dataset, exists_ok=True)

    for layer in [*environment_config(target).pr_clone_layers, "meta"]:
        source_dataset = f"{bq.project}.{source_datasets[layer]}"
        target_dataset = f"{bq.project}.{target_datasets[layer]}"
        for table in bq.list_tables(source_dataset):
            if not should_clone(layer, table.table_id, table.table_type):
                continue
            try:
                bq.query(
                    f"create or replace table `{target_dataset}.{table.table_id}` "
                    f"clone `{source_dataset}.{table.table_id}`"
                ).result()
            except NotFound:
                # A concurrent DEV run may replace tables while we iterate.
                logger.warning("Skipped %s.%s: no longer exists", source_dataset, table.table_id)
                continue
            logger.info("Cloned %s.%s", source_dataset, table.table_id)


def should_clone(layer: str, table_id: str, table_type: str) -> bool:
    if table_type != "TABLE":
        return False  # views are recreated by repeatable migrations and dbt
    return layer != "audit" or table_id in STATEFUL_AUDIT_TABLES


def drop_environment(target: str, bq: bigquery.Client | None = None) -> None:
    _require_pull_request(target)
    bq = bq or client()
    for name in environment_datasets(target).values():
        bq.delete_dataset(f"{bq.project}.{name}", delete_contents=True, not_found_ok=True)
        logger.info("Dropped %s", name)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    clone = subparsers.add_parser("clone")
    clone.add_argument("--source", required=True)
    clone.add_argument("--target", required=True)
    drop = subparsers.add_parser("drop")
    drop.add_argument("--target", required=True)
    args = parser.parse_args()

    if args.command == "clone":
        clone_environment(args.source, args.target)
    else:
        drop_environment(args.target)


if __name__ == "__main__":
    main()
