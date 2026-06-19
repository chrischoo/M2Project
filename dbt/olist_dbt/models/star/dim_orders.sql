with staging_orders as (
    select * from {{ ref('stg_orders') }}
)

select
    order_id,
    customer_id,
    order_status,
    purchased_at,
    approved_at,
    delivered_to_carrier_at,
    delivered_to_customer_at,
    estimated_delivery_at
from staging_orders