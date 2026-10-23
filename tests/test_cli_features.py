import logging
import subprocess
from pathlib import Path

import pytest

from bqchange import cli_scripts
from bqchange.cli import main
from bqchange.config import load_config
from bqchange.deploy import deploy
from bqchange.scripts import discover
from bqchange.secrets import MASK, Redactor, collect_secrets
from bqchange.verify import Check, format_report, run_checks

CONFIG = """project: "{{ env_var('GCP_PROJECT_ID', 'yaml-project') }}"
location: US
root-folder: scripts
change-history-table: dev_meta.change_history
layers:
  raw: dev_raw
vars:
  env: dev
  api_secret: s3cr3t-value
  secrets:
    webhook: https://hooks.example.com/abc123
"""


@pytest.fixture
def project(tmp_path: Path, monkeypatch) -> Path:
    for name in ("GCP_PROJECT_ID", "BQCHANGE_PROJECT", "BQCHANGE_VARS", "BQCHANGE_LOCATION"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "bqchange.yml").write_text(CONFIG)
    (tmp_path / "scripts" / "V1.0.0__token.sql").write_text(
        "select '{{ api_secret }}' as token, '{{ secrets.webhook }}' as hook"
    )
    return tmp_path


# --- secret masking ------------------------------------------------------------------


def test_secrets_are_found_by_name_and_under_a_secrets_key():
    found = collect_secrets(
        {"env": "dev", "API_SECRET": "a1", "nested": {"db_secret": "b2"}, "secrets": {"x": "c3"}}
    )
    assert found == {"a1", "b2", "c3"}


def test_redactor_masks_every_secret_in_text():
    redact = Redactor({"s3cr3t", "abc"})
    assert redact("token=s3cr3t url=/abc/") == f"token={MASK} url=/{MASK}/"


def test_redactor_masks_log_records(caplog):
    redact = Redactor({"s3cr3t"})
    logging.basicConfig()
    redact.install()
    handler = logging.getLogger().handlers[0]
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "value %s", ("s3cr3t",), None)
    for log_filter in handler.filters:
        log_filter.filter(record)
    assert record.getMessage() == f"value {MASK}"


def test_render_never_prints_secrets(project, capsys, monkeypatch):
    monkeypatch.chdir(project)
    assert main(["--config", "bqchange.yml", "render", "V1.0.0__token.sql"]) == 0
    out = capsys.readouterr().out
    assert "s3cr3t-value" not in out and "abc123" not in out
    assert out.count(MASK) == 2


# --- configuration precedence ---------------------------------------------------------


def test_cli_flags_override_environment_which_overrides_yaml(project, monkeypatch):
    config_file = project / "bqchange.yml"
    assert load_config(config_file).project == "yaml-project"

    monkeypatch.setenv("BQCHANGE_PROJECT", "env-project")
    monkeypatch.setenv("BQCHANGE_VARS", '{"env": "prod", "extra": "1"}')
    config = load_config(config_file)
    assert config.project == "env-project"
    assert config.vars["env"] == "prod" and config.vars["extra"] == "1"

    config = load_config(config_file, overrides={"project": "cli-project", "vars": {"env": "pr_1"}})
    assert config.project == "cli-project"
    assert config.vars["env"] == "pr_1"


def test_yaml_file_is_optional_when_flags_provide_the_essentials(tmp_path):
    config = load_config(
        tmp_path / "missing.yml",
        overrides={"project": "p", "change-history-table": "m.change_history"},
    )
    assert config.change_history_table == "p.m.change_history"


def test_missing_essentials_explain_how_to_set_them(tmp_path):
    with pytest.raises(ValueError, match="BQCHANGE_"):
        load_config(tmp_path / "missing.yml")


# --- CLI migration scripts ------------------------------------------------------------

CLI_SCRIPT = """steps:
  - bq update --clustering_fields=order_id,customer_id p:dev_raw.orders
  - command: bq show p:dev_raw.orders
"""


def test_cli_scripts_are_discovered_with_the_same_naming(tmp_path):
    (tmp_path / "V1.5.0__recluster_orders.cli.yml").write_text(CLI_SCRIPT)
    (tmp_path / "R__refresh.cli.yml").write_text(CLI_SCRIPT)
    scripts = {s.name: s for s in discover(tmp_path)}
    assert scripts["V1.5.0__recluster_orders.cli.yml"].is_cli
    assert scripts["V1.5.0__recluster_orders.cli.yml"].version == "1.5.0"
    assert scripts["R__refresh.cli.yml"].description == "refresh"


def test_cli_steps_are_parsed_without_a_shell():
    steps = cli_scripts.parse_steps(CLI_SCRIPT, ["bq"])
    assert steps[0] == [
        "bq",
        "update",
        "--clustering_fields=order_id,customer_id",
        "p:dev_raw.orders",
    ]
    assert steps[1][:2] == ["bq", "show"]


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("steps:\n  - rm -rf /\n", "not in cli-allowed-commands"),
        ("steps: []\n", "non-empty 'steps'"),
        ("steps:\n  - command: ''\n", "has no command"),
    ],
)
def test_invalid_cli_scripts_are_rejected(content, message):
    with pytest.raises(cli_scripts.CliScriptError, match=message):
        cli_scripts.parse_steps(content, ["bq", "gcloud", "gsutil"])


def test_cli_run_stops_at_the_first_failure_and_masks_secrets():
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 1, "", "bad token s3cr3t")

    with pytest.raises(cli_scripts.CliScriptError) as error:
        cli_scripts.run(CLI_SCRIPT, ["bq"], Redactor({"s3cr3t"}), runner)
    assert len(calls) == 1
    assert "s3cr3t" not in str(error.value) and MASK in str(error.value)


class RecordingExecutor:
    def __init__(self):
        self.executed, self.recorded = [], []

    def execute(self, sql, params=None):
        (self.recorded if params and "checksum" in params else self.executed).append(params or sql)

    def query(self, sql):
        return []

    def dry_run(self, sql):
        raise AssertionError("CLI scripts are not sent to BigQuery")

    def ensure_dataset(self, dataset_id):
        pass


def test_deploy_runs_cli_scripts_and_records_them(project, monkeypatch):
    (project / "scripts" / "V1.0.0__token.sql").unlink()
    (project / "scripts" / "V1.1.0__recluster.cli.yml").write_text(CLI_SCRIPT)
    ran = []
    monkeypatch.setattr(cli_scripts, "run", lambda content, allowed, redact: ran.append(content))
    executor = RecordingExecutor()
    deploy(load_config(project / "bqchange.yml"), executor)
    assert ran and "bq update" in ran[0]
    assert [r["script"] for r in executor.recorded] == ["V1.1.0__recluster.cli.yml"]


def test_dry_run_validates_cli_scripts_without_running_them(project, monkeypatch):
    (project / "scripts" / "V1.0.0__token.sql").unlink()
    (project / "scripts" / "V1.1.0__recluster.cli.yml").write_text(CLI_SCRIPT)
    monkeypatch.setattr(cli_scripts.shutil, "which", lambda name: f"/usr/bin/{name}")
    pending = deploy(load_config(project / "bqchange.yml"), RecordingExecutor(), dry_run=True)
    assert [p.script.name for p in pending] == ["V1.1.0__recluster.cli.yml"]


# --- verify ---------------------------------------------------------------------------


class FakeVerifyClient:
    def __init__(self, datasets=(), tables=(), jobs=True):
        self.datasets, self.tables, self.jobs = set(datasets), set(tables), jobs

    def principal(self):
        return "service account ci@p.iam.gserviceaccount.com"

    def can_run_jobs(self):
        return (True, "dry-run job in p") if self.jobs else (False, "Access Denied")

    def dataset_exists(self, dataset_id):
        return dataset_id in self.datasets

    def table_exists(self, table_id):
        return table_id in self.tables


def test_verify_reports_ok_warnings_and_failures(project):
    config = load_config(project / "bqchange.yml")
    checks = {c.name: c for c in run_checks(config, FakeVerifyClient(jobs=False))}
    assert checks["credentials"].status == "ok"
    assert checks["run jobs"].status == "fail"
    assert checks["layer raw"].status == "warn"
    assert checks["change history"].status == "warn"

    ready = FakeVerifyClient(
        datasets={"yaml-project.dev_raw"}, tables={config.change_history_table}
    )
    assert all(c.status == "ok" for c in run_checks(config, ready))


def test_verify_report_masks_secrets(project):
    config = load_config(project / "bqchange.yml")
    report = format_report(config, [Check("credentials", "ok", "x")], Redactor(config.secrets))
    assert "s3cr3t-value" not in report and "abc123" not in report
    assert MASK in report
