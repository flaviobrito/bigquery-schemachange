# Scenario 1a: undeclared BRONZE column is blocked

[Workflow run](https://github.com/flaviobrito/bigquery-schemachange/actions/runs/39885484254) · [pull request #1](https://github.com/flaviobrito/bigquery-schemachange/pull/1)

## Input

Migration `V1.4.0__add_customer_loyalty_tier.sql` adds `loyalty_tier` to `customers`; the dbt sources are **not** updated.

## Expected outcome

Only V1.4.0 is applied in the pull request datasets; the schema drift audit reports `loyalty_tier` as `undeclared_in_dbt`; `assert_no_bronze_schema_drift` fails; the pull request is red.

## Actual outcome: ❌ blocked

### Migrations (bqchange)

```text
INFO    PLAN  versioned/V1.4.0__add_customer_loyalty_tier.sql (new version) - valid, 0 bytes
INFO    PLAN  repeatable/R__audit_views.sql (content changed) - valid, 0 bytes
INFO    PLAN  repeatable/R__shared_routines.sql (content changed) - valid, 0 bytes
INFO    PLAN  always/A__dataset_options.sql (always) - valid, 0 bytes
INFO    PLAN  always/A__grants.sql (always) - valid, 0 bytes
INFO    APPLY versioned/V1.4.0__add_customer_loyalty_tier.sql (new version)
INFO    APPLY repeatable/R__audit_views.sql (content changed)
INFO    APPLY repeatable/R__shared_routines.sql (content changed)
INFO    APPLY always/A__dataset_options.sql (always)
INFO    APPLY always/A__grants.sql (always)
```

### dbt results

```text
4 of 6 FAIL 1 assert_no_bronze_schema_drift .................................... [FAIL 1 in 3.91s]
Done. PASS=5 WARN=0 ERROR=1 SKIP=0 NO-OP=0 REUSED=0 TOTAL=6
```

### Run report

### Schema and data quality report · `pr_1`

#### Schema migrations (change history)

| Installed on (UTC) | Version | Script | Type | Duration (ms) |
| --- | --- | --- | --- | --- |
| 2026-10-23 01:43:42 | - | `R__shared_routines.sql` | R | 726 |
| 2026-10-23 01:43:39 | - | `R__audit_views.sql` | R | 2292 |
| 2026-10-23 01:43:35 | 1.4.0 | `V1.4.0__add_customer_loyalty_tier.sql` | V | 925 |
| 2026-10-23 01:06:45 | - | `R__shared_routines.sql` | R | 1402 |
| 2026-10-23 01:06:41 | - | `R__audit_views.sql` | R | 2615 |
| 2026-10-23 01:06:37 | 1.3.0 | `V1.3.0__create_load_log.sql` | V | 1576 |
| 2026-10-23 01:06:32 | 1.2.0 | `V1.2.0__add_customer_marketing_consent.sql` | V | 1512 |
| 2026-10-23 01:06:29 | 1.1.0 | `V1.1.0__create_bronze_tables.sql` | V | 3880 |
| 2026-10-23 01:06:23 | 1.0.0 | `V1.0.0__create_medallion_datasets.sql` | V | 4838 |

#### BRONZE schema: most recent columns

| Table | Column | Type | First seen (UTC) | Still present |
| --- | --- | --- | --- | --- |
| customers | `loyalty_tier` | STRING | 2026-10-23 01:44:01 | yes |
| customers | `marketing_opt_in` | BOOL | 2026-10-23 01:44:01 | yes |
| customers | `_loaded_at` | TIMESTAMP | 2026-10-23 01:44:01 | yes |
| customers | `_source_row_number` | INT64 | 2026-10-23 01:44:01 | yes |
| customers | `_source_file` | STRING | 2026-10-23 01:44:01 | yes |
| customers | `updated_at` | TIMESTAMP | 2026-10-23 01:44:01 | yes |
| customers | `created_at` | TIMESTAMP | 2026-10-23 01:44:01 | yes |
| customers | `city` | STRING | 2026-10-23 01:44:01 | yes |
| customers | `state` | STRING | 2026-10-23 01:44:01 | yes |
| customers | `country_code` | STRING | 2026-10-23 01:44:01 | yes |

#### Schema drift

| Table | Column | Status | BigQuery type | Declared type |
| --- | --- | --- | --- | --- |
| customers | `loyalty_tier` | ❌ undeclared_in_dbt | STRING |  |

#### dbt (build)

❌ fail: 1 · ✅ pass: 3 · ✅ success: 2

| Status | Node | Failures | Message |
| --- | --- | --- | --- |
| ❌ fail | `assert_no_bronze_schema_drift` | 1 | Got 1 result, configured to fail if != 0 |
