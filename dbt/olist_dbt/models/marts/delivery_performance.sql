{{ config(materialized='table') }}

select
    o.order_id,
    o.customer_id,
    o.order_status,
    date(o.order_purchase_timestamp) as purchase_date,
    date(o.order_delivered_customer_date) as delivered_date,
    date(o.order_estimated_delivery_date) as estimated_delivery_date,

    date_diff(date(o.order_delivered_customer_date), date(o.order_purchase_timestamp), day) as delivery_days,
    date_diff(date(o.order_delivered_customer_date), date(o.order_estimated_delivery_date), day) as delay_days,

    case
        when date(o.order_delivered_customer_date) > date(o.order_estimated_delivery_date) then 1
        else 0
    end as late_delivery_flag,

    r.review_score

from {{ source('olist', 'olist_orders_dataset') }} o
left join {{ source('olist', 'olist_order_reviews_dataset') }} r
    on o.order_id = r.order_id
where o.order_status = 'delivered'