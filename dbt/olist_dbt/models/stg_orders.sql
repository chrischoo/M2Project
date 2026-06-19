with source as (
    select * from {{ source(env_var('TARGET_BIGQUERY_DATASET_ID'), 'olist_orders_dataset') }}
)

select
    cast(order_id as string) as order_id,
    cast(customer_id as string) as customer_id,
    cast(order_status as string) as order_status,
    
    -- Safe timestamp parsing handling empty string records
    cast(nullif(order_purchase_timestamp, '') as timestamp) as purchased_at,
    cast(nullif(order_approved_at, '') as timestamp) as approved_at,
    cast(nullif(order_delivered_carrier_date, '') as timestamp) as delivered_to_carrier_at,
    cast(nullif(order_delivered_customer_date, '') as timestamp) as delivered_to_customer_at,
    cast(nullif(order_estimated_delivery_date, '') as timestamp) as estimated_delivery_at
from source