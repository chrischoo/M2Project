import os
import time
from google.cloud import bigquery
from dotenv import load_dotenv
import polars as pl
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

st.set_page_config(page_title="Polars Variable Limits Dashboard", layout="wide")

st.title("⚡ Dynamic Top Products & Cities Logistics Analysis")
st.markdown("Adjust the sidebar sliders to control exactly how many top products and top cities are evaluated simultaneously.")

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
        foi.freight_cost_amount AS freight_value,
        p.product_category AS product_type,
        do.purchased_at,
        do.delivered_to_customer_at
    FROM `{dataset}.fct_order_items` foi
    JOIN `{dataset}.dim_orders` do ON foi.order_id = do.order_id
    JOIN `{dataset}.dim_customers` c ON foi.customer_id = c.customer_id
    JOIN `{dataset}.dim_sellers` s ON foi.seller_id = s.seller_id
    JOIN `{dataset}.dim_products` p ON foi.product_id = p.product_id
    WHERE do.order_status = 'delivered' AND do.delivered_to_customer_at IS NOT NULL
    """
    return pl.from_arrow(client.query(query).to_arrow())

# 1. EXTRACTION START TIMING
total_start = time.perf_counter()
df = get_data()

# 2. BASE TRANSFORMATION & RANKING EXTRACTION
df_proc = df.with_columns([
    ((pl.col("delivered_to_customer_at") - pl.col("purchased_at")).dt.total_milliseconds() / (1000 * 60 * 60 * 24)).alias("delivery_time_days"),
    (pl.col("customer_city").str.strip_chars().str.to_lowercase() == pl.col("seller_city").str.strip_chars().str.to_lowercase()).alias("is_same_city")
])

# Pre-calculate global volume rankings via Polars for the UI bounds
global_top_products = (
    df_proc.filter(pl.col("product_type").is_not_null())
    .group_by("product_type")
    .agg(pl.len().alias("count"))
    .sort("count", descending=True)["product_type"]
    .to_list()
)

global_top_cities = (
    df_proc.group_by("customer_city")
    .agg(pl.len().alias("total"))
    .sort("total", descending=True)["customer_city"]
    .to_list()
)

# --- INTERACTIVE SIDEBAR CONTROLS ---
st.sidebar.header("🎛️ Scope Configuration")

# Dynamic Toggle Option to Include All Products
include_all_products = st.sidebar.checkbox(
    "Include All Product Categories", 
    value=False,
    help="Check this box to bypass the slider and analyze every product category at once."
)

if include_all_products:
    selected_products = global_top_products
    st.sidebar.caption("📦 Analyzing all available product types.")
else:
    # Slider to adjust product scope if the toggle is turned off
    top_p_count = st.sidebar.slider(
        "Number of Top Products to Analyze", 
        min_value=1, 
        max_value=min(20, len(global_top_products)), 
        value=1,
        help="Select 1 to isolate the top product, or increase it to include more."
    )
    selected_products = global_top_products[:top_p_count]

# Slider to adjust city scope (Always sets to more than 1)
top_c_count = st.sidebar.slider(
    "Number of Top Cities to Analyze", 
    min_value=2, 
    max_value=min(15, len(global_top_cities)), 
    value=3,
    help="Determine how many of the highest-volume cities are displayed."
)
selected_cities = global_top_cities[:top_c_count]

# Display targeted criteria parameters directly in the sidebar panel
st.sidebar.markdown("---")
if not include_all_products:
    st.sidebar.markdown(f"**Targeted Products ({len(selected_products)}):**\n`{', '.join(selected_products)}`")
else:
    st.sidebar.markdown(f"**Targeted Products:** `All Available Categories`")
st.sidebar.markdown(f"**Targeted Cities ({len(selected_cities)}):**\n`{', '.join(selected_cities)}`")

# 3. DYNAMIC DATA AGGREGATION VIA POLARS
# Filter the dataset using the dynamically computed sublists
df_filtered = df_proc.filter(
    (pl.col("product_type").is_in(selected_products)) & 
    (pl.col("customer_city").is_in(selected_cities))
)

if len(df_filtered) == 0:
    st.warning("⚠️ No active transaction records matched the current criteria slices.")
else:
    proc_start = time.perf_counter()
    
    # Run structural groupings on the filtered boundaries
    final_df = (
        df_filtered.group_by(["customer_city", "product_type"])
        .agg([
            pl.col("order_id").n_unique().alias("total_orders"),
            
            # Shipping costs calculations
            pl.col("freight_value").filter(pl.col("is_same_city")).mean().round(2).fill_null(0).alias("avg_freight_same"),
            pl.col("freight_value").filter(~pl.col("is_same_city")).mean().round(2).fill_null(0).alias("avg_freight_outside"),
            
            # Timelines calculations
            pl.col("delivery_time_days").filter(pl.col("is_same_city")).mean().round(2).fill_null(0).alias("avg_time_same"),
            pl.col("delivery_time_days").filter(~pl.col("is_same_city")).mean().round(2).fill_null(0).alias("avg_time_outside")
        ])
        .sort(["customer_city", "total_orders"], descending=[False, True])
    )
    
    proc_duration = time.perf_counter() - proc_start

    # --- MAIN PAGE KPI METRICS ---
    st.markdown("---")
    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    
    with m_col1:
        st.metric("Total Filtered Orders", f"{final_df['total_orders'].sum():,}")
    with m_col2:
        st.metric("Active Chart Slices", len(final_df))
    with m_col3:
        st.metric("⏱️ Polars Engine Processing", f"{proc_duration:.4f} sec", help="In-memory data calculation execution runtime.")
    with m_col4:
        total_duration_placeholder = st.empty()
    st.markdown("---")

    # Generate multi-level labels for the horizontal axis chart platform
    x_labels = [f"{row['customer_city']}<br>({row['product_type']})" for row in final_df.iter_rows(named=True)]

    # 4. PLOTLY MULTI-ROW VISUALIZATION
    fig = make_subplots(
        rows=2, cols=1, 
        subplot_titles=(
            "Average Shipment Freight Cost Comparison ($) per Selection",
            "Average Delivery Timelines (Days) per Selection"
        )
    )
    
    # Row 1: Freight Metrics
    fig.add_trace(go.Bar(name='Avg Freight (Local Seller)', x=x_labels, y=final_df['avg_freight_same'], marker_color='#9467bd'), row=1, col=1)
    fig.add_trace(go.Bar(name='Avg Freight (Outside Seller)', x=x_labels, y=final_df['avg_freight_outside'], marker_color='#c5b0d5'), row=1, col=1)
    
    # Row 2: Delivery Timelines Context
    fig.add_trace(go.Bar(name='Avg Days (Local Seller)', x=x_labels, y=final_df['avg_time_same'], marker_color='#ff7f0e'), row=2, col=1)
    fig.add_trace(go.Bar(name='Avg Days (Outside Seller)', x=x_labels, y=final_df['avg_time_outside'], marker_color='#ffbb78'), row=2, col=1)

    fig.update_layout(barmode='group', height=850, margin=dict(t=60, b=60), hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    # 5. HALT PIPELINE CLOCK & UPDATE METRICS
    total_duration = time.perf_counter() - total_start
    total_duration_placeholder.metric(
        "🚀 Total App Loop Duration", 
        f"{total_duration:.2f} sec", 
        help="Includes full cache parsing, network handshake, dataframe math, and full Plotly engine execution."
    )

    # Underlying Table Inspection
    with st.expander("👁️ Inspect Polars Calculated Metric Data Table"):
        st.dataframe(final_df.to_pandas(), use_container_width=True)