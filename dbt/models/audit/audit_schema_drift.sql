-- Compares the physical BRONZE schema with the columns declared in dbt sources.
-- Any status other than 'aligned' is drift: a migration without a matching
-- source declaration, a manual change in BigQuery, or a stale YAML entry.
{{ config(materialized='view') }}

with physical as (

    select
        table_schema,
        table_name,
        column_name,
        -- Parameterized types such as NUMERIC(12, 2) are compared by base type.
        split(data_type, '(')[offset(0)] as physical_data_type
    from `{{ target.project }}.{{ layer_dataset('bronze') }}.INFORMATION_SCHEMA.COLUMNS`

),

declared as (

    {{ declared_source_columns(layer_dataset('bronze')) }}

),

declared_normalized as (

    select
        table_schema,
        table_name,
        column_name,
        case split(declared_data_type, '(')[offset(0)]
            when 'INTEGER' then 'INT64'
            when 'BOOLEAN' then 'BOOL'
            when 'DECIMAL' then 'NUMERIC'
            when 'FLOAT' then 'FLOAT64'
            else split(declared_data_type, '(')[offset(0)]
        end as declared_data_type
    from declared
    where table_name is not null

)

select
    coalesce(physical.table_schema, declared_normalized.table_schema) as table_schema,
    coalesce(physical.table_name, declared_normalized.table_name) as table_name,
    coalesce(physical.column_name, declared_normalized.column_name) as column_name,
    physical.physical_data_type,
    declared_normalized.declared_data_type,
    case
        when physical.column_name is null then 'missing_in_database'
        when declared_normalized.column_name is null then 'undeclared_in_dbt'
        when declared_normalized.declared_data_type != ''
            and declared_normalized.declared_data_type != physical.physical_data_type
            then 'type_mismatch'
        else 'aligned'
    end as drift_status,
    current_timestamp() as checked_at
from physical
full outer join declared_normalized
    on lower(physical.table_schema) = declared_normalized.table_schema
        and lower(physical.table_name) = declared_normalized.table_name
        and lower(physical.column_name) = declared_normalized.column_name
