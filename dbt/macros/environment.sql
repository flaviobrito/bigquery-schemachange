{#- Dataset of a medallion layer in the current environment, e.g. dev_bronze. -#}
{% macro layer_dataset(layer) -%}
    {{ env_var('BQ_ENV') }}_{{ layer }}
{%- endmacro %}

{#- Fully qualified persistent UDF created by migrations (R__shared_routines.sql). -#}
{% macro udf(name) -%}
    `{{ target.project }}.{{ layer_dataset('audit') }}.{{ name }}`
{%- endmacro %}
