# Scenario 2: business logic bug is blocked

[Workflow run](https://github.com/flaviobrito/bigquery-schemachange/actions/runs/39885487010) · [pull request #2](https://github.com/flaviobrito/bigquery-schemachange/pull/2)

## Input

`fct_orders.order_total` is changed to ignore shipping.

## Expected outcome

The unit test `test_fct_orders_totals_and_revenue_flag` fails before any table is built; dependent models are skipped; the pull request is red.

## Actual outcome: ❌ blocked

### Migrations (bqchange)

```text
INFO    PLAN  repeatable/R__audit_views.sql (content changed) - valid, 0 bytes
INFO    PLAN  repeatable/R__shared_routines.sql (content changed) - valid, 0 bytes
INFO    PLAN  always/A__dataset_options.sql (always) - valid, 0 bytes
INFO    PLAN  always/A__grants.sql (always) - valid, 0 bytes
INFO    APPLY repeatable/R__audit_views.sql (content changed)
INFO    APPLY repeatable/R__shared_routines.sql (content changed)
INFO    APPLY always/A__dataset_options.sql (always)
INFO    APPLY always/A__grants.sql (always)
```

### dbt results

```text
3 of 31 FAIL 1 fct_orders::test_fct_orders_totals_and_revenue_flag ............. [FAIL 1 in 8.79s]
Done. PASS=6 WARN=0 ERROR=1 SKIP=24 NO-OP=0 REUSED=0 TOTAL=31
```

### Run report

### Schema and data quality report · `pr_2`

#### Schema migrations (change history)

| Installed on (UTC) | Version | Script | Type | Duration (ms) |
| --- | --- | --- | --- | --- |
| 2026-10-23 01:43:41 | - | `R__shared_routines.sql` | R | 636 |
| 2026-10-23 01:43:38 | - | `R__audit_views.sql` | R | 1425 |
| 2026-10-23 01:06:45 | - | `R__shared_routines.sql` | R | 1402 |
| 2026-10-23 01:06:41 | - | `R__audit_views.sql` | R | 2615 |
| 2026-10-23 01:06:37 | 1.3.0 | `V1.3.0__create_load_log.sql` | V | 1576 |
| 2026-10-23 01:06:32 | 1.2.0 | `V1.2.0__add_customer_marketing_consent.sql` | V | 1512 |
| 2026-10-23 01:06:29 | 1.1.0 | `V1.1.0__create_bronze_tables.sql` | V | 3880 |
| 2026-10-23 01:06:23 | 1.0.0 | `V1.0.0__create_medallion_datasets.sql` | V | 4838 |

#### BRONZE schema: most recent columns

| Table | Column | Type | First seen (UTC) | Still present |
| --- | --- | --- | --- | --- |
| customers | `marketing_opt_in` | BOOL | 2026-10-23 01:44:00 | yes |
| customers | `_loaded_at` | TIMESTAMP | 2026-10-23 01:44:00 | yes |
| customers | `_source_row_number` | INT64 | 2026-10-23 01:44:00 | yes |
| customers | `_source_file` | STRING | 2026-10-23 01:44:00 | yes |
| customers | `updated_at` | TIMESTAMP | 2026-10-23 01:44:00 | yes |
| customers | `created_at` | TIMESTAMP | 2026-10-23 01:44:00 | yes |
| customers | `city` | STRING | 2026-10-23 01:44:00 | yes |
| customers | `state` | STRING | 2026-10-23 01:44:00 | yes |
| customers | `country_code` | STRING | 2026-10-23 01:44:00 | yes |
| customers | `phone` | STRING | 2026-10-23 01:44:00 | yes |

#### Schema drift

✅ BRONZE matches the dbt source declarations.

#### dbt (build)

❌ fail: 1 · ✅ pass: 4 · ⏭️ skipped: 24 · ✅ success: 2

| Status | Node | Failures | Message |
| --- | --- | --- | --- |
| ❌ fail | `fct_orders.test_fct_orders_totals_and_revenue_flag` | 1 |   actual differs from expected:  @@,order_id,order_total,gross_margin,...
 → |
