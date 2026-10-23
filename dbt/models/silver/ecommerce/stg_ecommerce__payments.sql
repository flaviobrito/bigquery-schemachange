-- One row per payment transaction.
with source as (

    select * from {{ source('ecommerce', 'payments') }}

),

deduplicated as (

    select *
    from source
    where true
    qualify
        row_number() over (
            partition by payment_id
            order by _loaded_at desc
        ) = 1

)

select
    trim(payment_id) as payment_id,
    trim(order_id) as order_id,
    lower(trim(payment_method)) as payment_method,
    lower(trim(payment_status)) as payment_status,
    {{ money('amount') }} as amount,
    paid_at,
    _loaded_at as loaded_at
from deduplicated
