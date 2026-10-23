-- Order-level rollup of line items, joined to product cost for margin.
with order_items as (

    select * from {{ ref('stg_ecommerce__order_items') }}

),

products as (

    select * from {{ ref('stg_ecommerce__products') }}

)

select
    order_items.order_id,
    count(*) as item_count,
    sum(order_items.quantity) as unit_count,
    sum(order_items.line_amount) as items_amount,
    sum(order_items.quantity * products.unit_cost) as items_cost
from order_items
left join products
    on order_items.product_id = products.product_id
group by order_items.order_id
