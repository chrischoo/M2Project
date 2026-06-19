with staging_products as (
    select * from {{ source(env_var('TARGET_BIGQUERY_DATASET_ID'), 'olist_products_dataset') }}
)

select
    cast(product_id as string) as product_id,
    cast(product_category_name as string) as product_category,
    
    -- safe_cast handles empty/blank fields gracefully by transforming them to NULL
    safe_cast(product_name_lenght as int64) as name_length,
    safe_cast(product_description_lenght as int64) as description_length,
    safe_cast(product_photos_qty as int64) as photos_quantity,
    safe_cast(product_weight_g as numeric) as weight_grams,
    safe_cast(product_length_cm as numeric) as length_cm,
    safe_cast(product_height_cm as numeric) as height_cm,
    safe_cast(product_width_cm as numeric) as width_cm
from staging_products