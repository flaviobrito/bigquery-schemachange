{#-
  Renders the columns declared in dbt sources as rows, straight from the
  project graph at compile time. Used by audit_schema_drift to compare the
  code contract against the physical INFORMATION_SCHEMA.
-#}
{% macro declared_source_columns(dataset_name) -%}
    {%- set rows = [] -%}
    {%- if execute -%}
        {%- for source in graph.sources.values() -%}
            {%- if source.schema | lower == dataset_name | lower -%}
                {%- for column_name in source.columns -%}
                    {%- do rows.append(
                        "('" ~ source.schema | lower ~ "', '"
                        ~ source.identifier | lower ~ "', '"
                        ~ column_name | lower ~ "', '"
                        ~ (source.columns[column_name].data_type or '') | upper ~ "')"
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
