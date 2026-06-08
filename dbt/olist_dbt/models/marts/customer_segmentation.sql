{{ config(materialized='table') }}

with customer_spend as (
    select
        c.customer_unique_id,
        c.customer_city,
        c.customer_state,
        count(distinct o.order_id) as total_orders,
        sum(p.payment_value) as total_spent
    from {{ source('olist', 'olist_customers_dataset') }} c
    join {{ source('olist', 'olist_orders_dataset') }} o
        on c.customer_id = o.customer_id
    join {{ source('olist', 'olist_order_payments_dataset') }} p
        on o.order_id = p.order_id
    group by
        c.customer_unique_id,
        c.customer_city,
        c.customer_state
)

select
    *,
    case
        when total_spent >= 1000 then 'Gold'
        when total_spent >= 300 then 'Silver'
        else 'Bronze'
    end as customer_segment
from customer_spend