{{ config(
    materialized='table'
) }}

with order_items as (
    select * from {{ ref('stg_order_items') }}
),

fulfilled_orders as (
    select 
        order_id,
        customer_id,
        order_status,
        purchased_at
    from {{ ref('stg_orders') }}
    where order_status = 'delivered' -- Simplified to status check only
)

select
    {{ dbt_utils.generate_surrogate_key(['oi.order_id', 'oi.order_item_sequence']) }} as order_item_key,
    oi.order_id,
    oi.product_id,
    oi.seller_id,
    fo.customer_id,
    oi.order_item_sequence,
    fo.order_status,         
    fo.purchased_at,
    oi.shipping_limit_at,
    oi.item_price_amount,
    oi.freight_cost_amount,
    (oi.item_price_amount + oi.freight_cost_amount) as total_item_cost_amount
from order_items oi
inner join fulfilled_orders fo 
    on oi.order_id = fo.order_id