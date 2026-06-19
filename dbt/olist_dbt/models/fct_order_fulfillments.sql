with orders as (
    -- References stg_orders.sql in the same root folder
    select * from {{ ref('stg_orders') }}
),

order_items as (
    -- References stg_order_items.sql in the same root folder
    select * from {{ ref('stg_order_items') }}
),

customers as (
    -- References dim_customers.sql inside the models/star/ folder
    select * from {{ ref('dim_customers') }}
),

sellers as (
    -- References dim_sellers.sql inside the models/star/ folder
    select * from {{ ref('dim_sellers') }}
)

select
    -- Primary and Foreign Keys
    order_items.order_id,
    order_items.order_item_sequence,
    orders.customer_id,
    order_items.seller_id,
    order_items.product_id,

    -- 1. Customer Context (Answering: customers from which unique cities)
    customers.customer_unique_id,
    customers.city_name as customer_city,
    customers.state_code as customer_state,

    -- 2. Seller Context (Answering: supplying sellers from which cities)
    sellers.city_name as seller_city,
    sellers.state_code as seller_state,

    -- Quantitative Operational Metrics
    orders.order_status,
    orders.purchased_at,
    order_items.item_price_amount,
    order_items.freight_cost_amount,
    
    -- Geographic validation flag
    case 
        when customers.city_name = sellers.city_name then true 
        else false 
    end as is_local_fulfillment

from order_items
inner join orders 
    on order_items.order_id = orders.order_id
inner join customers 
    on orders.customer_id = customers.customer_id
inner join sellers 
    on order_items.seller_id = sellers.seller_id