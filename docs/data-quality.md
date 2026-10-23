# Data quality

Checks are layered so that problems are caught as close to the source as
possible, while raw data is never silently discarded.

| Layer  | Mechanism                         | Severity | Where                                      |
| ------ | --------------------------------- | -------- | ------------------------------------------ |
| BRONZE | dbt source tests and freshness    | warn     | `_ecommerce__sources.yml`                  |
| SILVER | dbt data tests                    | error*   | `_ecommerce__models.yml`                   |
| GOLD   | Contracts, data and unit tests    | error*   | `_core__models.yml`, `_finance__models.yml` |
| AUDIT  | Schema drift                      | error    | `audit_schema_drift`, `assert_no_bronze_schema_drift` |

\* A few business heuristics are `warn` (see below). Failing rows of every test
are stored in the `<env>_audit` dataset, one table per test.

The email rule lives in one place: the persistent UDF
`<env>_audit.is_valid_email`, created by `R__shared_routines.sql` and used both
by `stg_ecommerce__customers.is_email_valid` and the `is_valid_email` generic test.

## dbt tests

| Category               | Examples                                                                 |
| ---------------------- | ------------------------------------------------------------------------ |
| Freshness              | Sources warn after 24 h and error after 72 h; `dbt_utils.recency` on `fct_orders` |
| Volume                 | `expect_table_row_count_to_be_between` (source), `expect_table_row_count_to_equal_other_table` (SILVER vs GOLD) |
| Uniqueness             | `unique`, `dbt_utils.unique_combination_of_columns`                       |
| Completeness           | `not_null`, contract `not_null` constraints                               |
| Referential integrity  | `relationships` on every foreign key, source to GOLD                      |
| Validity               | `accepted_values`, `dbt_utils.accepted_range`, `expect_column_values_to_match_regex`, custom `is_valid_email`, `non_negative` |
| Business rules         | `order_total = items - discount + shipping`, `unit_cost <= unit_price`, delivered orders are paid, payments do not exceed totals, revenue reconciles between `fct_orders` and `agg_daily_revenue` |
| Logic (unit tests)     | `fct_orders` totals and revenue flag; `dim_customers` segmentation        |
| Structure              | Enforced contracts (types and numeric precision) on all GOLD models; schema drift between BRONZE and sources |

## Warn vs error

- **BRONZE source tests warn.** Raw duplicates and invalid emails are expected and
  are handled in SILVER (deduplication, `is_email_valid`).
- **SILVER and GOLD tests error**, except heuristics that can legitimately occur
  (cost above price, discount above items amount, orders without items, stale
  data, payments above total) which warn.
- Run `python -m ops.generate_sample_data --inject-anomalies` and load it into a
  development environment to see the error-level tests fail.
