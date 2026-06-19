{{ config(
    materialized='table'
) }}

with staging_payments as (
    select * from {{ source(env_var('TARGET_BIGQUERY_DATASET_ID'), 'olist_order_payments_dataset') }}
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
    {{ dbt_utils.generate_surrogate_key(['p.order_id', 'p.payment_sequential']) }} as order_payment_key,
    p.order_id,
    fo.customer_id,
    cast(p.payment_sequential as int64) as payment_split_sequence,
    cast(p.payment_type as string) as payment_method,
    cast(p.payment_installments as int64) as payment_installments_count,
    fo.purchased_at,
    fo.order_status, 
    cast(p.payment_value as numeric) as payment_allocated_amount
from staging_payments p
inner join fulfilled_orders fo 
    on p.order_id = fo.order_id