-- Order line grain fact enriched with product and order context.
with order_items as (

    select * from {{ ref('stg_ecommerce__order_items') }}

),

orders as (

    select * from {{ ref('stg_ecommerce__orders') }}

),

products as (

    select * from {{ ref('stg_ecommerce__products') }}

)

select
    order_items.order_item_id,
    order_items.order_id,
    order_items.product_id,
    orders.customer_id,
    orders.order_date,
    orders.order_status,
    products.category as product_category,
    order_items.quantity,
    order_items.unit_price,
    order_items.line_amount,
    {{ money('order_items.quantity * products.unit_cost') }} as line_cost,
    {{ money('order_items.line_amount - order_items.quantity * products.unit_cost') }}
        as line_margin
from order_items
inner join orders
    on order_items.order_id = orders.order_id
left join products
    on order_items.product_id = products.product_id
