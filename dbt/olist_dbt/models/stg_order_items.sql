with source as (
    select * from {{ source(env_var('TARGET_BIGQUERY_DATASET_ID'), 'olist_order_items_dataset') }}
)

select
    cast(order_id as string) as order_id,
    cast(order_item_id as int64) as order_item_sequence,
    cast(product_id as string) as product_id,
    cast(seller_id as string) as seller_id,
    cast(shipping_limit_date as timestamp) as shipping_limit_at,
    cast(price as numeric) as item_price_amount,
    cast(freight_value as numeric) as freight_cost_amount
from source