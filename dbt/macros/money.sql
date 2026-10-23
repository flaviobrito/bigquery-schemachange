{#- Rounds monetary values to two decimals as NUMERIC across all models. -#}
{% macro money(expression, scale=2) -%}
    cast(round({{ expression }}, {{ scale }}) as numeric)
{%- endmacro %}
