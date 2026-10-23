-- Net payments above the order total indicate double charging or bad joins.
{{ config(severity='warn') }}

select
    order_id,
    order_total,
    net_paid_amount
from {{ ref('fct_orders') }}
where net_paid_amount > order_total + 0.01
