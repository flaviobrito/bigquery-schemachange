-- Delivered orders must have an approved payment.
select
    order_id,
    order_status,
    approved_payment_amount
from {{ ref('fct_orders') }}
where order_status = 'delivered'
    and approved_payment_amount = 0
