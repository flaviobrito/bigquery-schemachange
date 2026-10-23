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

`project` and `location` are always available to scripts as variables.

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
bqchange --config other.yml ...
```

In a dry run, a script that references objects created by an earlier pending
script cannot be validated yet; it is reported as such instead of failing. Only
an invalid first pending script fails the plan.

When `GITHUB_STEP_SUMMARY` is set, `deploy` appends a Markdown table of the
planned or applied scripts to the GitHub Actions job summary.

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
