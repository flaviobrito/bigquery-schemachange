{#-
  Renders every column declared in the dbt project as rows, straight from the
  project graph at compile time:
    - BRONZE: columns of sources (tables created by migrations)
    - SILVER/GOLD: columns of models (tables and views built by dbt, all under contract)
  Used by audit_schema_drift to compare the code against INFORMATION_SCHEMA.
-#}
{% macro declared_columns(dataset_names) -%}
    {%- set datasets = dataset_names | map('lower') | list -%}
    {%- set rows = [] -%}
    {%- if execute -%}
        {%- set nodes = (graph.sources.values() | list) + (graph.nodes.values() | list) -%}
        {%- for node in nodes -%}
            {%- set is_relation = node.resource_type == 'source'
                or (node.resource_type == 'model' and node.config.materialized != 'ephemeral') -%}
            {%- if is_relation and node.schema | lower in datasets -%}
                {%- set table_name = node.identifier if node.resource_type == 'source' else node.alias -%}
                {%- for column_name in node.columns -%}
                    {%- do rows.append(
                        "('" ~ node.schema | lower ~ "', '"
                        ~ table_name | lower ~ "', '"
                        ~ column_name | lower ~ "', '"
                        ~ (node.columns[column_name].data_type or '') | upper ~ "')"
                    ) -%}
                {%- endfor -%}
            {%- endif -%}
        {%- endfor -%}
    {%- endif -%}
    {%- if rows | length == 0 -%}
        {%- do rows.append("(null, null, null, null)") -%}
    {%- endif -%}
    select *
    from unnest(
        array<struct<
            table_schema string,
            table_name string,
            column_name string,
            declared_data_type string
        >>[
            {{ rows | join(',\n            ') }}
        ]
    )
{%- endmacro %}

{#- Physical columns of several datasets, unioned from their INFORMATION_SCHEMA views. -#}
{% macro physical_columns(dataset_names) -%}
    {%- for dataset in dataset_names %}
    select
        table_schema,
        table_name,
        column_name,
        data_type,
        ordinal_position,
        is_nullable
    from `{{ target.project }}.{{ dataset }}.INFORMATION_SCHEMA.COLUMNS`
    -- dbt's own transient relations (incremental merges, swaps) are not drift.
    where not regexp_contains(table_name, r'__dbt_(tmp|backup)')
    {%- if not loop.last %}
    union all
    {%- endif %}
    {%- endfor %}
{%- endmacro %}

{#- Datasets watched by the schema audit: every medallion layer of the environment. -#}
{% macro monitored_datasets() -%}
    {{ return([layer_dataset('bronze'), layer_dataset('silver'), layer_dataset('gold')]) }}
{%- endmacro %}
