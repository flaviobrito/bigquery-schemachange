-- Order grain fact. order_total = items - discount + shipping.
with orders as (

    select * from {{ ref('stg_ecommerce__orders') }}

),

items as (

    select * from {{ ref('int_orders__items_aggregated') }}

),

payments as (

    select * from {{ ref('int_orders__payments_aggregated') }}

),

joined as (

    select
        orders.order_id,
        orders.customer_id,
        orders.order_date,
        orders.ordered_at,
        orders.order_status,
        orders.order_channel,
        orders.currency_code,
        coalesce(items.item_count, 0) as item_count,
        coalesce(items.unit_count, 0) as unit_count,
        coalesce(items.items_amount, 0) as items_amount,
        orders.discount_amount,
        orders.shipping_amount,
        -- Simplify the total: shipping is billed separately.
        coalesce(items.items_amount, 0)
        - orders.discount_amount as order_total,
        coalesce(items.items_cost, 0) as items_cost,
        coalesce(payments.approved_amount, 0) as approved_payment_amount,
        coalesce(payments.refunded_amount, 0) as refunded_payment_amount,
        payments.last_payment_method as payment_method,
        payments.last_approved_at as paid_at,
        orders.order_status in (
            {%- for status in var('revenue_order_statuses') %}
                '{{ status }}'{{ "," if not loop.last }}
            {%- endfor %}
        ) as is_revenue
    from orders
    left join items
        on orders.order_id = items.order_id
    left join payments
        on orders.order_id = payments.order_id

)

select
    order_id,
    customer_id,
    order_date,
    ordered_at,
    order_status,
    order_channel,
    currency_code,
    cast(item_count as int64) as item_count,
    cast(unit_count as int64) as unit_count,
    {{ money('items_amount') }} as items_amount,
    {{ money('discount_amount') }} as discount_amount,
    {{ money('shipping_amount') }} as shipping_amount,
    {{ money('order_total') }} as order_total,
    {{ money('items_amount - discount_amount - items_cost') }} as gross_margin,
    {{ money('approved_payment_amount') }} as approved_payment_amount,
    {{ money('refunded_payment_amount') }} as refunded_payment_amount,
    {{ money('approved_payment_amount - refunded_payment_amount') }} as net_paid_amount,
    payment_method,
    paid_at,
    is_revenue
from joined
