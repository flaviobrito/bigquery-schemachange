# Scenario 4: broken source data is blocked

[Workflow run](https://github.com/flaviobrito/bigquery-schemachange/actions/runs/39885807472)

## Input

`dq-gate-demo.yml` (manual) clones DEV into a throwaway environment and loads data generated with `--inject-anomalies`: 5 invalid emails, an order for a non-existent customer, a negative price and an unknown order status.

## Expected outcome

BRONZE tests report the problems as warnings; SILVER tests fail with errors; GOLD models are skipped so bad data never reaches them; the throwaway environment is dropped.

## Actual outcome: ❌ blocked

### Migrations (bqchange)

```text
INFO    APPLY repeatable/R__audit_views.sql (content changed)
INFO    APPLY repeatable/R__shared_routines.sql (content changed)
INFO    APPLY always/A__dataset_options.sql (always)
INFO    APPLY always/A__grants.sql (always)
```

### dbt results

```text
4 of 103 WARN 1 source_accepted_values_ecommerce_orders_order_status__placed__paid__shipped__delivered__cancelled__returned  [WARN 1 in 2.50s]
5 of 103 WARN 5 source_is_valid_email_ecommerce_customers_email ................ [WARN 5 in 2.67s]
13 of 103 WARN 500 source_unique_ecommerce_customers_customer_id ............... [WARN 500 in 2.60s]
14 of 103 WARN 7551 source_unique_ecommerce_order_items_order_item_id .......... [WARN 7551 in 2.54s]
12 of 103 WARN 1 source_relationships_ecommerce_orders_customer_id__customer_id__source_ecommerce_customers_  [WARN 1 in 2.97s]
15 of 103 WARN 3000 source_unique_ecommerce_orders_order_id .................... [WARN 3000 in 2.80s]
17 of 103 WARN 60 source_unique_ecommerce_products_product_id .................. [WARN 60 in 2.35s]
16 of 103 WARN 3000 source_unique_ecommerce_payments_payment_id ................ [WARN 3000 in 3.26s]
34 of 103 FAIL 1 non_negative_stg_ecommerce__order_items_unit_price ............ [FAIL 1 in 2.43s]
57 of 103 FAIL 1 accepted_values_stg_ecommerce__orders_order_status__placed__paid__shipped__delivered__cancelled__returned  [FAIL 1 in 2.62s]
66 of 103 FAIL 1 relationships_stg_ecommerce__orders_customer_id__customer_id__ref_stg_ecommerce__customers_  [FAIL 1 in 2.47s]
Done. PASS=63 WARN=8 ERROR=3 SKIP=29 NO-OP=0 REUSED=0 TOTAL=103
```

### Run report

### Schema and data quality report · `pr_39885807472`

#### dbt (build)

❌ fail: 3 · ✅ pass: 54 · ⏭️ skipped: 29 · ✅ success: 9 · ⚠️ warn: 8

| Status | Node | Failures | Message |
| --- | --- | --- | --- |
| ⚠️ warn | `source_accepted_values_ecommerce_orders_order_status__placed__paid__shipped__delivered__cancelled__returned` | 1 | Got 1 result, configured to warn if != 0 |
| ⚠️ warn | `source_is_valid_email_ecommerce_customers_email` | 5 | Got 5 results, configured to warn if != 0 |
| ⚠️ warn | `source_unique_ecommerce_customers_customer_id` | 500 | Got 500 results, configured to warn if != 0 |
| ⚠️ warn | `source_unique_ecommerce_order_items_order_item_id` | 7551 | Got 7551 results, configured to warn if != 0 |
| ⚠️ warn | `source_relationships_ecommerce_orders_customer_id__customer_id__source_ecommerce_customers_` | 1 | Got 1 result, configured to warn if != 0 |
| ⚠️ warn | `source_unique_ecommerce_orders_order_id` | 3000 | Got 3000 results, configured to warn if != 0 |
| ⚠️ warn | `source_unique_ecommerce_products_product_id` | 60 | Got 60 results, configured to warn if != 0 |
| ⚠️ warn | `source_unique_ecommerce_payments_payment_id` | 3000 | Got 3000 results, configured to warn if != 0 |
| ❌ fail | `non_negative_stg_ecommerce__order_items_unit_price` | 1 | Got 1 result, configured to fail if != 0 |
| ❌ fail | `accepted_values_stg_ecommerce__orders_order_status__placed__paid__shipped__delivered__cancelled__returned` | 1 | Got 1 result, configured to fail if != 0 |
| ❌ fail | `relationships_stg_ecommerce__orders_customer_id__customer_id__ref_stg_ecommerce__customers_` | 1 | Got 1 result, configured to fail if != 0 |
