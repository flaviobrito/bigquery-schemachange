-- Version 1 (deprecated): exposes the raw email. Kept at the original relation
-- name `dim_customers` until its deprecation date so consumers can migrate to v2.
with customers as (

    select * from {{ ref('stg_ecommerce__customers') }}

),

orders as (

    select * from {{ ref('fct_orders') }}
    where is_revenue

),

customer_orders as (

    select
        customer_id,
        min(ordered_at) as first_order_at,
        max(ordered_at) as last_order_at,
        count(*) as lifetime_order_count,
        sum(order_total) as lifetime_revenue
    from orders
    group by customer_id

)

select
    customers.customer_id,
    customers.full_name,
    customers.email,
    customers.is_email_valid,
    customers.country_code,
    customers.state,
    customers.city,
    customers.has_marketing_opt_in,
    customers.created_at as customer_since,
    customer_orders.first_order_at,
    customer_orders.last_order_at,
    cast(coalesce(customer_orders.lifetime_order_count, 0) as int64) as lifetime_order_count,
    {{ money('coalesce(customer_orders.lifetime_revenue, 0)') }} as lifetime_revenue,
    case
        when customer_orders.lifetime_order_count is null then 'prospect'
        when customer_orders.lifetime_revenue >= 2000 then 'vip'
        when customer_orders.lifetime_order_count >= 2 then 'returning'
        else 'new'
    end as customer_segment
from customers
left join customer_orders
    on customers.customer_id = customer_orders.customer_id
