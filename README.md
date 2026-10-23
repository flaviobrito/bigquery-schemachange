# BigQuery schema migrations + dbt: e-commerce lakehouse

A production-style reference project for **versioned schema management on
Google BigQuery**, using the same approach as
[schemachange](https://github.com/Snowflake-Labs/schemachange) on Snowflake:

- **`bqchange`** (in this repository, `src/bqchange`) owns database objects:
  datasets, landing tables, column changes, UDFs, views and grants, as
  versioned (`V`), repeatable (`R__`) and always (`A__`) SQL scripts with Jinja.
  schemachange itself only supports Snowflake, so `bqchange` brings the same
  conventions to BigQuery and adds a BigQuery-native plan via dry-run jobs.
- **[dbt](https://www.getdbt.com/)** owns the transformations: a medallion
  architecture (BRONZE → SILVER → GOLD) with layered data quality tests,
  enforced contracts and a schema drift audit.
- **GitHub Actions** ties them together: static checks, isolated datasets per
  pull request, gated DEV → PROD deployments and an on-demand data quality
  monitor. Every run publishes a report of schema changes and test results.

> **New to these tools?** Read the [complete guide](docs/guide.md): concepts,
> diagrams, setup with expected outcomes, and screenshots of the quality gate
> blocking real changes. Run-by-run proof is in [docs/evidence](docs/evidence/README.md).

Authentication uses **Workload Identity Federation**: no service account key
exists anywhere. Python tooling is managed with [uv](https://docs.astral.sh/uv/).

## Architecture

```mermaid
flowchart LR
    subgraph Sources
        CSV[Storefront exports]
    end

    subgraph BQ["BigQuery project · one dataset set per environment (dev_, prod_, pr_n_)"]
        subgraph BRONZE["*_bronze · bqchange"]
            RAW[customers · products · orders<br/>order_items · payments]
        end
        subgraph SILVER["*_silver · dbt"]
            STG[stg_ecommerce__*<br/>int_orders__*]
        end
        subgraph GOLD["*_gold · dbt"]
            MARTS[dim_customers · dim_products<br/>fct_orders · fct_order_items<br/>agg_daily_revenue]
        end
        subgraph AUDIT["*_audit"]
            DQ[test failures · schema snapshots<br/>schema drift · load log<br/>deployment history · UDFs]
        end
        META[("*_meta.change_history")]
    end

    CSV -- load jobs --> RAW
    RAW --> STG --> MARTS
    STG -. dbt tests .-> DQ
    MARTS -. dbt tests .-> DQ
    RAW -. INFORMATION_SCHEMA .-> DQ
    META --> DQ
    DQ -- drift alert --> CHAT[Slack / Teams]
```

| Dataset        | Owner    | Content                                                                 |
| -------------- | -------- | ----------------------------------------------------------------------- |
| `<env>_bronze` | bqchange | Source-shaped landing tables, partitioned by load date, with lineage columns |
| `<env>_silver` | dbt      | Typed, cleaned, deduplicated entities; `stg_ecommerce__orders` is an incremental merge |
| `<env>_gold`   | dbt      | Dimensional models with enforced contracts                              |
| `<env>_audit`  | both     | Stored test failures, schema snapshots and drift, load log, UDFs, deployment history |
| `<env>_meta`   | bqchange | `change_history`: one row per applied migration                          |

Environments (`dev`, `prod`, `pr_<number>`) share one GCP project and are
isolated by dataset prefix, set with the `BQ_ENV` variable.

## Repository layout

```
bootstrap/setup_gcp.sh     One-time GCP setup: APIs, service account, Workload Identity Federation
migrations/
  bqchange.yml             Configuration (project, location, history table, vars) rendered with Jinja
  modules/                 Shared Jinja macros
  scripts/versioned/       V<x.y.z>__*.sql  applied once, in version order, immutable afterwards
  scripts/repeatable/      R__*.sql         re-applied when their rendered content changes
  scripts/always/          A__*.sql         applied on every deployment
src/bqchange/              The migration runner (CLI: `bqchange deploy | render`)
dbt/
  models/silver/           Sources (BRONZE), staging and intermediate models
  models/gold/             core (dimensions/facts) and finance (aggregates)
  models/audit/            Schema snapshot history and drift view
  tests/generic|singular/  Custom data quality tests
ops/                       Sample data, loading, pull request environments, drift alerts, run reports
tests/                     pytest suite for bqchange and ops
.github/                   Workflows, composite setup action, Dependabot, CODEOWNERS
docs/                      bqchange reference, runbook and data quality catalogue
```

## Migrations

| Script                                       | Type       | Demonstrates                                     |
| -------------------------------------------- | ---------- | ------------------------------------------------ |
| `V1.0.0__create_medallion_datasets.sql`      | versioned  | Datasets with location, labels and descriptions   |
| `V1.1.0__create_bronze_tables.sql`           | versioned  | Jinja module import, partitioning and clustering  |
| `V1.2.0__add_customer_marketing_consent.sql` | versioned  | Schema evolution (`ALTER TABLE ... ADD COLUMN`)   |
| `V1.3.0__create_load_log.sql`                | versioned  | Operational table in AUDIT                        |
| `R__shared_routines.sql`                     | repeatable | Persistent UDF used by dbt models and tests       |
| `R__audit_views.sql`                         | repeatable | Views over change history, load log and schema history |
| `A__dataset_options.sql`                     | always     | Converging labels; 7-day table expiration on PR datasets |
| `A__grants.sql`                              | always     | Dataset-level `GRANT` for a reader principal      |

```bash
uv run bqchange deploy --dry-run   # plan: pending scripts validated by BigQuery dry runs
uv run bqchange deploy             # apply and record in <env>_meta.change_history
uv run bqchange render versioned/V1.2.0__add_customer_marketing_consent.sql
```

Safety rules enforced by `bqchange` (see [docs/bqchange.md](docs/bqchange.md)):
an applied versioned script can never change, versions cannot be applied out of
order without `--out-of-order`, and every job runs with a `maximum_bytes_billed` cap.

## Data quality

Checks run in layers. See [docs/data-quality.md](docs/data-quality.md) for the full catalogue.

1. **Source tests and freshness** on BRONZE (severity `warn`).
2. **SILVER/GOLD data tests**: uniqueness, referential integrity, accepted
   values, ranges, regex, row-count parity and business rule expressions
   (`dbt_utils`, `dbt_expectations` and custom generic tests).
3. **Singular tests**: revenue reconciliation, payment consistency, schema drift.
4. **Unit tests** for business logic (`fct_orders` totals, customer segmentation).
5. **Contracts** on every SILVER and GOLD model: column names, types and precision.
6. **Schema drift audit on BRONZE, SILVER and GOLD**: `INFORMATION_SCHEMA.COLUMNS`
   versus dbt sources and model contracts, with history in `audit_schema_snapshots`
   and Slack/Teams alerts. Manual changes in BigQuery are reported before dbt overwrites them.
7. **Schema history for every layer**: `bqchange record-schema` logs each added,
   removed or retyped column of BRONZE, SILVER and GOLD with its source
   (migration, dbt or manual), commit and pull request (`<env>_audit.schema_history`).
8. **Versioned GOLD models** for breaking changes: `dim_customers` v1 (deprecated,
   still at `dim_customers`) and v2 (`dim_customers_v2`, without the raw email).

Failing rows of every test are stored in `<env>_audit`.

## CI/CD

```mermaid
flowchart LR
    PR[Pull request] --> SC[Static checks<br/>ruff · pytest · sqlfluff<br/>dbt parse · bqchange render]
    SC --> CL[Clone DEV tables<br/>→ pr_n_* datasets]
    CL --> MIG[bqchange plan + deploy]
    MIG --> BUILD[dbt build state:modified+<br/>deferred to DEV]
    BUILD --> REP[Run report]
    MERGE[Merge to main] --> DEV[DEV: migrate · build · report]
    DEV --> GATE{{production<br/>approval}}
    GATE --> PROD[PROD: plan · migrate · build · docs · report]
    MANUAL[Manual trigger] --> MON[PROD monitor: freshness · drift alert · tests]
    CLOSE[PR closed] --> DROP[Drop pr_n_* datasets]
```

| Workflow         | Trigger                 | What it does                                                        |
| ---------------- | ----------------------- | ------------------------------------------------------------------- |
| `ci.yml`         | pull request            | Offline checks; then migrations and slim `dbt build` in pull request datasets |
| `deploy.yml`     | push to `main`, manual  | DEV, then PROD behind the `production` environment approval; dbt docs artifact |
| `monitor.yml`    | manual (`dev` or `prod`) | Source freshness, schema drift alert (all layers) and the full data test suite |
| `pr-cleanup.yml` | pull request closed     | Drops the pull request datasets                                      |
| `dq-gate-demo.yml` | manual               | Loads deliberately broken data into a throwaway environment; the quality gate is expected to fail |

Each run writes a **job summary** with the migrations planned and applied, the
newest BRONZE columns, schema drift and dbt results, so schema changes are
visible directly on the run page. The monitor is manual for this showcase; add a
`schedule` trigger for daily production monitoring.

## Quality gate in action

The pipeline is designed to stop bad changes. These cases are reproduced in the
repository's pull requests and workflow runs:

| Change                                                    | Blocked by                                             |
| --------------------------------------------------------- | ------------------------------------------------------ |
| Migration adds a BRONZE column not declared in dbt sources | `assert_no_bronze_schema_drift` (schema drift audit)   |
| Logic bug: order total ignores shipping                    | `fct_orders` unit test and `order_total` expression test |
| Edit of an already applied versioned migration             | bqchange immutability check                            |
| Broken source data (invalid values, orphans, negative prices) | SILVER data tests (`dq-gate-demo.yml`)              |
| Manual `ALTER TABLE` on a SILVER/GOLD table in BigQuery    | Schema drift audit on all layers (`monitor.yml`)      |

## Getting started

Requirements: [uv](https://docs.astral.sh/uv/), the
[gcloud CLI](https://cloud.google.com/sdk/docs/install) and a GCP project with
billing enabled (the BigQuery sandbox does not allow the DML used by
incremental models; the demo stays within the free tier).

```bash
make install                                  # uv sync, dbt deps, pre-commit hooks
cp .env.example .env                          # set GCP_PROJECT_ID and BQ_ENV
gcloud auth application-default login         # local credentials, stored outside the repo
make lint test-python                         # everything that runs offline
make migrate-plan migrate sample-data build   # plan, migrate, load and build
make drift docs                               # drift report and dbt docs on localhost
```

Generate broken data on purpose to watch the data quality tests react:

```bash
uv run python -m ops.generate_sample_data --inject-anomalies
```

## GitHub configuration

Run `bootstrap/setup_gcp.sh` once (see [docs/runbook.md](docs/runbook.md)). Workflow
logs of a public repository are public, so every value that identifies the GCP
project is stored as a **secret** and masked in logs.

| Kind        | Name                              | Value                                              |
| ----------- | --------------------------------- | -------------------------------------------------- |
| Secret      | `GCP_PROJECT_ID`                  | Project ID                                         |
| Secret      | `GCP_WORKLOAD_IDENTITY_PROVIDER`  | `projects/<number>/locations/global/workloadIdentityPools/github/providers/github-oidc` |
| Secret      | `GCP_SERVICE_ACCOUNT`             | `bq-ecommerce-cicd@<project>.iam.gserviceaccount.com` |
| Secret      | `SCHEMA_ALERT_WEBHOOK_URL`        | Slack or Teams incoming webhook (optional)          |
| Variable    | `GCP_ENABLED`                     | `true` to run the jobs that need Google Cloud        |
| Variable    | `BQ_LOCATION`                     | Dataset location (default `US`)                     |
| Variable    | `BQ_READER_PRINCIPAL`             | e.g. `group:analysts@example.com` (optional)        |
| Variable    | `FRESHNESS_BLOCKING`              | `true` to fail the monitor on stale sources          |
| Environment | `ci`, `dev`, `production`, `production-monitoring` | Required reviewers on `production` |

## License

[MIT](LICENSE)
