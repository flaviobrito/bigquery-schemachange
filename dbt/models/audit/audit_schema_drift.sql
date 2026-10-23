-- Compares the physical schema of BRONZE, SILVER and GOLD with what the dbt
-- project declares: sources for BRONZE, model contracts for SILVER and GOLD.
-- Any status other than 'aligned' is drift: a migration without a matching
-- source declaration, a manual ALTER in BigQuery, or a stale YAML entry.
{{ config(materialized='view') }}

with physical as (

    select
        table_schema,
        table_name,
        column_name,
        -- Parameterized types such as NUMERIC(18, 2) are compared by base type.
        split(data_type, '(')[offset(0)] as physical_data_type
    from ({{ physical_columns(monitored_datasets()) }})

),

declared as (

    {{ declared_columns(monitored_datasets()) }}

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

),

compared as (

    select
        coalesce(lower(physical.table_schema), declared_normalized.table_schema) as table_schema,
        coalesce(lower(physical.table_name), declared_normalized.table_name) as table_name,
        coalesce(lower(physical.column_name), declared_normalized.column_name) as column_name,
        physical.physical_data_type,
        declared_normalized.declared_data_type,
        case
            when physical.column_name is null then 'missing_in_database'
            when declared_normalized.column_name is null then 'undeclared_in_dbt'
            when declared_normalized.declared_data_type != ''
                and declared_normalized.declared_data_type != physical.physical_data_type
                then 'type_mismatch'
            else 'aligned'
        end as drift_status
    from physical
    full outer join declared_normalized
        on lower(physical.table_schema) = declared_normalized.table_schema
            and lower(physical.table_name) = declared_normalized.table_name
            and lower(physical.column_name) = declared_normalized.column_name

),

built_relations as (

    select distinct
        lower(table_schema) as table_schema,
        lower(table_name) as table_name
    from physical

)

select
    regexp_extract(compared.table_schema, r'_([a-z]+)$') as layer,
    compared.table_schema,
    compared.table_name,
    compared.column_name,
    compared.physical_data_type,
    compared.declared_data_type,
    compared.drift_status,
    current_timestamp() as checked_at
from compared
left join built_relations
    on compared.table_schema = built_relations.table_schema
        and compared.table_name = built_relations.table_name
-- A SILVER/GOLD model not built yet in this environment is not drift;
-- a missing BRONZE table always is (BRONZE must exist before dbt runs).
where
    built_relations.table_name is not null
    or regexp_extract(compared.table_schema, r'_([a-z]+)$') = 'bronze'
