"""Command line interface.

bqchange deploy [--config migrations/bqchange.yml] [--dry-run] [--out-of-order]
bqchange render <script relative to root-folder> [--config ...]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from bqchange import __version__
from bqchange.config import load_config
from bqchange.deploy import MigrationError, deploy
from bqchange.render import Renderer
from bqchange.schema_log import SOURCES, SchemaLog
from bqchange.summary import render_schema_changes, write_summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bqchange", description="Migrations for BigQuery.")
    parser.add_argument("--version", action="version", version=f"bqchange {__version__}")
    parser.add_argument("--config", type=Path, default=Path("migrations/bqchange.yml"))
    parser.add_argument("--log-level", default="INFO")
    subcommands = parser.add_subparsers(dest="command", required=True)

    deploy_parser = subcommands.add_parser("deploy", help="Apply pending scripts")
    deploy_parser.add_argument(
        "--dry-run", action="store_true", help="Validate pending scripts with BigQuery dry runs"
    )
    deploy_parser.add_argument("--out-of-order", action="store_true")

    render_parser = subcommands.add_parser("render", help="Print a rendered script")
    render_parser.add_argument("script", help="Path relative to root-folder")

    record_parser = subcommands.add_parser(
        "record-schema", help="Log column-level schema changes since the last snapshot"
    )
    record_parser.add_argument("--source", required=True, choices=SOURCES)

    args = parser.parse_args(argv)
    logging.basicConfig(level=args.log_level.upper(), format="%(levelname)-7s %(message)s")
    config = load_config(args.config)

    if args.command == "render":
        variables = {"project": config.project, "location": config.location, **config.vars}
        print(Renderer.from_config(config).render(args.script, variables))
        return 0

    from bqchange.executor import BigQueryExecutor

    if args.command == "record-schema":
        log = SchemaLog(
            BigQueryExecutor(config),
            config.project,
            config.change_history_dataset.split(".", 1)[1],
            config.schema_log_datasets,
        )
        changes = log.record(args.source)
        logging.info("Recorded %s schema change(s) from %s", len(changes), args.source)
        write_summary(render_schema_changes(args.source, config.vars.get("env", ""), changes))
        return 0

    try:
        deploy(
            config, BigQueryExecutor(config), dry_run=args.dry_run, out_of_order=args.out_of_order
        )
    except MigrationError as error:
        logging.error("%s", error)
        write_summary(f"### bqchange · `{config.vars.get('env', '')}`\n\n❌ {error}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
