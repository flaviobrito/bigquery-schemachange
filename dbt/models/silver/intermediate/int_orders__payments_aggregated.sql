-- Order-level rollup of payment transactions.
with payments as (

    select * from {{ ref('stg_ecommerce__payments') }}

)

select
    order_id,
    count(*) as payment_attempt_count,
    sum(if(payment_status = 'approved', amount, 0)) as approved_amount,
    sum(if(payment_status = 'refunded', amount, 0)) as refunded_amount,
    array_agg(payment_method order by paid_at desc limit 1)[safe_offset(0)]
        as last_payment_method,
    max(if(payment_status = 'approved', paid_at, null)) as last_approved_at
from payments
group by order_id
