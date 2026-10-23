-- Incremental: only rows landed since the last run are merged on order_id,
-- so late status updates (e.g. shipped -> delivered) overwrite the old version.
{{
    config(
        materialized='incremental',
        unique_key='order_id',
        incremental_strategy='merge',
        on_schema_change='append_new_columns',
        partition_by={'field': 'order_date', 'data_type': 'date'},
        cluster_by=['customer_id']
    )
}}

with source as (

    select * from {{ source('ecommerce', 'orders') }}
    -- Jinja blocks confuse the indentation rule; keep the SQL readable instead.
    -- noqa: disable=LT02
    {% if is_incremental() %}
    where _loaded_at > (
        select coalesce(max(existing.loaded_at), timestamp('1900-01-01'))
        from {{ this }} as existing
    )
    {% endif %}
    -- noqa: enable=LT02

),

deduplicated as (

    select *
    from source
    where true
    qualify
        row_number() over (
            partition by order_id
            order by updated_at desc nulls last, _loaded_at desc
        ) = 1

)

select
    trim(order_id) as order_id,
    trim(customer_id) as customer_id,
    lower(trim(order_status)) as order_status,
    lower(trim(order_channel)) as order_channel,
    upper(trim(currency_code)) as currency_code,
    {{ money('coalesce(shipping_amount, 0)') }} as shipping_amount,
    {{ money('coalesce(discount_amount, 0)') }} as discount_amount,
    ordered_at,
    date(ordered_at) as order_date,
    updated_at,
    _loaded_at as loaded_at
from deduplicated
