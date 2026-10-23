"""Command line interface.

    bqchange [global flags] deploy [--dry-run] [--out-of-order]
    bqchange [global flags] render <script relative to root-folder>
    bqchange [global flags] verify
    bqchange [global flags] record-schema --source migration|dbt|manual

Global flags override BQCHANGE_* environment variables, which override the YAML file.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from bqchange import __version__
from bqchange.config import load_config
from bqchange.deploy import MigrationError, deploy
from bqchange.render import Renderer
from bqchange.schema_log import SOURCES, SchemaLog
from bqchange.secrets import Redactor
from bqchange.summary import render_schema_changes, write_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bqchange", description="Migrations for BigQuery.")
    parser.add_argument("--version", action="version", version=f"bqchange {__version__}")
    parser.add_argument("--config", type=Path, default=Path("migrations/bqchange.yml"))
    parser.add_argument("--log-level", default="INFO")
    flags = parser.add_argument_group(
        "configuration overrides", "Take precedence over BQCHANGE_* variables and the YAML file"
    )
    flags.add_argument("--project", help="GCP project (BQCHANGE_PROJECT)")
    flags.add_argument("--location", help="BigQuery location (BQCHANGE_LOCATION)")
    flags.add_argument("--root-folder", help="Scripts folder (BQCHANGE_ROOT_FOLDER)")
    flags.add_argument("--modules-folder", help="Jinja modules folder (BQCHANGE_MODULES_FOLDER)")
    flags.add_argument(
        "--change-history-table",
        help="dataset.table of the change history (BQCHANGE_CHANGE_HISTORY_TABLE)",
    )
    flags.add_argument(
        "--maximum-bytes-billed",
        type=int,
        help="Per-job billing cap (BQCHANGE_MAXIMUM_BYTES_BILLED)",
    )
    flags.add_argument(
        "--vars",
        type=json.loads,
        help='JSON merged into vars, e.g. \'{"env": "dev"}\' (BQCHANGE_VARS)',
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    deploy_parser = subcommands.add_parser("deploy", help="Apply pending scripts")
    deploy_parser.add_argument(
        "--dry-run", action="store_true", help="Validate pending scripts without changing anything"
    )
    deploy_parser.add_argument("--out-of-order", action="store_true")

    render_parser = subcommands.add_parser(
        "render", help="Print a rendered script (secrets masked)"
    )
    render_parser.add_argument("script", help="Path relative to root-folder")

    subcommands.add_parser(
        "verify", help="Show the resolved configuration and check credentials and permissions"
    )

    record_parser = subcommands.add_parser(
        "record-schema", help="Log schema changes of the monitored datasets since the last snapshot"
    )
    record_parser.add_argument("--source", required=True, choices=SOURCES)
    record_parser.add_argument(
        "--ignore-missing-tables",
        action="store_true",
        help="Do not report tables absent from this environment as removed (pull request CI)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=args.log_level.upper(), format="%(levelname)-7s %(message)s")
    overrides = {
        "project": args.project,
        "location": args.location,
        "root-folder": args.root_folder,
        "modules-folder": args.modules_folder,
        "change-history-table": args.change_history_table,
        "maximum-bytes-billed": args.maximum_bytes_billed,
        "vars": args.vars,
    }
    try:
        config = load_config(args.config, overrides=overrides)
    except ValueError as error:
        logging.error("%s", error)
        return 2
    redact = Redactor(config.secrets)
    redact.install()

    if args.command == "render":
        print(redact(Renderer.from_config(config).render(args.script, config.variables)))
        return 0

    from bqchange.executor import BigQueryExecutor

    executor = BigQueryExecutor(config)
    if args.command == "verify":
        from bqchange.verify import format_report, run_checks

        checks = run_checks(config, executor)
        print(format_report(config, checks, redact))
        return 1 if any(c.status == "fail" for c in checks) else 0

    if args.command == "record-schema":
        log = SchemaLog(executor, config.project, config.meta_dataset, config.schema_log_datasets)
        changes = log.record(args.source, args.ignore_missing_tables)
        logging.info("Recorded %s schema change(s) from %s", len(changes), args.source)
        write_summary(
            redact(render_schema_changes(args.source, config.vars.get("env", ""), changes))
        )
        return 0

    try:
        deploy(config, executor, dry_run=args.dry_run, out_of_order=args.out_of_order)
    except MigrationError as error:
        logging.error("%s", redact(error))
        write_summary(f"### bqchange · `{config.vars.get('env', '')}`\n\n❌ {redact(error)}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
