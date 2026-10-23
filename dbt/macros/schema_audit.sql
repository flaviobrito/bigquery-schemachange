{#-
  Renders every column declared in the dbt project as rows, straight from the
  project graph at compile time:
    - source layers: columns of sources (tables created by migrations)
    - other layers: columns of models (tables and views built by dbt, under contract)
  Used by audit_schema_drift to compare the code against INFORMATION_SCHEMA.
-#}
{% macro declared_columns(layers) -%}
    {%- set layer_of = {} -%}
    {%- for layer in layers -%}
        {%- do layer_of.update({layer_dataset(layer) | trim | lower: layer}) -%}
    {%- endfor -%}
    {%- set rows = [] -%}
    {%- if execute -%}
        {%- set nodes = (graph.sources.values() | list) + (graph.nodes.values() | list) -%}
        {%- for node in nodes -%}
            {%- set is_relation = node.resource_type == 'source'
                or (node.resource_type == 'model' and node.config.materialized != 'ephemeral') -%}
            {%- if is_relation and node.schema | lower in layer_of -%}
                {%- set table_name = node.identifier if node.resource_type == 'source' else node.alias -%}
                {%- for column_name in node.columns -%}
                    {%- do rows.append(
                        "('" ~ layer_of[node.schema | lower] ~ "', '"
                        ~ node.schema | lower ~ "', '"
                        ~ table_name | lower ~ "', '"
                        ~ column_name | lower ~ "', '"
                        ~ (node.columns[column_name].data_type or '') | upper ~ "')"
                    ) -%}
                {%- endfor -%}
            {%- endif -%}
        {%- endfor -%}
    {%- endif -%}
    {%- if rows | length == 0 -%}
        {%- do rows.append("(null, null, null, null, null)") -%}
    {%- endif -%}
    select *
    from unnest(
        array<struct<
            layer string,
            table_schema string,
            table_name string,
            column_name string,
            declared_data_type string
        >>[
            {{ rows | join(',\n            ') }}
        ]
    )
{%- endmacro %}

{#- Physical columns of several layers, unioned from their INFORMATION_SCHEMA views. -#}
{% macro physical_columns(layers) -%}
    {%- for layer in layers %}
    select
        '{{ layer }}' as layer,
        table_schema,
        table_name,
        column_name,
        data_type,
        ordinal_position,
        is_nullable
    from `{{ target.project }}.{{ layer_dataset(layer) }}.INFORMATION_SCHEMA.COLUMNS`
    -- dbt's own transient relations (incremental merges, swaps) are not drift.
    where not regexp_contains(table_name, r'__dbt_(tmp|backup)')
    {%- if not loop.last %}
    union all
    {%- endif %}
    {%- endfor %}
{%- endmacro %}

{#- Layers watched by the schema audit (var('monitored_layers')). -#}
{% macro monitored_layers() -%}
    {{ return(var('monitored_layers')) }}
{%- endmacro %}
