import os
import time
from google.cloud import bigquery
from dotenv import load_dotenv
import polars as pl
import plotly.graph_objects as go
import streamlit as st

# --- STREAMLIT PAGE CONFIGURATION ---
st.set_page_config(page_title="Seller Sign-up Funnel Analysis", layout="wide")
st.title("🤝 Seller Sign-up & Marketing Funnel Conversion")
st.markdown("Analyzing how effectively Marketing Qualified Leads (MQL) convert into signed-up Olist sellers directly from BigQuery.")

@st.cache_data(show_spinner="Extracting marketing funnel data from BigQuery...")
def calculate_signup_metrics():
    # Load background environment variables
    load_dotenv(dotenv_path='../../.env')
    client = bigquery.Client(project=os.getenv('GCP_PROJECT_ID'))
    dataset = os.getenv('TARGET_BIGQUERY_DATASET_ID')

    # Query to pull and left-join both funnel tables directly in BigQuery
    query = f"""
    SELECT 
        mql.origin,
        mql.mql_id,
        cd.seller_id
    FROM `{dataset}.olist_marketing_qualified_leads_dataset` mql
    LEFT JOIN `{dataset}.olist_closed_deals_dataset` cd ON mql.mql_id = cd.mql_id
    """
    funnel_df = pl.from_arrow(client.query(query).to_arrow())
    
    # FIX 1: Use unique ID counts to eliminate downstream many-to-many join duplication
    total_mql = funnel_df["mql_id"].n_unique()
    total_closed = funnel_df.filter(pl.col("seller_id").is_not_null())["seller_id"].n_unique()
    
    # Calculate global conversion rate based on unique business entities
    global_signup_rate = (total_closed / total_mql) * 100 if total_mql > 0 else 0.0
    
    # FIX 2: Calculate channel breakdown accurately using unique aggregations
    channel_conversion = (
        funnel_df.group_by("origin")
        .agg([
            # Count unique MQL IDs and non-null sellers instead of checking raw row heights
            pl.col("mql_id").n_unique().alias("total_leads"),
            pl.col("seller_id").drop_nulls().n_unique().alias("successful_signups")
        ])
        .filter(pl.col("origin").is_not_null())
        .with_columns(
            ((pl.col("successful_signups") / pl.col("total_leads")) * 100).round(2).alias("conversion_rate")
        )
        .sort("total_leads", descending=True)
    )
    
    return total_mql, total_closed, global_signup_rate, channel_conversion

# --- RUN TIMED PIPELINE ---
total_start = time.perf_counter()
total_mql, total_closed, global_rate, channel_df = calculate_signup_metrics()
pipeline_duration = time.perf_counter() - total_start

# --- MAIN KPI METRIC DISPLAY ---
st.markdown("---")
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Approached Leads (MQL)", f"{total_mql:,}")
with col2:
    st.metric("Total Signed-up Sellers", f"{total_closed:,}")
with col3:
    st.metric("📈 Global Seller Sign-up Rate", f"{global_rate:.2f}%")
with col4:
    st.metric("⏱️ Execution Time", f"{pipeline_duration:.2f} sec")
st.markdown("---")

# --- DATA VISUALIZATION CHART ---
st.subheader("Channels Driving the Highest Seller Conversions")

fig = go.Figure()

# Left Y-Axis: Bars representing the raw lead volumes
fig.add_trace(go.Bar(
    x=channel_df["origin"],
    y=channel_df["total_leads"],
    name="Total Leads Generated",
    marker_color="#1f77b4"
))

# Right Y-Axis: Line representing the actual conversion rate percentages
fig.add_trace(go.Scatter(
    x=channel_df["origin"],
    y=channel_df["conversion_rate"],
    name="Sign-up Rate (%)",
    yaxis="y2",
    mode="lines+markers",
    marker=dict(size=8),
    line=dict(color="#ff7f0e", width=3)
))

# Composite dual-axis configuration
fig.update_layout(
    height=600,
    hovermode="x unified",
    legend=dict(x=0.8, y=0.95),
    xaxis=dict(title="Marketing Channel Origin"),
    yaxis=dict(title="Volume of Leads"),
    yaxis2=dict(
        title="Sign-up Conversion Rate (%)",
        overlaying="y",
        side="right",
        showgrid=False
    )
)

st.plotly_chart(fig, use_container_width=True)

# --- UNDERLYING DATA INSPECTION ---
with st.expander("👁️ View Source Channel Performance Matrix"):
    st.dataframe(channel_df.to_pandas(), use_container_width=True)