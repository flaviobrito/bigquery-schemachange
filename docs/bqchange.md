# bqchange reference

`bqchange` is a small migration runner for BigQuery that follows the
[schemachange](https://github.com/Snowflake-Labs/schemachange) conventions.

## Configuration (`migrations/bqchange.yml`)

The file is rendered with Jinja before being parsed; `env_var('NAME', 'default')`
reads environment variables. It never contains credentials.

| Key                           | Meaning                                                            |
| ----------------------------- | ------------------------------------------------------------------ |
| `project`                     | GCP project that runs the jobs and owns the datasets               |
| `location`                    | Dataset and job location (default `US`)                            |
| `root-folder`                 | Folder scanned recursively for scripts                             |
| `modules-folder`              | Shared Jinja templates, imported as `modules/<file>`               |
| `change-history-table`        | `dataset.table` (or `project.dataset.table`) of the change history |
| `create-change-history-table` | Create the history dataset and table when missing (default `true`) |
| `maximum-bytes-billed`        | Per-job billing cap; a job above it fails instead of running        |
| `labels`                      | Labels added to every job (cost attribution)                       |
| `vars`                        | Variables available in every script                                 |
| `layers`                      | Logical layer → dataset of this environment, e.g. `bronze: "{{ env_var('BQ_ENV') }}_bronze"`. Any names work |
| `schema-log-layers`           | Layers whose column-level changes `record-schema` logs |
| `pr-clone-layers`             | Layers copied from DEV into pull request environments (plus the meta dataset) |

`project`, `location` and `layers` (the map above) are always available to scripts
as variables, e.g. `{{ layers.bronze }}`.

## Script types

| Pattern                       | Applied                                   | Typical content                 |
| ----------------------------- | ----------------------------------------- | ------------------------------- |
| `V<version>__<description>.sql` | Once, ordered numerically (`1.10.0` after `1.2.0`) | Datasets, tables, `ALTER TABLE` |
| `R__<description>.sql`        | When the rendered content changes         | Views, UDFs, procedures          |
| `A__<description>.sql`        | On every deployment, last                 | Grants, labels, options          |

Each script is executed as a single BigQuery job, so multi-statement scripts are allowed.

## Execution order and rules

1. Versioned scripts in ascending version, then repeatable scripts by name, then always scripts by name.
2. A versioned script whose checksum differs from the applied one fails the
   deployment: applied versions are immutable, ship a new version instead.
3. A pending version lower than the latest applied version fails unless
   `--out-of-order` is passed.
4. Duplicate script names or versions fail discovery.
5. Each successful script is recorded in the change history with its checksum,
   duration, `SESSION_USER()` and timestamp.

## Commands

```bash
bqchange deploy --dry-run       # plan: render and validate pending scripts with dry-run jobs
bqchange deploy                 # apply pending scripts
bqchange deploy --out-of-order  # allow versions older than the latest applied one
bqchange render <path>          # print a rendered script (path relative to root-folder)
bqchange record-schema --source migration|dbt|manual   # log schema changes since the last snapshot
bqchange --config other.yml ...
```

In a dry run, a script that references objects created by an earlier pending
script cannot be validated yet; it is reported as such instead of failing. Only
an invalid first pending script fails the plan.

When `GITHUB_STEP_SUMMARY` is set, `deploy` appends a Markdown table of the
planned or applied scripts to the GitHub Actions job summary.

## Schema change log (all monitored datasets)

The change history records what bqchange **applied** (its own scripts). The
schema change log records what bqchange **observes** in BigQuery's catalog, for
**every table and view** of the monitored datasets, whoever changed them:
migrations, dbt models or people in the console. `bqchange record-schema`:

1. It reads `INFORMATION_SCHEMA.COLUMNS` of the dataset of every layer in `schema-log-layers`.
2. It compares the result with the previous snapshot (`<env>_meta.schema_state`),
   **by layer**, so a pull request clone compares correctly with the DEV state it inherited.
3. Every change becomes one row in `<env>_meta.schema_change_log`, with its
   **source** and the GitHub context (commit, pull request, workflow run, actor):

   | Level | Changes | `change_type` |
   | --- | --- | --- |
   | Column | added, removed, type changed | `added`, `removed`, `type_changed` |
   | Column | description | `property_added` / `property_removed` / `property_changed` with `property = description` |
   | Table | table type, partitioning, clustering, every table option (`option:description`, `option:labels`, `option:expiration_timestamp`…) | `property_*` with `column_name = (table)` |

   The first run records a column **baseline**; the first property snapshot only
   sets the state. Properties of tables being created or dropped are not listed
   (the column changes already describe the table).
4. The new snapshots replace the old ones (`schema_state`, `schema_state_properties`).

Coverage: only the datasets of `schema-log-layers`. Add a layer to watch any
other dataset, including one no tool manages.

Pipelines call it around each step, so every change is attributed to whoever made it:

| Call | Records changes made by |
| --- | --- |
| `record-schema --source manual` (before anything runs) | someone outside the pipeline since the last snapshot |
| `record-schema --source migration` (after `deploy`) | bqchange scripts |
| `record-schema --source dbt` (after `dbt build`) | dbt models |

The view `<env>_audit.schema_history` lists every non-baseline change, newest first.

## Change history table

| Column              | Type      |
| ------------------- | --------- |
| `version`           | STRING    |
| `description`       | STRING    |
| `script`            | STRING    |
| `script_type`       | STRING    |
| `checksum`          | STRING (SHA-224 of the rendered script) |
| `execution_time_ms` | INT64     |
| `status`            | STRING    |
| `installed_by`      | STRING    |
| `installed_on`      | TIMESTAMP |
