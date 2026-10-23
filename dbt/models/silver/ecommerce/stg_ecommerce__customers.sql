-- One row per customer: latest exported version, standardized attributes.
-- Email validity uses the persistent UDF created by R__shared_routines.sql.
with source as (

    select * from {{ source('ecommerce', 'customers') }}

),

deduplicated as (

    select *
    from source
    where true
    qualify
        row_number() over (
            partition by customer_id
            order by updated_at desc nulls last, _loaded_at desc
        ) = 1

)

select
    trim(customer_id) as customer_id,
    initcap(trim(first_name)) as first_name,
    initcap(trim(last_name)) as last_name,
    concat(initcap(trim(first_name)), ' ', initcap(trim(last_name))) as full_name,
    lower(trim(email)) as email,
    coalesce({{ udf('is_valid_email') }}(email), false) as is_email_valid,
    nullif(regexp_replace(phone, r'[^0-9+]', ''), '') as phone,
    upper(trim(country_code)) as country_code,
    trim(state) as state,
    initcap(trim(city)) as city,
    coalesce(marketing_opt_in, false) as has_marketing_opt_in,
    created_at,
    updated_at,
    _loaded_at as loaded_at
from deduplicated
