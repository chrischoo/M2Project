import os
from google.cloud import bigquery
from dotenv import load_dotenv
import polars as pl

def compute_order_fulfillment_split():
    # Load environment variables
    load_dotenv(dotenv_path='../../.env')
    client = bigquery.Client(project=os.getenv('GCP_PROJECT_ID'))
    dataset = os.getenv('TARGET_BIGQUERY_DATASET_ID')

    # Query to pull raw order statuses and customer delivery timestamps
    query = f"""
    SELECT 
        order_id, 
        order_status, 
        order_delivered_customer_date 
    FROM `{dataset}.olist_orders_dataset`
    """
    # Read Arrow data directly into a Polars DataFrame
    df = pl.from_arrow(client.query(query).to_arrow())

    # Calculate total database rows safely using cross-version len()
    total_orders = len(df)

    # Filter for fulfilled orders based on your business logic rules
    df_fulfilled = df.filter(
        (pl.col("order_status") == "delivered") & 
        (pl.col("order_delivered_customer_date").is_not_null())
    )
    fulfilled_count = len(df_fulfilled)

    # Unfulfilled orders are simply the remaining remainder
    unfulfilled_count = total_orders - fulfilled_count
    
    # Calculate relative percentage distribution
    fulfilled_pct = (fulfilled_count / total_orders) * 100 if total_orders > 0 else 0.0
    unfulfilled_pct = 100.0 - fulfilled_pct

    # Print a structured metric summary directly to the terminal console
    print("=" * 55)
    print(f"📦 Total Database Orders:                {total_orders:,}")
    print("-" * 55)
    print(f"✅ Fulfilled (Processed for Insights):   {fulfilled_count:,} ({fulfilled_pct:.2f}%)")
    print(f"⚠️ Unfulfilled (Dropped from Insights):  {unfulfilled_count:,} ({unfulfilled_pct:.2f}%)")
    print("=" * 55)

if __name__ == "__main__":
    compute_order_fulfillment_split()