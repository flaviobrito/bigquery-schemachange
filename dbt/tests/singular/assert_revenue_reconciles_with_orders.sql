-- GOLD aggregate must reconcile with the order fact it is built from.
with aggregate_revenue as (

    select sum(revenue) as revenue from {{ ref('agg_daily_revenue') }}

),

order_revenue as (

    select sum(order_total) as revenue from {{ ref('fct_orders') }}
    where is_revenue

)

select
    aggregate_revenue.revenue as aggregate_revenue,
    order_revenue.revenue as order_revenue
from aggregate_revenue
cross join order_revenue
where abs(coalesce(aggregate_revenue.revenue, 0) - coalesce(order_revenue.revenue, 0)) > 0.01
