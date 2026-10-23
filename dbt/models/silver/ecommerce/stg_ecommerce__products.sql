-- One row per product with normalized catalog attributes.
with source as (

    select * from {{ source('ecommerce', 'products') }}

),

deduplicated as (

    select *
    from source
    where true
    qualify
        row_number() over (
            partition by product_id
            order by updated_at desc nulls last, _loaded_at desc
        ) = 1

)

select
    trim(product_id) as product_id,
    upper(trim(sku)) as sku,
    trim(product_name) as product_name,
    lower(trim(category)) as category,
    trim(brand) as brand,
    {{ money('unit_price') }} as unit_price,
    {{ money('unit_cost') }} as unit_cost,
    coalesce(is_active, false) as is_active,
    created_at,
    updated_at,
    _loaded_at as loaded_at
from deduplicated
