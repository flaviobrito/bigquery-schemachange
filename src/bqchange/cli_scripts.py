"""CLI migration scripts (.cli.yml): command-line steps for what SQL cannot do.

BigQuery DDL covers most changes, but some operations only exist in the bq,
gcloud or gsutil command-line tools (changing clustering of an existing table,
copying tables, loading files, dataset access controls...). A CLI script lists
those commands as steps; it is rendered with Jinja like any SQL script and
follows the same naming, ordering and change history rules.

    # V1.5.0__recluster_orders.cli.yml
    steps:
      - bq update --clustering_fields=order_id,customer_id {{ project }}:{{ layers.bronze }}.orders
      - command: bq show --format=prettyjson {{ project }}:{{ layers.bronze }}.orders

Each step runs without a shell (no pipes, redirects or variable expansion), and
only executables listed in `cli-allowed-commands` may run.
"""

from __future__ import annotations

import logging
import shlex
import shutil
import subprocess
from collections.abc import Callable, Sequence

import yaml

logger = logging.getLogger(__name__)


class CliScriptError(RuntimeError):
    """A CLI script is malformed, uses a forbidden command or a step failed."""


def parse_steps(content: str, allowed: Sequence[str]) -> list[list[str]]:
    """Commands of a rendered .cli.yml script, validated against the allow list."""
    document = yaml.safe_load(content) or {}
    raw_steps = document.get("steps") if isinstance(document, dict) else None
    if not raw_steps or not isinstance(raw_steps, list):
        raise CliScriptError("A CLI script needs a non-empty 'steps' list")
    steps = []
    for index, step in enumerate(raw_steps, start=1):
        command = step.get("command") if isinstance(step, dict) else step
        if not isinstance(command, str) or not command.strip():
            raise CliScriptError(f"Step {index} has no command")
        argv = shlex.split(command)
        if argv[0] not in allowed:
            raise CliScriptError(
                f"Step {index} runs {argv[0]!r}, which is not in "
                f"cli-allowed-commands {list(allowed)}"
            )
        steps.append(argv)
    return steps


def validate(content: str, allowed: Sequence[str]) -> str:
    """Dry run: check the steps and that each executable is installed."""
    steps = parse_steps(content, allowed)
    missing = sorted({argv[0] for argv in steps if shutil.which(argv[0]) is None})
    if missing:
        raise CliScriptError(f"Executable(s) not found on PATH: {missing}")
    return f"{len(steps)} step(s)"


def run(
    content: str,
    allowed: Sequence[str],
    redact: Callable[[object], str] = str,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> None:
    """Run every step in order; stop at the first failure."""
    for index, argv in enumerate(parse_steps(content, allowed), start=1):
        logger.info("STEP  %s: %s", index, redact(shlex.join(argv)))
        result = runner(argv, capture_output=True, text=True, check=False)
        if result.stdout:
            logger.info("%s", redact(result.stdout.strip()))
        if result.returncode != 0:
            raise CliScriptError(
                f"Step {index} failed with exit code {result.returncode}: "
                f"{redact((result.stderr or result.stdout).strip())}"
            )
