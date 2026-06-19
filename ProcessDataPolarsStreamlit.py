import os
import time
from google.cloud import bigquery
from dotenv import load_dotenv
import polars as pl
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# Set up Streamlit page layout
st.set_page_config(page_title="E-Commerce Delivery Analysis", layout="wide")
st.title("🚚 City-Level Delivery & Seller Distribution Analysis")

@st.cache_data(show_spinner="Extracting data from BigQuery...")
def get_data():
    load_dotenv(dotenv_path='../../.env')
    client = bigquery.Client(project=os.getenv('GCP_PROJECT_ID'))
    dataset = os.getenv('TARGET_BIGQUERY_DATASET_ID')

    query = f"""
    SELECT 
        c.city_name AS customer_city,
        s.city_name AS seller_city,
        foi.order_id,
        do.purchased_at,
        do.delivered_to_customer_at
    FROM `{dataset}.fct_order_items` foi
    JOIN `{dataset}.dim_orders` do ON foi.order_id = do.order_id
    JOIN `{dataset}.dim_customers` c ON foi.customer_id = c.customer_id
    JOIN `{dataset}.dim_sellers` s ON foi.seller_id = s.seller_id
    WHERE do.order_status = 'delivered' AND do.delivered_to_customer_at IS NOT NULL
    """
    # Stream from BigQuery via Arrow to Polars
    return pl.from_arrow(client.query(query).to_arrow())

# 1. EXTRACTION
total_start = time.perf_counter()
df = get_data()

# 2. TRANSFORMATION
proc_start = time.perf_counter()

df_proc = df.with_columns([
    ((pl.col("delivered_to_customer_at") - pl.col("purchased_at")).dt.total_milliseconds() / (1000 * 60 * 60 * 24)).alias("delivery_time_days"),
    (pl.col("customer_city").str.strip_chars().str.to_lowercase() == pl.col("seller_city").str.strip_chars().str.to_lowercase()).alias("is_same_city")
])

# Find top 3 cities by total orders
top_3 = df_proc.group_by("customer_city").agg(pl.len().alias("total")).sort("total", descending=True).head(3)["customer_city"]

final_df = (
    df_proc.filter(pl.col("customer_city").is_in(top_3))
    .group_by("customer_city")
    .agg([
        pl.col("order_id").n_unique().alias("total_orders"),
        pl.col("seller_city").filter(pl.col("is_same_city")).n_unique().fill_null(0).alias("sellers_same"),
        pl.col("seller_city").filter(~pl.col("is_same_city")).n_unique().fill_null(0).alias("sellers_outside"),
        pl.col("delivery_time_days").filter(pl.col("is_same_city")).mean().round(2).fill_null(0).alias("avg_time_same"),
        pl.col("delivery_time_days").filter(~pl.col("is_same_city")).mean().round(2).fill_null(0).alias("avg_time_outside")
    ])
)

proc_duration = time.perf_counter() - proc_start
total_duration = time.perf_counter() - total_start

# --- STREAMLIT SIDEBAR / METRICS ---
st.sidebar.header("Pipeline Metrics")
st.sidebar.metric(label="Polars Process Time", value=f"{proc_duration:.2f}s")
st.sidebar.metric(label="Total App Load Time", value=f"{total_duration:.2f}s")

# Display the raw underlying table dynamically in the app
with st.expander("🔍 View Processed Data Schema & Table"):
    st.dataframe(final_df.to_pandas(), use_container_width=True)

# 3. VISUALIZATION
fig = make_subplots(rows=2, cols=1, subplot_titles=("Sellers by Location", "Avg Delivery (Days)"))
fig.add_trace(go.Bar(name='Same City Sellers', x=final_df['customer_city'], y=final_df['sellers_same']), row=1, col=1)
fig.add_trace(go.Bar(name='Outside City Sellers', x=final_df['customer_city'], y=final_df['sellers_outside']), row=1, col=1)
fig.add_trace(go.Bar(name='Avg Days (Same)', x=final_df['customer_city'], y=final_df['avg_time_same']), row=2, col=1)
fig.add_trace(go.Bar(name='Avg Days (Outside)', x=final_df['customer_city'], y=final_df['avg_time_outside']), row=2, col=1)

fig.update_layout(barmode='group', height=600, margin=dict(t=50, b=50))

# Render chart directly into the Streamlit dashboard app layout
st.plotly_chart(fig, use_container_width=True)