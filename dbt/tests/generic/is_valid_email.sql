{#- Fails for non-null values rejected by the is_valid_email UDF (R__shared_routines.sql). -#}
{% test is_valid_email(model, column_name) %}

select {{ column_name }}
from {{ model }}
where {{ column_name }} is not null
    and not coalesce({{ udf('is_valid_email') }}({{ column_name }}), false)

{% endtest %}
