{#- Dataset of a logical layer in the current environment, from var('layers'). -#}
{% macro layer_dataset(layer) -%}
    {%- set layers = var('layers') -%}
    {#- Outside dbt (sqlfluff linting) var() is a stub: fall back to the layer name. -#}
    {%- if layers is mapping and layer not in layers -%}
        {{ exceptions.raise_compiler_error(
            "Unknown layer '" ~ layer ~ "'. Declared layers: " ~ (layers | list | join(', '))
        ) }}
    {%- endif -%}
    {{ env_var('BQ_ENV') }}_{{ layers[layer] if layers is mapping else layer }}
{%- endmacro %}

{#- Fully qualified persistent UDF created by migrations (R__shared_routines.sql). -#}
{% macro udf(name) -%}
    `{{ target.project }}.{{ layer_dataset('audit') }}.{{ name }}`
{%- endmacro %}
