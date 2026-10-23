"""Plan and apply pending migrations."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from bqchange.config import Config
from bqchange.executor import Executor
from bqchange.history import AppliedScript, ChangeHistory
from bqchange.render import Renderer, checksum
from bqchange.schema_log import SchemaLog
from bqchange.scripts import Script, ScriptType, discover, parse_version
from bqchange.summary import SummaryRow, render_summary, write_summary

logger = logging.getLogger(__name__)


class MigrationError(RuntimeError):
    """The scripts on disk are inconsistent with the change history."""


@dataclass(frozen=True)
class PendingScript:
    script: Script
    content: str
    checksum: str
    reason: str


@dataclass(frozen=True)
class ChecksumUpgrade:
    """A versioned script recorded with a checksum of its *rendered* content.

    Versioned checksums are computed on the raw file so they are identical in
    every environment (rendered SQL contains the environment's dataset names,
    which made clones look modified). Rows written before that change are
    recognised and rewritten once.
    """

    script: str
    old: str
    new: str


@dataclass(frozen=True)
class Plan:
    pending: list[PendingScript]
    checksum_upgrades: list[ChecksumUpgrade]


def plan(
    scripts: list[Script],
    applied: list[AppliedScript],
    renderer: Renderer,
    variables: dict,
    out_of_order: bool = False,
) -> Plan:
    applied_by_name = {row.script: row for row in applied}
    applied_versions = [
        parse_version(row.version) for row in applied if row.script_type == "V" and row.version
    ]
    max_applied = max(applied_versions, default=())

    pending: list[PendingScript] = []
    upgrades: list[ChecksumUpgrade] = []
    for script in scripts:
        content = renderer.render(script.relative_path, variables)
        previous = applied_by_name.get(script.name)

        if script.script_type is ScriptType.VERSIONED:
            digest = checksum(renderer.source(script.relative_path))
            if previous:
                if previous.checksum == checksum(content) != digest:
                    upgrades.append(ChecksumUpgrade(script.name, previous.checksum, digest))
                elif previous.checksum != digest:
                    raise MigrationError(
                        f"{script.name} was already applied and has been modified. "
                        "Versioned scripts are immutable: add a new version instead."
                    )
                continue
            if script.version_key < max_applied and not out_of_order:
                raise MigrationError(
                    f"{script.name} is older than the latest applied version "
                    f"{'.'.join(map(str, max_applied))}. Use --out-of-order to apply it."
                )
            pending.append(PendingScript(script, content, digest, "new version"))
            continue

        digest = checksum(content)
        if script.script_type is ScriptType.REPEATABLE:
            if previous is None:
                pending.append(PendingScript(script, content, digest, "new repeatable"))
            elif previous.checksum != digest:
                pending.append(PendingScript(script, content, digest, "content changed"))
        else:
            pending.append(PendingScript(script, content, digest, "always"))
    return Plan(pending, upgrades)


def deploy(
    config: Config,
    executor: Executor,
    dry_run: bool = False,
    out_of_order: bool = False,
) -> list[PendingScript]:
    history = ChangeHistory(executor, config.change_history_table)
    if config.create_change_history_table and not dry_run:
        history.ensure(config.change_history_dataset)
        if config.schema_log_datasets:
            # Repeatable scripts may build views over the schema change log.
            meta_dataset = config.change_history_dataset.split(".", 1)[1]
            SchemaLog(executor, config.project, meta_dataset, config.schema_log_datasets).ensure()

    try:
        applied = history.applied()
    except Exception:
        if not dry_run:
            raise
        logger.info("Change history table not found: every script is pending")
        applied = []

    renderer = Renderer.from_config(config)
    variables = {"project": config.project, "location": config.location, **config.vars}
    result = plan(discover(config.root_folder), applied, renderer, variables, out_of_order)
    pending = result.pending
    for upgrade in result.checksum_upgrades:
        if dry_run:
            logger.info("PLAN  %s - legacy checksum will be upgraded", upgrade.script)
        else:
            history.update_checksum(upgrade.script, upgrade.old, upgrade.new)
            logger.info("UPGRADE checksum of %s", upgrade.script)

    environment = str(config.vars.get("env", config.change_history_dataset))
    title = "bqchange plan (dry run)" if dry_run else "bqchange deploy"
    rows: list[SummaryRow] = []

    if not pending:
        logger.info("Nothing to deploy: %s is up to date", config.change_history_table)
        write_summary(render_summary(title, environment, rows))
        return pending

    failed_validation = False
    for index, item in enumerate(pending):
        row = {
            "script": item.script.relative_path,
            "script_type": item.script.script_type.value,
            "reason": item.reason,
        }
        label = f"{item.script.relative_path} ({item.reason})"
        if dry_run:
            result = executor.dry_run(item.content)
            if result.ok:
                logger.info("PLAN  %s - valid, %s bytes", label, f"{result.bytes_processed:,}")
                outcome = f"✅ valid ({result.bytes_processed:,} bytes)"
            elif index > 0:
                # Earlier pending scripts may create the objects this one references.
                logger.warning("PLAN  %s - not validated yet: %s", label, result.error)
                outcome = "⏳ depends on an earlier pending script"
            else:
                logger.error("PLAN  %s - invalid: %s", label, result.error)
                outcome = f"❌ invalid: {result.error}"
                failed_validation = True
            rows.append(SummaryRow(**row, outcome=outcome))
            continue

        started = time.monotonic()
        logger.info("APPLY %s", label)
        try:
            executor.execute(item.content)
        except Exception as error:
            rows.append(SummaryRow(**row, outcome=f"❌ failed: {error}"))
            write_summary(render_summary(title, environment, rows))
            raise
        elapsed_ms = int((time.monotonic() - started) * 1000)
        history.record(
            script=item.script.name,
            script_type=item.script.script_type.value,
            version=item.script.version,
            description=item.script.description,
            checksum=item.checksum,
            execution_time_ms=elapsed_ms,
        )
        rows.append(SummaryRow(**row, outcome=f"✅ applied in {elapsed_ms:,} ms"))

    write_summary(render_summary(title, environment, rows))
    if failed_validation:
        raise MigrationError("Dry run found invalid scripts")
    return pending
