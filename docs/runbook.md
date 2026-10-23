# Runbook

## 1. Google Cloud bootstrap (once)

Prerequisites: a project with billing enabled, `gcloud` authenticated as a
project owner, and the GitHub repository created.

```bash
GCP_PROJECT_ID=<project> GITHUB_REPOSITORY=<owner>/<repo> CONFIGURE_GITHUB=true \
  ./bootstrap/setup_gcp.sh
```

The script is idempotent and creates:

| Resource                               | Purpose                                                   |
| -------------------------------------- | --------------------------------------------------------- |
| APIs: BigQuery, IAM, IAM Credentials, STS | Required by Workload Identity Federation              |
| Service account `bq-ecommerce-cicd`    | Identity used by GitHub Actions (`bigquery.jobUser`, `bigquery.dataOwner`) |
| Workload Identity pool `github` + OIDC provider | Exchanges GitHub OIDC tokens for short-lived Google credentials |
| `workloadIdentityUser` binding         | Only workflows of the given repository can impersonate the service account |
| Budget alert (optional, `BUDGET_AMOUNT=1`) | Email when monthly spend reaches 50 % / 100 %          |

With `CONFIGURE_GITHUB=true` it also stores `GCP_PROJECT_ID`,
`GCP_WORKLOAD_IDENTITY_PROVIDER` and `GCP_SERVICE_ACCOUNT` as repository secrets
and sets `GCP_ENABLED=true`. No key file is created at any point.

**Hardening:** `bigquery.dataOwner` at project level also covers datasets
unrelated to this project. In shared projects, add IAM conditions such as
`resource.name.startsWith("projects/<project>/datasets/dev_")` (one binding per
prefix: `dev_`, `prod_`, `pr_`) or use a dedicated project.

## 2. First deployment

Run **Actions → Deploy → Run workflow** with *Load sample data* checked, approve
the `production` environment when prompted, then check the job summaries.

Locally: `make migrate sample-data build` with `BQ_ENV=dev` in `.env`.

## 3. Writing migrations

- **Never edit an applied versioned script**: bqchange rejects it. Add `V<next>__description.sql`.
- Use `if not exists` / `if exists` so scripts are safe on clones and re-runs.
- Views and UDFs belong in `R__` scripts; grants and dataset options in `A__` scripts.
- Every new or changed BRONZE column must be declared in
  `dbt/models/silver/ecommerce/_ecommerce__sources.yml`, otherwise
  `assert_no_bronze_schema_drift` fails the pull request.
- Preview offline: `uv run bqchange render versioned/<file>.sql`.

## 4. Rollback

bqchange is forward-only. Options, from least to most invasive:

| Situation                              | Action                                                              |
| -------------------------------------- | ------------------------------------------------------------------- |
| Bad view or UDF (`R__`)                | Revert the commit; the repeatable script is re-applied on the next deploy |
| Bad versioned migration, data intact   | Ship a new corrective `V` script (forward fix)                       |
| Dropped table                          | Restore within the time travel window: `bq cp <dataset>.<table>@-3600000 <dataset>.<table>` |
| Corrupted rows                         | `create or replace table ... as select * from ... for system_time as of timestamp_sub(current_timestamp(), interval 1 hour)` |

Time travel covers 7 days by default (plus 7 days of fail-safe recoverable through support).

## 5. Pull request environments

CI creates `pr_<number>_{bronze,silver,gold,audit,meta}`, clones DEV's BRONZE,
AUDIT and META tables into them (`CREATE TABLE ... CLONE`: storage is only billed
for changed data) and applies the pull request's migrations. Unmodified dbt
models are deferred to DEV. Tables in these datasets expire after 7 days, and
`pr-cleanup.yml` drops the datasets when the pull request closes.
`ops/manage_environment.py` refuses to drop anything other than `pr_<number>`.

## 6. Schema drift

`monitor.yml` (choose `dev` or `prod`) refreshes `<env>_audit.audit_schema_snapshots`
and `<env>_audit.audit_schema_drift` for BRONZE, SILVER and GOLD, posts non-aligned
columns to `SCHEMA_ALERT_WEBHOOK_URL` and fails the run **before** `dbt build`, so a
manual change is reported instead of being silently overwritten. To resolve drift
in SILVER/GOLD, either revert the manual change by rebuilding the model
(`dbt build --select <model>`) or make it official in code (model + contract) via a
pull request.

| Status                | Meaning                                       | Fix                                     |
| --------------------- | --------------------------------------------- | --------------------------------------- |
| `undeclared_in_dbt`   | Column exists in BigQuery but not in dbt (sources for BRONZE, contracts for SILVER/GOLD) | Declare it in code, or revert the manual change |
| `missing_in_database` | Declared in sources but not in BigQuery       | Add the migration, or remove the declaration |
| `type_mismatch`       | Types differ                                  | Align the declaration or migrate the column |

## 7. Schema history

Every structural change of every table in the monitored datasets (columns and
table/column properties such as partitioning, clustering, options and
descriptions) is logged with its source:

```sql
select changed_at, layer, table_name, column_name, change_type, property,
       old_value, new_value, source, pull_request, run_url
from `<project>.prod_audit.schema_history`
order by changed_at desc;
```

`source = 'manual'` means the change was made outside the pipeline; follow up
with the schema drift section above.

## 8. Cost controls

- `maximum_bytes_billed` of 1 GiB per job in bqchange and dbt.
- BRONZE tables are partitioned by load date and clustered by key.
- Load jobs, DDL and table clones are free; the sample dataset is a few MB.
- Pull request tables expire after 7 days.
