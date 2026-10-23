{#-
  Environments share one GCP project and are isolated by dataset prefix (BQ_ENV).
  A custom schema that names a declared layer (var('layers')) resolves to that
  layer's dataset, e.g. +schema: silver -> dev_silver.
-#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- elif custom_schema_name | trim | lower in var('layers') -%}
        {{ layer_dataset(custom_schema_name | trim | lower) }}
    {%- else -%}
        {{ env_var('BQ_ENV') }}_{{ custom_schema_name | trim | lower }}
    {%- endif -%}
{%- endmacro %}
