"""Change history table: one row per applied script, the source of truth for what is pending."""

from __future__ import annotations

from dataclasses import dataclass

from bqchange.executor import Executor


@dataclass(frozen=True)
class AppliedScript:
    script: str
    script_type: str
    version: str | None
    checksum: str
    # Raw file fingerprint and text, used to tell real edits from re-rendering
    # and to show a diff. Empty for rows written by older versions.
    source_checksum: str | None = None
    script_source: str | None = None


class ChangeHistory:
    def __init__(self, executor: Executor, table: str):
        self._executor = executor
        self._table = table

    def ensure(self, dataset_id: str) -> None:
        self._executor.ensure_dataset(dataset_id)
        self._executor.execute(
            f"""
            create table if not exists `{self._table}` (
                version string,
                description string,
                script string not null,
                script_type string not null,
                checksum string not null,
                execution_time_ms int64,
                status string not null,
                installed_by string,
                installed_on timestamp not null
            )
            options (description = 'Scripts applied by bqchange, one row per execution.')
            """
        )
        self._executor.execute(
            f"""
            alter table `{self._table}`
            add column if not exists source_checksum string,
            add column if not exists script_source string
            """
        )

    def applied(self) -> list[AppliedScript]:
        """Latest successful execution of each script."""
        latest = "qualify row_number() over (partition by script order by installed_on desc) = 1"
        try:
            rows = self._executor.query(
                f"""
                select script, script_type, version, checksum, source_checksum, script_source
                from `{self._table}`
                where status = 'success'
                {latest}
                """
            )
        except Exception as error:
            # A history table created by an older version (e.g. read in a dry run).
            if "source_checksum" not in str(error) and "script_source" not in str(error):
                raise
            rows = self._executor.query(
                f"""
                select script, script_type, version, checksum
                from `{self._table}`
                where status = 'success'
                {latest}
                """
            )
        return [AppliedScript(**row) for row in rows]

    def backfill_source(
        self, script: str, checksum: str, source_checksum: str, source: str
    ) -> None:
        """Attach the raw file to rows written before sources were recorded."""
        self._executor.execute(
            f"""
            update `{self._table}`
            set source_checksum = @source_checksum, script_source = @script_source
            where script = @script and checksum = @checksum and source_checksum is null
            """,
            params={
                "script": script,
                "checksum": checksum,
                "source_checksum": source_checksum,
                "script_source": source,
            },
        )

    def update_checksum(self, script: str, old: str, new: str) -> None:
        """Rewrite a legacy checksum in place (see deploy.ChecksumUpgrade)."""
        self._executor.execute(
            f"""
            update `{self._table}`
            set checksum = @new
            where script = @script and checksum = @old
            """,
            params={"script": script, "old": old, "new": new},
        )

    def record(
        self,
        *,
        script: str,
        script_type: str,
        version: str | None,
        description: str,
        checksum: str,
        execution_time_ms: int,
        source_checksum: str | None = None,
        script_source: str | None = None,
    ) -> None:
        self._executor.execute(
            f"""
            insert into `{self._table}` (
                version, description, script, script_type, checksum,
                execution_time_ms, status, installed_by, installed_on,
                source_checksum, script_source
            )
            values (
                @version, @description, @script, @script_type, @checksum,
                @execution_time_ms, 'success', session_user(), current_timestamp(),
                @source_checksum, @script_source
            )
            """,
            params={
                "version": version,
                "description": description,
                "script": script,
                "script_type": script_type,
                "checksum": checksum,
                "execution_time_ms": execution_time_ms,
                "source_checksum": source_checksum,
                "script_source": script_source,
            },
        )
