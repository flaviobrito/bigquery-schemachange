"""Load generated CSV files into BRONZE with load jobs (free of charge) and log each file.

Lineage columns (_source_file, _source_row_number, _loaded_at) are added here,
and rows are sent as newline-delimited JSON so columns match by name.

Example:
    python -m ops.load_sample_data --input-dir data/sample
"""

from __future__ import annotations

import argparse
import csv
import logging
from datetime import UTC, datetime
from pathlib import Path

from google.cloud import bigquery

from ops.environment import client, current_environment, dataset_id
from ops.generate_sample_data import COLUMNS

logger = logging.getLogger(__name__)

BOOLEAN_COLUMNS = {"marketing_opt_in", "is_active"}


def to_json_rows(path: Path, loaded_at: datetime) -> list[dict]:
    rows = []
    with path.open(newline="", encoding="utf-8") as handle:
        for number, row in enumerate(csv.DictReader(handle), start=1):
            record: dict[str, object] = {
                key: (None if value == "" else value) for key, value in row.items()
            }
            for column in BOOLEAN_COLUMNS & record.keys():
                if record[column] is not None:
                    record[column] = str(record[column]).lower() == "true"
            record["_source_file"] = path.name
            record["_source_row_number"] = number
            record["_loaded_at"] = loaded_at.isoformat()
            rows.append(record)
    return rows


def load(input_dir: Path) -> None:
    bq = client()
    environment = current_environment()
    bronze = dataset_id(bq.project, environment, "bronze")
    load_log = f"{dataset_id(bq.project, environment, 'audit')}.load_log"
    log_rows = []

    for table in COLUMNS:
        files = sorted((input_dir / table).glob("*.csv"))
        if not files:
            logger.warning("No files for %s in %s", table, input_dir / table)
            continue
        destination = bq.get_table(f"{bronze}.{table}")
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            schema=destination.schema,
            labels={"tool": "ops-loader", "environment": environment},
        )
        for path in files:
            loaded_at = datetime.now(UTC)
            rows = to_json_rows(path, loaded_at)
            job = bq.load_table_from_json(rows, destination, job_config=job_config)
            job.result()
            logger.info("Loaded %s rows from %s into %s", len(rows), path.name, table)
            log_rows.append(
                {
                    "table_name": table,
                    "source_file": path.name,
                    "row_count": len(rows),
                    "load_job_id": job.job_id,
                    "loaded_at": loaded_at.isoformat(),
                }
            )

    if log_rows:
        bq.load_table_from_json(
            log_rows,
            load_log,
            job_config=bigquery.LoadJobConfig(
                source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
                write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            ),
        ).result()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("data/sample"))
    load(parser.parse_args().input_dir)


if __name__ == "__main__":
    main()
