{#-
  Environments share one GCP project and are isolated by dataset prefix:
  dev_silver, prod_gold, pr_42_audit... BQ_ENV holds the prefix.
-#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ env_var('BQ_ENV') }}_{{ custom_schema_name | trim | lower }}
    {%- endif -%}
{%- endmacro %}
