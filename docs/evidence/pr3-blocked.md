# Scenario 3: editing an applied migration is blocked

[Workflow run](https://github.com/flaviobrito/bigquery-schemachange/actions/runs/39885488994) · [pull request #3](https://github.com/flaviobrito/bigquery-schemachange/pull/3)

## Input

The already applied `V1.1.0__create_bronze_tables.sql` is edited (a column description is added).

## Expected outcome

bqchange stops at the plan step with "Versioned scripts are immutable"; nothing is applied; the pull request is red.

## Actual outcome: ❌ blocked

### Migrations (bqchange)

```text
ERROR   V1.1.0__create_bronze_tables.sql was already applied and has been modified. Versioned scripts are immutable: add a new version instead.
```

### dbt results

_(none)_

### Run report

### Schema and data quality report · `pr_3`

#### Schema migrations (change history)

⚠️ Not available: the query failed (see the step log).

#### BRONZE schema: most recent columns

| Table | Column | Type | First seen (UTC) | Still present |
| --- | --- | --- | --- | --- |
| customers | `marketing_opt_in` | BOOL | 2026-10-23 01:10:16 | yes |
| customers | `_loaded_at` | TIMESTAMP | 2026-10-23 01:10:16 | yes |
| customers | `_source_row_number` | INT64 | 2026-10-23 01:10:16 | yes |
| customers | `_source_file` | STRING | 2026-10-23 01:10:16 | yes |
| customers | `updated_at` | TIMESTAMP | 2026-10-23 01:10:16 | yes |
| customers | `created_at` | TIMESTAMP | 2026-10-23 01:10:16 | yes |
| customers | `city` | STRING | 2026-10-23 01:10:16 | yes |
| customers | `state` | STRING | 2026-10-23 01:10:16 | yes |
| customers | `country_code` | STRING | 2026-10-23 01:10:16 | yes |
| customers | `phone` | STRING | 2026-10-23 01:10:16 | yes |

#### Schema drift

⚠️ Not available: the query failed (see the step log).

#### dbt

No dbt results found.
