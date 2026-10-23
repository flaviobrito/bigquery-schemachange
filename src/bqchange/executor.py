"""Thin BigQuery access layer, kept behind a protocol so planning logic is unit-testable."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from google.api_core.exceptions import BadRequest, NotFound
from google.cloud import bigquery

from bqchange.config import Config


@dataclass(frozen=True)
class DryRunResult:
    ok: bool
    bytes_processed: int = 0
    error: str | None = None


class Executor(Protocol):
    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None: ...

    def query(self, sql: str) -> Iterable[dict[str, Any]]: ...

    def dry_run(self, sql: str) -> DryRunResult: ...

    def ensure_dataset(self, dataset_id: str) -> None: ...


class BigQueryExecutor:
    def __init__(self, config: Config, client: bigquery.Client | None = None):
        self._config = config
        self._client = client or bigquery.Client(project=config.project, location=config.location)

    def _job_config(self, **kwargs: Any) -> bigquery.QueryJobConfig:
        return bigquery.QueryJobConfig(
            labels={"tool": "bqchange", **self._config.labels},
            maximum_bytes_billed=self._config.maximum_bytes_billed,
            **kwargs,
        )

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None:
        query_parameters = [
            bigquery.ScalarQueryParameter(name, _bq_type(value), value)
            for name, value in (params or {}).items()
        ]
        job = self._client.query(
            sql, job_config=self._job_config(query_parameters=query_parameters)
        )
        job.result()

    def query(self, sql: str) -> Iterable[dict[str, Any]]:
        return [dict(row.items()) for row in self._client.query(sql, job_config=self._job_config())]

    def dry_run(self, sql: str) -> DryRunResult:
        try:
            job = self._client.query(sql, job_config=self._job_config(dry_run=True))
        except (BadRequest, NotFound) as error:
            details = [item.get("message") for item in getattr(error, "errors", []) or []]
            return DryRunResult(ok=False, error=next(filter(None, details), str(error)))
        return DryRunResult(ok=True, bytes_processed=job.total_bytes_processed or 0)

    def ensure_dataset(self, dataset_id: str) -> None:
        dataset = bigquery.Dataset(dataset_id)
        dataset.location = self._config.location
        dataset.description = "bqchange metadata: migration change history."
        dataset.labels = {"managed_by": "bqchange", **self._config.labels}
        self._client.create_dataset(dataset, exists_ok=True)


def _bq_type(value: Any) -> str:
    if isinstance(value, bool):
        return "BOOL"
    if isinstance(value, int):
        return "INT64"
    return "STRING"
