# Production deployment (after manual approval)

[Workflow run](https://github.com/flaviobrito/bigquery-schemachange/actions/runs/39883046028)

## Input

Manual run of `deploy.yml` with *Load sample data*; DEV deployed automatically, PROD waited for the owner's approval.

## Expected outcome

All migrations applied to the empty PROD environment, sample data loaded, every model built and tested.

## Actual outcome: ✅ passed

### Migrations (bqchange)

```text
INFO    PLAN  versioned/V1.0.0__create_medallion_datasets.sql (new version) - valid, 0 bytes
INFO    PLAN  always/A__dataset_options.sql (always) - valid, 0 bytes
INFO    PLAN  always/A__grants.sql (always) - valid, 0 bytes
INFO    APPLY versioned/V1.0.0__create_medallion_datasets.sql (new version)
INFO    APPLY versioned/V1.1.0__create_bronze_tables.sql (new version)
INFO    APPLY versioned/V1.2.0__add_customer_marketing_consent.sql (new version)
INFO    APPLY versioned/V1.3.0__create_load_log.sql (new version)
INFO    APPLY repeatable/R__audit_views.sql (new repeatable)
INFO    APPLY repeatable/R__shared_routines.sql (new repeatable)
INFO    APPLY always/A__dataset_options.sql (always)
INFO    APPLY always/A__grants.sql (always)
```

### dbt results

```text
13 of 103 WARN 10 source_unique_ecommerce_customers_customer_id ................ [WARN 10 in 3.94s]
Done. PASS=102 WARN=1 ERROR=0 SKIP=0 NO-OP=0 REUSED=0 TOTAL=103
```

### Run report

### Schema and data quality report · `prod`

#### Schema migrations (change history)

| Installed on (UTC) | Version | Script | Type | Duration (ms) |
| --- | --- | --- | --- | --- |
| 2026-10-23 01:25:42 | - | `R__shared_routines.sql` | R | 728 |
| 2026-10-23 01:25:39 | - | `R__audit_views.sql` | R | 1917 |
| 2026-10-23 01:25:36 | 1.3.0 | `V1.3.0__create_load_log.sql` | V | 727 |
| 2026-10-23 01:25:34 | 1.2.0 | `V1.2.0__add_customer_marketing_consent.sql` | V | 763 |
| 2026-10-23 01:25:31 | 1.1.0 | `V1.1.0__create_bronze_tables.sql` | V | 3705 |
| 2026-10-23 01:25:26 | 1.0.0 | `V1.0.0__create_medallion_datasets.sql` | V | 3953 |

#### BRONZE schema: most recent columns

| Table | Column | Type | First seen (UTC) | Still present |
| --- | --- | --- | --- | --- |
| customers | `marketing_opt_in` | BOOL | 2026-10-23 01:26:20 | yes |
| customers | `_loaded_at` | TIMESTAMP | 2026-10-23 01:26:20 | yes |
| customers | `_source_row_number` | INT64 | 2026-10-23 01:26:20 | yes |
| customers | `_source_file` | STRING | 2026-10-23 01:26:20 | yes |
| customers | `updated_at` | TIMESTAMP | 2026-10-23 01:26:20 | yes |
| customers | `created_at` | TIMESTAMP | 2026-10-23 01:26:20 | yes |
| customers | `city` | STRING | 2026-10-23 01:26:20 | yes |
| customers | `state` | STRING | 2026-10-23 01:26:20 | yes |
| customers | `country_code` | STRING | 2026-10-23 01:26:20 | yes |
| customers | `phone` | STRING | 2026-10-23 01:26:20 | yes |

#### Schema drift

✅ BRONZE matches the dbt source declarations.

#### dbt (build)

✅ pass: 88 · ✅ success: 14 · ⚠️ warn: 1

| Status | Node | Failures | Message |
| --- | --- | --- | --- |
| ⚠️ warn | `source_unique_ecommerce_customers_customer_id` | 10 | Got 10 results, configured to warn if != 0 |
