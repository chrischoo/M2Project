{{ config(materialized='table') }}

select
    s.seller_id,
    s.seller_city,
    s.seller_state,
    count(distinct oi.order_id) as total_orders,
    sum(oi.price) as total_product_revenue,
    sum(oi.freight_value) as total_freight_value,
    avg(r.review_score) as average_review_score
from {{ source('olist', 'olist_sellers_dataset') }} s
left join {{ source('olist', 'olist_order_items_dataset') }} oi
    on s.seller_id = oi.seller_id
left join {{ source('olist', 'olist_order_reviews_dataset') }} r
    on oi.order_id = r.order_id
group by
    s.seller_id,
    s.seller_city,
    s.seller_state