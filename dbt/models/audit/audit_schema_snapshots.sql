-- Physical column history of every medallion layer (BRONZE, SILVER, GOLD).
-- Each column signature (dataset, table, column, type) is inserted once with
-- first_seen_at; later runs only refresh last_seen_at, so dropped or retyped
-- columns keep their history.
{{
    config(
        materialized='incremental',
        unique_key='column_signature',
        incremental_strategy='merge',
        on_schema_change='append_new_columns',
        merge_update_columns=['ordinal_position', 'is_nullable', 'last_seen_at']
    )
}}

with physical_columns as (

    {{ physical_columns(monitored_datasets()) }}

)

select
    {{ dbt_utils.generate_surrogate_key(
        ['table_schema', 'table_name', 'column_name', 'data_type']
    ) }} as column_signature,
    regexp_extract(table_schema, r'_([a-z]+)$') as layer,
    table_schema,
    table_name,
    column_name,
    data_type,
    ordinal_position,
    is_nullable = 'YES' as is_nullable,
    current_timestamp() as first_seen_at,
    current_timestamp() as last_seen_at
from physical_columns
