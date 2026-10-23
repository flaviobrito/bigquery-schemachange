-- Daily revenue by sales channel, revenue-recognized orders only.
-- Partitioned by day: dashboards always filter by date, so queries scan less.
{{ config(partition_by={'field': 'order_date', 'data_type': 'date'}) }}
select
    order_date,
    order_channel,
    count(*) as order_count,
    count(distinct customer_id) as customer_count,
    sum(unit_count) as unit_count,
    {{ money('sum(order_total)') }} as revenue,
    {{ money('sum(gross_margin)') }} as gross_margin,
    {{ money('avg(order_total)') }} as average_order_value
from {{ ref('fct_orders') }}
where is_revenue
group by order_date, order_channel
