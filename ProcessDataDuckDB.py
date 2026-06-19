import os
import time
import psutil
from google.cloud import bigquery
from dotenv import load_dotenv
import duckdb
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

st.set_page_config(page_title="DuckDB Interactive E-Commerce Analysis", layout="wide")

st.title("🦆 Interactive DuckDB Delivery & Seller Analysis")
st.markdown("Use the sidebar widgets to slice and filter the BigQuery data via DuckDB.")

# Helper to capture baseline system state
def get_process_metrics():
    process = psutil.Process(os.getpid())
    # memory in MB, CPU as a percentage
    return {
        "memory": process.memory_info().rss / (1024 * 1024),
        "cpu": psutil.cpu_percent(interval=None)
    }

@st.cache_data(show_spinner="Extracting data from BigQuery...")
def get_raw_arrow_table():
    load_dotenv(dotenv_path='../../.env')
    client = bigquery.Client(project=os.getenv('GCP_PROJECT_ID'))
    dataset = os.getenv('TARGET_BIGQUERY_DATASET_ID')

    query = f"""
    SELECT 
        c.city_name AS customer_city,
        s.city_name AS seller_city,
        fo.order_id,
        do.purchased_at,
        do.delivered_to_customer_at
    FROM `{dataset}.fct_order_items` fo
    JOIN `{dataset}.dim_orders` do ON fo.order_id = do.order_id
    JOIN `{dataset}.dim_customers` c ON fo.customer_id = c.customer_id
    JOIN `{dataset}.dim_sellers` s ON fo.seller_id = s.seller_id
    WHERE do.order_status = 'delivered' AND do.delivered_to_customer_at IS NOT NULL
    """
    return client.query(query).to_arrow()

# 1. EXTRACTION START TIMING
total_start = time.perf_counter()
arrow_table = get_raw_arrow_table()

# Create a local in-memory DuckDB connection and register the Arrow table
con = duckdb.connect()
con.register("raw_orders", arrow_table)

# Get sorted unique cities for sidebar selection using DuckDB
unique_cities_df = con.execute("""
    SELECT customer_city, COUNT(DISTINCT order_id) as total 
    FROM raw_orders 
    GROUP BY customer_city 
    ORDER BY total DESC
""").df()
unique_cities_sorted = unique_cities_df["customer_city"].tolist()

# --- INTERACTIVE SIDEBAR CONTROLS ---
st.sidebar.header("🎛️ Interactive Filters")

top_n = st.sidebar.slider("Show Top N Cities by Order Volume", min_value=2, max_value=15, value=5)
default_cities = unique_cities_sorted[:top_n]

selected_cities = st.sidebar.multiselect(
    "Select Target Customer Cities",
    options=unique_cities_sorted,
    default=default_cities
)

# 3. DYNAMIC DATA AGGREGATION VIA DUCKDB
if not selected_cities:
    st.warning("⚠️ Please select at least one city in the sidebar to visualize.")
else:
    # Capture resource baseline right before computation
    baseline_metrics = get_process_metrics()
    proc_start = time.perf_counter()
    
    duck_query = """
        WITH calculated_base AS (
            SELECT 
                customer_city,
                order_id,
                (epoch(delivered_to_customer_at) - epoch(purchased_at)) / (60 * 60 * 24) AS delivery_time_days,
                (trim(lower(customer_city)) = trim(lower(seller_city))) AS is_same_city
            FROM raw_orders
            WHERE customer_city IN ?
        )
        SELECT 
            customer_city,
            COUNT(DISTINCT order_id) AS total_orders,
            COUNT(DISTINCT CASE WHEN is_same_city THEN order_id END) AS orders_same_city,
            COUNT(DISTINCT CASE WHEN NOT is_same_city THEN order_id END) AS orders_outside_city,
            ROUND(COALESCE(AVG(CASE WHEN is_same_city THEN delivery_time_days END), 0), 2) AS avg_time_same,
            ROUND(COALESCE(AVG(CASE WHEN NOT is_same_city THEN delivery_time_days END), 0), 2) AS avg_time_outside
        FROM calculated_base
        GROUP BY customer_city
        ORDER BY total_orders DESC
    """
    
    # Execute query
    final_df = con.execute(duck_query, (selected_cities,)).df()
    
    # Capture resource usage right after computation
    proc_duration = time.perf_counter() - proc_start
    post_metrics = get_process_metrics()
    
    # Calculate differentials
    memory_used_mb = max(0.0, post_metrics["memory"] - baseline_metrics["memory"])
    cpu_utilization = psutil.cpu_percent(interval=None) # Capture core utilization during execution

    # Get HDD footprint (DuckDB in-memory database uses 0 bytes on disk, but we check temporary storage allocation)
    # If using a persistent file, os.path.getsize('file.duckdb') would be utilized here
    db_size_bytes = con.execute("PRAGMA database_size;").fetchone()
    # Extract 'wal_size' or 'memory_usage' fields safely from DuckDB metadata properties
    allocated_hdd_mb = (db_size_bytes[2] if db_size_bytes else 0) / (1024 * 1024)

    # --- PERFORMANCE SIDEBAR METRICS ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("⚙️ Resource Utilization")
    
    st.sidebar.metric("DuckDB Compute Time", f"{proc_duration:.4f}s")
    st.sidebar.metric("RAM Allocated (Delta)", f"{memory_used_mb:.2f} MB")
    st.sidebar.metric("CPU Core Load", f"{cpu_utilization:.1f}%")
    st.sidebar.metric("DuckDB Virtual HDD/Cache Size", f"{allocated_hdd_mb:.2f} MB")

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
    
    fig.add_trace(go.Bar(name='Total Customer Orders', x=final_df['customer_city'], y=final_df['total_orders'], marker_color='#2ca02c'), row=1, col=1)
    fig.add_trace(go.Bar(name='Orders from Local Sellers', x=final_df['customer_city'], y=final_df['orders_same_city'], marker_color='#1f77b4'), row=1, col=1)
    fig.add_trace(go.Bar(name='Orders from Outside Sellers', x=final_df['customer_city'], y=final_df['orders_outside_city'], marker_color='#aec7e8'), row=1, col=1)
    
    fig.add_trace(go.Bar(name='Avg Days (Local Seller)', x=final_df['customer_city'], y=final_df['avg_time_same'], marker_color='#ff7f0e'), row=2, col=1)
    fig.add_trace(go.Bar(name='Avg Days (Outside Seller)', x=final_df['customer_city'], y=final_df['avg_time_outside'], marker_color='#ffbb78'), row=2, col=1)
    
    fig.update_layout(barmode='group', height=700, margin=dict(t=60, b=40), hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    total_pipeline_duration = time.perf_counter() - total_start
    st.sidebar.metric("Total Pipeline Loop", f"{total_pipeline_duration:.2f}s")

    with st.expander("👁️ Inspect DuckDB Calculated Metric Data Table"):
        st.dataframe(final_df, use_container_width=True)