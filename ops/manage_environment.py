"""Pull request environments: clone an environment's datasets, then drop them when done.

BigQuery has no dataset-level clone, so each table is cloned individually with
CREATE TABLE ... CLONE (copy-on-write: no storage is billed until data changes).
Only BRONZE, AUDIT and META tables are cloned: SILVER/GOLD are rebuilt by dbt,
which defers unmodified models to DEV.

Examples:
    python -m ops.manage_environment clone --source dev --target pr_42
    python -m ops.manage_environment drop --target pr_42
"""

from __future__ import annotations

import argparse
import logging

from google.cloud import bigquery

from ops.environment import LAYERS, client, dataset_id, validate_environment

logger = logging.getLogger(__name__)

CLONED_LAYERS = ("bronze", "audit", "meta")
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

    for layer in LAYERS:
        dataset = bigquery.Dataset(dataset_id(bq.project, target, layer))
        dataset.location = bq.location
        dataset.default_table_expiration_ms = PULL_REQUEST_EXPIRATION_MS
        dataset.labels = {"environment": target, "layer": layer, "managed_by": "ci"}
        bq.create_dataset(dataset, exists_ok=True)

    for layer in CLONED_LAYERS:
        source_dataset = dataset_id(bq.project, source, layer)
        target_dataset = dataset_id(bq.project, target, layer)
        for table in bq.list_tables(source_dataset):
            if table.table_type != "TABLE":
                continue  # views are recreated by repeatable migrations and dbt
            bq.query(
                f"create or replace table `{target_dataset}.{table.table_id}` "
                f"clone `{source_dataset}.{table.table_id}`"
            ).result()
            logger.info("Cloned %s.%s", source_dataset, table.table_id)


def drop_environment(target: str, bq: bigquery.Client | None = None) -> None:
    _require_pull_request(target)
    bq = bq or client()
    for layer in LAYERS:
        bq.delete_dataset(
            dataset_id(bq.project, target, layer), delete_contents=True, not_found_ok=True
        )
        logger.info("Dropped %s_%s", target, layer)


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
