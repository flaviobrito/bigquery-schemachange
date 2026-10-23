# Scenario 5: a manual change in BigQuery is detected

Someone alters a GOLD table directly in the BigQuery console, outside Git and
the pipeline. Before this change to the project, dbt would have silently
overwritten it on the next build and nobody would have known.

| Stage | What happens | Run | Result |
| --- | --- | --- | --- |
| Before | Monitor on `dev` with every layer aligned | [39935547618](https://github.com/flaviobrito/bigquery-schemachange/actions/runs/39935547618) | ✅ success |
| Manual change | `alter table dev_gold.dim_customers add column manual_note string` in the BigQuery console | – | – |
| Effect | Monitor detects the undeclared column, alerts and **stops before `dbt build`**, preserving the evidence | [39940900977](https://github.com/flaviobrito/bigquery-schemachange/actions/runs/39940900977) | ❌ failure |
| Restore | `dbt build --select dim_customers` recreates the table from code (any deployment does the same) | local | 9 passed |
| After | Monitor on `dev` again | [39941074529](https://github.com/flaviobrito/bigquery-schemachange/actions/runs/39941074529) | ✅ success |

## Before

### Schema drift (report)

✅ BRONZE, SILVER and GOLD match the dbt declarations.

```text
INFO No schema drift in dev_bronze
```

> This run used the alert wording from before the layer-aware messages were
> added ("dev_bronze"); the check itself already covered all three layers.

## Effect

### Schema drift (report)

| Layer | Table | Column | Status | BigQuery type | Declared type |
| --- | --- | --- | --- | --- | --- |
| GOLD | dim_customers | `manual_note` | ❌ undeclared_in_dbt | STRING |  |

### Alert sent to Slack/Teams (and printed in the log)

```text
Schema drift detected in dev (1 column(s))
- GOLD dim_customers.manual_note: exists in BigQuery but is not declared in the dbt model contracts
```

## After

### Schema drift (report)

✅ BRONZE, SILVER and GOLD match the dbt declarations.

```text
INFO No schema drift in dev
```
