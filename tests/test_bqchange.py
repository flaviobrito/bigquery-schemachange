from pathlib import Path

import pytest

from bqchange.config import load_config
from bqchange.deploy import MigrationError, deploy, plan
from bqchange.executor import DryRunResult
from bqchange.history import AppliedScript
from bqchange.render import Renderer, checksum
from bqchange.scripts import ScriptType, discover, parse_version


class FakeExecutor:
    """Records statements and serves change history rows from memory."""

    def __init__(self, applied=None, dry_run_errors=None):
        self.applied_rows = [row.__dict__ for row in applied or []]
        self.dry_run_errors = dry_run_errors or {}
        self.executed: list[str] = []
        self.recorded: list[dict] = []
        self.datasets: list[str] = []
        self.upgrades: list[dict] = []
        self.backfills: list[dict] = []

    def execute(self, sql, params=None):
        if params and "new" in params:
            self.upgrades.append(params)
        elif (
            params
            and "script_source" in params
            and "checksum" in params
            and "version" not in params
        ):
            self.backfills.append(params)
        elif params and "checksum" in params:
            self.recorded.append(params)
        else:
            self.executed.append(sql)

    def query(self, sql):
        return self.applied_rows

    def dry_run(self, sql):
        for marker, error in self.dry_run_errors.items():
            if marker in sql:
                return DryRunResult(ok=False, error=error)
        return DryRunResult(ok=True, bytes_processed=10)

    def ensure_dataset(self, dataset_id):
        self.datasets.append(dataset_id)


@pytest.fixture
def project(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    monkeypatch.setenv("BQ_ENV", "dev")
    scripts = tmp_path / "scripts"
    (scripts / "versioned").mkdir(parents=True)
    (scripts / "repeatable").mkdir()
    (scripts / "always").mkdir()
    (tmp_path / "modules").mkdir()
    (tmp_path / "modules" / "common.sql").write_text("{% macro label() %}'demo'{% endmacro %}")
    (scripts / "versioned" / "V1.0.0__first.sql").write_text("create schema `{{ env }}_a`")
    (scripts / "versioned" / "V1.10.0__tenth.sql").write_text("select 10")
    (scripts / "versioned" / "V1.2.0__second.sql").write_text(
        '{% import "modules/common.sql" as common %}select {{ common.label() }}'
    )
    (scripts / "repeatable" / "R__views.sql").write_text("create or replace view v as select 1")
    (scripts / "always" / "A__grants.sql").write_text("select '{{ env }}'")
    (tmp_path / "bqchange.yml").write_text(
        "project: \"{{ env_var('GCP_PROJECT_ID') }}\"\n"
        "root-folder: scripts\n"
        "modules-folder: modules\n"
        "change-history-table: \"{{ env_var('BQ_ENV') }}_meta.change_history\"\n"
        "vars:\n  env: \"{{ env_var('BQ_ENV') }}\"\n"
    )
    return tmp_path


def applied_from(
    project: Path, *names: str, checksum_override: str | None = None, legacy: bool = False
):
    config = load_config(project / "bqchange.yml")
    renderer = Renderer.from_config(config)
    variables = {"project": config.project, "location": config.location, **config.vars}
    rows = []
    for script in discover(config.root_folder):
        if script.name in names:
            content = renderer.render(script.relative_path, variables)
            if script.script_type is ScriptType.VERSIONED and not legacy:
                content = renderer.source(script.relative_path)
            rows.append(
                AppliedScript(
                    script=script.name,
                    script_type=script.script_type.value,
                    version=script.version,
                    checksum=checksum_override or checksum(content),
                )
            )
    return rows


def test_config_resolves_env_vars_and_qualifies_history_table(project):
    config = load_config(project / "bqchange.yml")
    assert config.change_history_table == "test-project.dev_meta.change_history"
    assert config.change_history_dataset == "test-project.dev_meta"
    assert config.vars == {"env": "dev"}
    assert config.location == "US"


def test_missing_env_var_fails_fast(project, monkeypatch):
    monkeypatch.delenv("BQ_ENV")
    with pytest.raises(ValueError, match="BQ_ENV"):
        load_config(project / "bqchange.yml")


def test_discovery_orders_versions_numerically_then_repeatable_then_always(project):
    names = [s.name for s in discover(project / "scripts")]
    assert names == [
        "V1.0.0__first.sql",
        "V1.2.0__second.sql",
        "V1.10.0__tenth.sql",
        "R__views.sql",
        "A__grants.sql",
    ]


def test_discovery_rejects_duplicate_versions(project):
    (project / "scripts" / "versioned" / "V1.0__duplicate.sql").write_text("select 1")
    (project / "scripts" / "versioned" / "V1_0__again.sql").write_text("select 1")
    with pytest.raises(ValueError, match="Duplicate versions"):
        discover(project / "scripts")


def test_parse_version_accepts_dots_and_underscores():
    assert parse_version("1.2_3") == (1, 2, 3)


def test_fresh_environment_applies_everything_in_order(project):
    executor = FakeExecutor()
    deploy(load_config(project / "bqchange.yml"), executor)

    assert executor.datasets == ["test-project.dev_meta"]
    applied = [row["script"] for row in executor.recorded]
    assert applied == [
        "V1.0.0__first.sql",
        "V1.2.0__second.sql",
        "V1.10.0__tenth.sql",
        "R__views.sql",
        "A__grants.sql",
    ]
    assert "create schema `dev_a`" in executor.executed
    assert "select 'demo'" in executor.executed


def test_up_to_date_environment_only_runs_always_scripts(project):
    applied = applied_from(
        project, "V1.0.0__first.sql", "V1.2.0__second.sql", "V1.10.0__tenth.sql", "R__views.sql"
    )
    executor = FakeExecutor(applied)
    deploy(load_config(project / "bqchange.yml"), executor)
    assert [row["script"] for row in executor.recorded] == ["A__grants.sql"]


def test_changed_repeatable_script_is_reapplied(project):
    applied = applied_from(project, "V1.0.0__first.sql", "V1.2.0__second.sql", "V1.10.0__tenth.sql")
    applied.append(AppliedScript("R__views.sql", "R", None, "old-checksum"))
    config = load_config(project / "bqchange.yml")
    pending = plan(
        discover(config.root_folder),
        applied,
        Renderer.from_config(config),
        {"project": config.project, "location": config.location, **config.vars},
    ).pending
    assert [(p.script.name, p.reason) for p in pending] == [
        ("R__views.sql", "content changed"),
        ("A__grants.sql", "always"),
    ]


def test_modified_versioned_script_is_rejected(project):
    applied = applied_from(project, "V1.0.0__first.sql", checksum_override="tampered")
    with pytest.raises(MigrationError, match="immutable"):
        deploy(load_config(project / "bqchange.yml"), FakeExecutor(applied))


def test_out_of_order_version_requires_flag(project):
    applied = applied_from(project, "V1.0.0__first.sql", "V1.10.0__tenth.sql")
    config = load_config(project / "bqchange.yml")
    with pytest.raises(MigrationError, match="out-of-order"):
        deploy(config, FakeExecutor(applied))

    executor = FakeExecutor(applied)
    deploy(config, executor, out_of_order=True)
    assert executor.recorded[0]["script"] == "V1.2.0__second.sql"


def test_dry_run_executes_nothing_and_reports_invalid_first_script(project):
    executor = FakeExecutor(dry_run_errors={"create schema": "Syntax error"})
    with pytest.raises(MigrationError, match="invalid"):
        deploy(load_config(project / "bqchange.yml"), executor, dry_run=True)
    assert executor.executed == []
    assert executor.recorded == []
    assert executor.datasets == []


def test_dry_run_tolerates_errors_caused_by_earlier_pending_scripts(project):
    executor = FakeExecutor(dry_run_errors={"select 10": "Not found: Dataset dev_a"})
    pending = deploy(load_config(project / "bqchange.yml"), executor, dry_run=True)
    assert len(pending) == 5


def test_script_types(project):
    types = {s.name: s.script_type for s in discover(project / "scripts")}
    assert types["R__views.sql"] is ScriptType.REPEATABLE
    assert types["A__grants.sql"] is ScriptType.ALWAYS


def test_deploy_writes_github_job_summary(project, tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    deploy(load_config(project / "bqchange.yml"), FakeExecutor())

    content = summary.read_text()
    assert "### bqchange deploy · `dev`" in content
    assert "| `versioned/V1.0.0__first.sql` | versioned | new version | ✅ applied" in content
    assert "| `always/A__grants.sql` | always | always |" in content


def test_dry_run_summary_marks_dependent_scripts(project, tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    executor = FakeExecutor(dry_run_errors={"select 10": "Not found"})
    deploy(load_config(project / "bqchange.yml"), executor, dry_run=True)
    assert "⏳ depends on an earlier pending script" in summary.read_text()


def test_versioned_checksums_do_not_depend_on_the_environment(project, monkeypatch):
    """A pull request clone inherits DEV's history but renders pr_1 dataset names."""
    applied = applied_from(
        project, "V1.0.0__first.sql", "V1.2.0__second.sql", "V1.10.0__tenth.sql", "R__views.sql"
    )
    monkeypatch.setenv("BQ_ENV", "pr_1")
    executor = FakeExecutor(applied)
    deploy(load_config(project / "bqchange.yml"), executor)
    assert [row["script"] for row in executor.recorded] == ["A__grants.sql"]


def test_editing_the_raw_file_is_still_rejected_in_any_environment(project, monkeypatch):
    applied = applied_from(project, "V1.0.0__first.sql")
    (project / "scripts" / "versioned" / "V1.0.0__first.sql").write_text("create schema `x`")
    monkeypatch.setenv("BQ_ENV", "pr_1")
    with pytest.raises(MigrationError, match="immutable"):
        deploy(load_config(project / "bqchange.yml"), FakeExecutor(applied))


def test_legacy_rendered_checksums_are_upgraded_once(project):
    applied = applied_from(
        project,
        "V1.0.0__first.sql",
        "V1.2.0__second.sql",
        "V1.10.0__tenth.sql",
        "R__views.sql",
        legacy=True,
    )
    executor = FakeExecutor(applied)
    deploy(load_config(project / "bqchange.yml"), executor)

    # V1.10.0 has no Jinja: its rendered and raw checksums are identical.
    assert [u["script"] for u in executor.upgrades] == ["V1.0.0__first.sql", "V1.2.0__second.sql"]
    assert [row["script"] for row in executor.recorded] == ["A__grants.sql"]


def test_dry_run_never_upgrades_checksums(project):
    applied = applied_from(project, "V1.0.0__first.sql", legacy=True)
    executor = FakeExecutor(applied)
    deploy(load_config(project / "bqchange.yml"), executor, dry_run=True)
    assert executor.upgrades == []


def _applied_with_source(project, name, source_text, rendered_checksum="old"):
    from bqchange.render import checksum as digest

    return AppliedScript(name, "R", None, rendered_checksum, digest(source_text), source_text)


def test_repeatable_rerendered_for_another_environment_is_labelled_as_such(project):
    config = load_config(project / "bqchange.yml")
    source = (project / "scripts" / "repeatable" / "R__views.sql").read_text().strip()
    applied = applied_from(project, "V1.0.0__first.sql", "V1.2.0__second.sql", "V1.10.0__tenth.sql")
    applied.append(_applied_with_source(project, "R__views.sql", source))
    pending = plan(
        discover(config.root_folder),
        applied,
        Renderer.from_config(config),
        {"project": config.project, "location": config.location, **config.vars},
    ).pending
    views = next(p for p in pending if p.script.name == "R__views.sql")
    assert views.reason == "re-rendered for dev (file unchanged)"
    assert views.diff is None


def test_edited_repeatable_shows_a_diff_in_the_summary(project, tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    applied = applied_from(project, "V1.0.0__first.sql", "V1.2.0__second.sql", "V1.10.0__tenth.sql")
    applied.append(
        _applied_with_source(project, "R__views.sql", "create or replace view v as select 0")
    )
    executor = FakeExecutor(applied)
    deploy(load_config(project / "bqchange.yml"), executor)

    content = summary.read_text()
    assert "| `repeatable/R__views.sql` | repeatable | file changed |" in content
    assert "-create or replace view v as select 0" in content
    assert "+create or replace view v as select 1" in content
    recorded = next(r for r in executor.recorded if r["script"] == "R__views.sql")
    assert recorded["script_source"] == "create or replace view v as select 1"


def test_unchanged_scripts_recorded_without_source_are_backfilled_once(project):
    applied = applied_from(
        project, "V1.0.0__first.sql", "V1.2.0__second.sql", "V1.10.0__tenth.sql", "R__views.sql"
    )
    executor = FakeExecutor(applied)
    deploy(load_config(project / "bqchange.yml"), executor)
    assert sorted(b["script"] for b in executor.backfills) == [
        "R__views.sql",
        "V1.0.0__first.sql",
        "V1.10.0__tenth.sql",
        "V1.2.0__second.sql",
    ]


def test_new_scripts_show_their_content_in_the_summary(project, tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    deploy(load_config(project / "bqchange.yml"), FakeExecutor())
    content = summary.read_text()
    assert "View changes in <code>versioned/V1.0.0__first.sql</code>" in content
    assert "+create schema `{{ env }}_a`" in content
