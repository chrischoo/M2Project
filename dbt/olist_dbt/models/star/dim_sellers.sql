with staging_sellers as (
    select * from {{ source(env_var('TARGET_BIGQUERY_DATASET_ID'), 'olist_sellers_dataset') }}
)

select
    cast(seller_id as string) as seller_id,
    cast(seller_zip_code_prefix as int64) as zip_code_prefix,
    cast(seller_city as string) as city_name,
    cast(seller_state as string) as state_code
from staging_sellers