-- One row per order line with its extended amount.
with source as (

    select * from {{ source('ecommerce', 'order_items') }}

),

deduplicated as (

    select *
    from source
    where true
    qualify
        row_number() over (
            partition by order_item_id
            order by _loaded_at desc
        ) = 1

)

select
    trim(order_item_id) as order_item_id,
    trim(order_id) as order_id,
    trim(product_id) as product_id,
    quantity,
    {{ money('unit_price') }} as unit_price,
    {{ money('quantity * unit_price') }} as line_amount,
    _loaded_at as loaded_at
from deduplicated
