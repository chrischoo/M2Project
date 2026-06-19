import os
import time
from google.cloud import bigquery
from dotenv import load_dotenv
import polars as pl
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

st.set_page_config(page_title="Polars Performance Dashboard", layout="wide")

st.title("⚡ Interactive Polars Delivery & Freight Analysis")
st.markdown("Use the sidebar widgets to slice and filter the BigQuery data via Polars.")

@st.cache_data(show_spinner="Extracting data from BigQuery...")
def get_data():
    load_dotenv(dotenv_path='../../.env')
    client = bigquery.Client(project=os.getenv('GCP_PROJECT_ID'))
    dataset = os.getenv('TARGET_BIGQUERY_DATASET_ID')

    # Pulling correct schema field 'freight_cost_amount' from fact table
    query = f"""
    SELECT 
        c.city_name AS customer_city,
        s.city_name AS seller_city,
        foi.order_id,
        foi.freight_cost_amount AS freight_value,
        do.purchased_at,
        do.delivered_to_customer_at
    FROM `{dataset}.fct_order_items` foi
    JOIN `{dataset}.dim_orders` do ON foi.order_id = do.order_id
    JOIN `{dataset}.dim_customers` c ON foi.customer_id = c.customer_id
    JOIN `{dataset}.dim_sellers` s ON foi.seller_id = s.seller_id
    WHERE do.order_status = 'delivered' AND do.delivered_to_customer_at IS NOT NULL
    """
    return pl.from_arrow(client.query(query).to_arrow())

# 1. EXTRACTION START TIMING
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

# 3. DYNAMIC DATA AGGREGATION VIA POLARS
if not selected_cities:
    st.warning("⚠️ Please select at least one city in the sidebar to visualize.")
else:
    # START TRACKING POLARS COMPUTATION TIME
    proc_start = time.perf_counter()
    
    final_df = (
        df_proc.filter(pl.col("customer_city").is_in(selected_cities))
        .group_by("customer_city")
        .agg([
            pl.col("order_id").n_unique().alias("total_orders"),
            pl.col("order_id").filter(pl.col("is_same_city")).n_unique().fill_null(0).alias("orders_same_city"),
            pl.col("order_id").filter(~pl.col("is_same_city")).n_unique().fill_null(0).alias("orders_outside_city"),
            
            # Timelines
            pl.col("delivery_time_days").filter(pl.col("is_same_city")).mean().round(2).fill_null(0).alias("avg_time_same"),
            pl.col("delivery_time_days").filter(~pl.col("is_same_city")).mean().round(2).fill_null(0).alias("avg_time_outside"),
            
            # Shipment Freight Costs
            pl.col("freight_value").filter(pl.col("is_same_city")).mean().round(2).fill_null(0).alias("avg_freight_same"),
            pl.col("freight_value").filter(~pl.col("is_same_city")).mean().round(2).fill_null(0).alias("avg_freight_outside")
        ])
        .sort("total_orders", descending=True)
    )
    
    # STOP TRACKING POLARS COMPUTATION TIME
    proc_duration = time.perf_counter() - proc_start

    # --- MAIN PAGE DUAL HEADER COLUMNS ---
    st.markdown("---")
    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    
    with m_col1:
        st.metric("Total Active Orders", f"{final_df['total_orders'].sum():,}")
    with m_col2:
        st.metric("Cities Filtered", len(selected_cities))
    with m_col3:
        st.metric("⏱️ Polars Engine Processing", f"{proc_duration:.4f} sec", help="In-memory aggregation execution speed.")
    with m_col4:
        # Dynamic layout placeholder updated after frontend canvas generation complete
        total_duration_placeholder = st.empty()
    st.markdown("---")

    # 4. PLOTLY MULTI-ROW VISUALIZATION
    fig = make_subplots(
        rows=3, cols=1, 
        subplot_titles=(
            "Order Fulfillment Breakdown vs Total Volume", 
            "Average Delivery Timelines (Days)", 
            "Average Shipment Freight Cost Comparison"
        )
    )
    
    # Chart 1: Order Volume Splits
    fig.add_trace(go.Bar(name='Total Customer Orders', x=final_df['customer_city'], y=final_df['total_orders'], marker_color='#2ca02c'), row=1, col=1)
    fig.add_trace(go.Bar(name='Orders from Local Sellers', x=final_df['customer_city'], y=final_df['orders_same_city'], marker_color='#1f77b4'), row=1, col=1)
    fig.add_trace(go.Bar(name='Orders from Outside Sellers', x=final_df['customer_city'], y=final_df['orders_outside_city'], marker_color='#aec7e8'), row=1, col=1)
    
    # Chart 2: Delivery Timelines
    fig.add_trace(go.Bar(name='Avg Days (Local Seller)', x=final_df['customer_city'], y=final_df['avg_time_same'], marker_color='#ff7f0e'), row=2, col=1)
    fig.add_trace(go.Bar(name='Avg Days (Outside Seller)', x=final_df['customer_city'], y=final_df['avg_time_outside'], marker_color='#ffbb78'), row=2, col=1)
    
    # Chart 3: Freight Costs Analysis
    fig.add_trace(go.Bar(name='Avg Freight (Local Seller)', x=final_df['customer_city'], y=final_df['avg_freight_same'], marker_color='#9467bd'), row=3, col=1)
    fig.add_trace(go.Bar(name='Avg Freight (Outside Seller)', x=final_df['customer_city'], y=final_df['avg_freight_outside'], marker_color='#c5b0d5'), row=3, col=1)

    fig.update_layout(barmode='group', height=950, margin=dict(t=60, b=40), hovermode="x unified")
    
    st.plotly_chart(fig, use_container_width=True)

    # 5. CONTAINER PAINT FINISHED TIMING
    total_duration = time.perf_counter() - total_start
    total_duration_placeholder.metric(
        "🚀 Total App Loop Duration", 
        f"{total_duration:.2f} sec", 
        help="Includes full end-to-end framework execution, query runtime, and Plotly chart assembly."
    )

    # Table Explorer
    with st.expander("👁️ Inspect Polars Calculated Metric Data Table"):
        st.dataframe(final_df.to_pandas(), use_container_width=True)