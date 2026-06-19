with staging_customers as (
    select * from {{ source(env_var('TARGET_BIGQUERY_DATASET_ID'), 'olist_customers_dataset') }}
)

select
    cast(customer_id as string) as customer_id,
    cast(customer_unique_id as string) as customer_unique_id,
    cast(customer_zip_code_prefix as int64) as zip_code_prefix,
    cast(customer_city as string) as city_name,
    cast(customer_state as string) as state_code
from staging_customers