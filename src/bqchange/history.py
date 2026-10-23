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

    def applied(self) -> list[AppliedScript]:
        """Latest successful execution of each script."""
        rows = self._executor.query(
            f"""
            select script, script_type, version, checksum
            from `{self._table}`
            where status = 'success'
            qualify row_number() over (partition by script order by installed_on desc) = 1
            """
        )
        return [AppliedScript(**row) for row in rows]

    def record(
        self,
        *,
        script: str,
        script_type: str,
        version: str | None,
        description: str,
        checksum: str,
        execution_time_ms: int,
    ) -> None:
        self._executor.execute(
            f"""
            insert into `{self._table}` (
                version, description, script, script_type, checksum,
                execution_time_ms, status, installed_by, installed_on
            )
            values (
                @version, @description, @script, @script_type, @checksum,
                @execution_time_ms, 'success', session_user(), current_timestamp()
            )
            """,
            params={
                "version": version,
                "description": description,
                "script": script,
                "script_type": script_type,
                "checksum": checksum,
                "execution_time_ms": execution_time_ms,
            },
        )
