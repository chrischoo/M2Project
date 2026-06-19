import os
import time
from google.cloud import bigquery
from dotenv import load_dotenv
import polars as pl
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

st.set_page_config(page_title="Customer Retention Dashboard", layout="wide")

st.title("👥 Customer Retention Analysis by City")
st.markdown("Evaluating the distribution of recurring (repeat buyers) vs. non-recurring (one-time buyers) customers across different locations.")

@st.cache_data(show_spinner="Extracting customer data from BigQuery...")
def get_data():
    load_dotenv(dotenv_path='../../.env')
    client = bigquery.Client(project=os.getenv('GCP_PROJECT_ID'))
    dataset = os.getenv('TARGET_BIGQUERY_DATASET_ID')

    # Query pulls customer geographic data along with order identifiers
    query = f"""
    SELECT 
        c.city_name AS customer_city,
        c.customer_unique_id,
        foi.order_id
    FROM `{dataset}.fct_order_items` foi
    JOIN `{dataset}.dim_orders` do ON foi.order_id = do.order_id
    JOIN `{dataset}.dim_customers` c ON foi.customer_id = c.customer_id
    WHERE do.order_status = 'delivered'
    """
    return pl.from_arrow(client.query(query).to_arrow())

# 1. EXTRACTION START TIMING
total_start = time.perf_counter()
df = get_data()

# 2. DYNAMIC RETENTION AGGREGATION VIA POLARS
proc_start = time.perf_counter()

# Step 1: Calculate total orders placed per unique customer within their city
customer_orders = df.group_by(["customer_city", "customer_unique_id"]).agg(
    pl.col("order_id").n_unique().alias("order_count")
)

# Step 2: Categorize customers and aggregate at the city level
city_retention = (
    customer_orders.group_by("customer_city")
    .agg([
        # Total unique people in that city
        pl.col("customer_unique_id").n_unique().alias("total_unique_customers"),
        
        # Non-Recurring: Unique IDs with exactly 1 order
        pl.col("customer_unique_id")
          .filter(pl.col("order_count") == 1)
          .n_unique()
          .fill_null(0)
          .alias("non_recurring_customers"),
          
        # Recurring: Unique IDs with more than 1 order
        pl.col("customer_unique_id")
          .filter(pl.col("order_count") > 1)
          .n_unique()
          .fill_null(0)
          .alias("recurring_customers")
    ])
    .with_columns([
        (pl.col("recurring_customers") / pl.col("total_unique_customers") * 100).round(2).alias("recurring_pct"),
        (pl.col("non_recurring_customers") / pl.col("total_unique_customers") * 100).round(2).alias("non_recurring_pct")
    ])
    .sort("total_unique_customers", descending=True)
)

proc_duration = time.perf_counter() - proc_start

# --- INTERACTIVE SIDEBAR OPTIONS ---
st.sidebar.header("🎛️ Visual Configuration")

unique_cities_sorted = city_retention["customer_city"].to_list()
top_n_cities = st.sidebar.slider("Show Top N Cities by Customer Volume", min_value=2, max_value=20, value=5)
selected_cities = unique_cities_sorted[:top_n_cities]

# Filter down display frame based on user selection scope
final_df = city_retention.filter(pl.col("customer_city").is_in(selected_cities))

# --- MAIN PAGE KPI METRICS ---
st.markdown("---")
m_col1, m_col2, m_col3, m_col4 = st.columns(4)

with m_col1:
    st.metric("Total Unique Customers Evaluated", f"{city_retention['total_unique_customers'].sum():,}")
with m_col2:
    st.metric("Global Recurring Customers", f"{city_retention['recurring_customers'].sum():,}")
with m_col3:
    st.metric("⏱️ Polars Execution", f"{proc_duration:.4f} sec")
with m_col4:
    total_duration_placeholder = st.empty()
st.markdown("---")

# 3. PLOTLY COHORT VISUALIZATION
fig = make_subplots(
    rows=2, cols=1, 
    subplot_titles=(
        "Customer Category Volume Breakdown (Absolute Count)", 
        "Customer Base Percentage Distribution (%)"
    )
)

# Row 1: Absolute Volumes
fig.add_trace(go.Bar(name='One-Time (Non-Recurring)', x=final_df['customer_city'], y=final_df['non_recurring_customers'], marker_color='#636EFA'), row=1, col=1)
fig.add_trace(go.Bar(name='Repeat (Recurring)', x=final_df['customer_city'], y=final_df['recurring_customers'], marker_color='#EF553B'), row=1, col=1)

# Row 2: Relative Share Percentages
fig.add_trace(go.Bar(name='One-Time Pct (%)', x=final_df['customer_city'], y=final_df['non_recurring_pct'], marker_color='#abc9ea', showlegend=False), row=2, col=1)
fig.add_trace(go.Bar(name='Repeat Pct (%)', x=final_df['customer_city'], y=final_df['recurring_pct'], marker_color='#ff9e9e', showlegend=False), row=2, col=1)

fig.update_layout(barmode='stack', height=800, margin=dict(t=60, b=40), hovermode="x unified")
st.plotly_chart(fig, use_container_width=True)

# 4. HALT PIPELINE CLOCK
total_duration = time.perf_counter() - total_start
total_duration_placeholder.metric("🚀 App Loop Duration", f"{total_duration:.2f} sec")

# Data Inspection Panel
with st.expander("👁️ Inspect Retention Metric Data Table"):
    st.dataframe(final_df.to_pandas(), use_container_width=True)