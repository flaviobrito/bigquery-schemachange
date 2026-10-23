{#-
  Shared Jinja macros for migration scripts.
  Import with: {% import "modules/bronze.sql" as bronze %}
-#}

{#- Standard lineage columns appended to every BRONZE landing table. -#}
{% macro metadata_columns() -%}
    _source_file string options (description = 'File the row was loaded from'),
    _source_row_number int64 options (description = 'Row number inside the source file'),
    _loaded_at timestamp default current_timestamp()
        options (description = 'Load timestamp, used for source freshness')
{%- endmacro %}

{#- Partitioning and clustering shared by landing tables. -#}
{% macro landing_options(cluster_column, description) -%}
partition by date(_loaded_at)
cluster by {{ cluster_column }}
options (description = '{{ description }}', labels = [('layer', 'bronze')])
{%- endmacro %}
