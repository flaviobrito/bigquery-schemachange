# Scenario 1b: the same change, done right, passes

[Workflow run](https://github.com/flaviobrito/bigquery-schemachange/actions/runs/39885783246) · [pull request #1](https://github.com/flaviobrito/bigquery-schemachange/pull/1)

## Input

Second commit on the same pull request declares `loyalty_tier` (with an `accepted_values` test) in `_ecommerce__sources.yml`.

## Expected outcome

V1.4.0 applied, schema drift aligned, every check passes; the pull request turns green.

## Actual outcome: ✅ passed

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
Done. PASS=7 WARN=0 ERROR=0 SKIP=0 NO-OP=0 REUSED=0 TOTAL=7
```

### Run report

### Schema and data quality report · `pr_1`

#### Schema migrations (change history)

| Installed on (UTC) | Version | Script | Type | Duration (ms) |
| --- | --- | --- | --- | --- |
| 2026-10-23 01:46:34 | - | `R__shared_routines.sql` | R | 578 |
| 2026-10-23 01:46:32 | - | `R__audit_views.sql` | R | 1471 |
| 2026-10-23 01:46:29 | 1.4.0 | `V1.4.0__add_customer_loyalty_tier.sql` | V | 629 |
| 2026-10-23 01:06:45 | - | `R__shared_routines.sql` | R | 1402 |
| 2026-10-23 01:06:41 | - | `R__audit_views.sql` | R | 2615 |
| 2026-10-23 01:06:37 | 1.3.0 | `V1.3.0__create_load_log.sql` | V | 1576 |
| 2026-10-23 01:06:32 | 1.2.0 | `V1.2.0__add_customer_marketing_consent.sql` | V | 1512 |
| 2026-10-23 01:06:29 | 1.1.0 | `V1.1.0__create_bronze_tables.sql` | V | 3880 |
| 2026-10-23 01:06:23 | 1.0.0 | `V1.0.0__create_medallion_datasets.sql` | V | 4838 |

#### BRONZE schema: most recent columns

| Table | Column | Type | First seen (UTC) | Still present |
| --- | --- | --- | --- | --- |
| customers | `loyalty_tier` | STRING | 2026-10-23 01:46:50 | yes |
| customers | `marketing_opt_in` | BOOL | 2026-10-23 01:46:50 | yes |
| customers | `_loaded_at` | TIMESTAMP | 2026-10-23 01:46:50 | yes |
| customers | `_source_row_number` | INT64 | 2026-10-23 01:46:50 | yes |
| customers | `_source_file` | STRING | 2026-10-23 01:46:50 | yes |
| customers | `updated_at` | TIMESTAMP | 2026-10-23 01:46:50 | yes |
| customers | `created_at` | TIMESTAMP | 2026-10-23 01:46:50 | yes |
| customers | `city` | STRING | 2026-10-23 01:46:50 | yes |
| customers | `state` | STRING | 2026-10-23 01:46:50 | yes |
| customers | `country_code` | STRING | 2026-10-23 01:46:50 | yes |

#### Schema drift

✅ BRONZE matches the dbt source declarations.

#### dbt (build)

✅ pass: 5 · ✅ success: 2
