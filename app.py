import os
import time
from google.cloud import bigquery
from dotenv import load_dotenv
import polars as pl
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

st.set_page_config(page_title="Interactive E-Commerce Analysis", layout="wide")

st.title("📊 Interactive Delivery & Seller Analysis")
st.markdown("Use the sidebar widgets to slice and filter the BigQuery data dynamically.")

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
    return pl.from_arrow(client.query(query).to_arrow())

# 1. EXTRACTION
total_start = time.perf_counter()
df = get_data()

# 2. BASE TRANSFORMATION
df_proc = df.with_columns([
    ((pl.col("delivered_to_customer_at") - pl.col("purchased_at")).dt.total_milliseconds() / (1000 * 60 * 60 * 24)).alias("delivery_time_days"),
    (pl.col("customer_city").str.strip_chars().str.to_lowercase() == pl.col("seller_city").str.strip_chars().str.to_lowercase()).alias("is_same_city")
])

unique_cities_sorted = (
    df_proc.group_by("customer_city")
    .agg(pl.len().alias("total"))
    .sort("total", descending=True)["customer_city"]
    .to_list()
)

# --- INTERACTIVE SIDEBAR CONTROLS ---
st.sidebar.header("🎛️ Interactive Filters")

top_n = st.sidebar.slider("Show Top N Cities by Order Volume", min_value=2, max_value=15, value=5)
default_cities = unique_cities_sorted[:top_n]

selected_cities = st.sidebar.multiselect(
    "Select Target Customer Cities",
    options=unique_cities_sorted,
    default=default_cities
)

# 3. DYNAMIC DATA AGGREGATION
if not selected_cities:
    st.warning("⚠️ Please select at least one city in the sidebar to visualize.")
else:
    proc_start = time.perf_counter()
    
    final_df = (
        df_proc.filter(pl.col("customer_city").is_in(selected_cities))
        .group_by("customer_city")
        .agg([
            pl.col("order_id").n_unique().alias("total_orders"),
            pl.col("order_id").filter(pl.col("is_same_city")).n_unique().fill_null(0).alias("orders_same_city"),
            pl.col("order_id").filter(~pl.col("is_same_city")).n_unique().fill_null(0).alias("orders_outside_city"),
            
            pl.col("delivery_time_days").filter(pl.col("is_same_city")).mean().round(2).fill_null(0).alias("avg_time_same"),
            pl.col("delivery_time_days").filter(~pl.col("is_same_city")).mean().round(2).fill_null(0).alias("avg_time_outside")
        ])
        .sort("total_orders", descending=True)
    )
    
    proc_duration = time.perf_counter() - proc_start
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("Performance Metrics")
    st.sidebar.metric("Polars Aggregation Time", f"{proc_duration:.4f}s")
    st.sidebar.metric("Total App Pipeline Time", f"{time.perf_counter() - total_start:.2f}s")

    # --- RENDER KEY PERFORMANCE METRICS ---
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Analyzed Cities", len(selected_cities))
    with col2:
        st.metric("Total Overall Orders", f"{final_df['total_orders'].sum():,}")
    with col3:
        overall_avg_same = final_df['avg_time_same'].mean()
        st.metric("Avg Intracity Delivery Time", f"{overall_avg_same:.1f} Days")

    # 4. PLOTLY VISUALIZATION
    fig = make_subplots(rows=2, cols=1, subplot_titles=("Order Fulfillment Breakdown vs Total Volume", "Average Delivery Timelines (Days)"))
    
    # Chart 1: Added Total Customer Orders alongside the breakdowns
    fig.add_trace(go.Bar(name='Total Customer Orders', x=final_df['customer_city'], y=final_df['total_orders'], marker_color='#2ca02c'), row=1, col=1)
    fig.add_trace(go.Bar(name='Orders from Local Sellers', x=final_df['customer_city'], y=final_df['orders_same_city'], marker_color='#1f77b4'), row=1, col=1)
    fig.add_trace(go.Bar(name='Orders from Outside Sellers', x=final_df['customer_city'], y=final_df['orders_outside_city'], marker_color='#aec7e8'), row=1, col=1)
    
    # Chart 2: Timelines
    fig.add_trace(go.Bar(name='Avg Days (Local Seller)', x=final_df['customer_city'], y=final_df['avg_time_same'], marker_color='#ff7f0e'), row=2, col=1)
    fig.add_trace(go.Bar(name='Avg Days (Outside Seller)', x=final_df['customer_city'], y=final_df['avg_time_outside'], marker_color='#ffbb78'), row=2, col=1)
    
    fig.update_layout(barmode='group', height=700, margin=dict(t=60, b=40), hovermode="x unified")
    
    st.plotly_chart(fig, use_container_width=True)

    # Underlying Table Explorer
    with st.expander("👁️ Inspect Calculated Metric Data Table (Verify Math Here)"):
        st.dataframe(final_df.to_pandas(), use_container_width=True)