import os
import time
import psutil
import plotly.express as px
import streamlit as st
from google.cloud import bigquery
from dotenv import load_dotenv

# Initialize Streamlit configuration layout
st.set_page_config(page_title="BigQuery Seller Segment Analysis", layout="wide")

st.title("🏭 BigQuery Engine: Seller Performance & Segmentation")
st.markdown("Analyzing seller sales distributions and tier groups within the top 3 high-volume cities.")

# Helper function to monitor local system resources
def get_process_metrics():
    process = psutil.Process(os.getpid())
    return {
        "memory": process.memory_info().rss / (1024 * 1024),
        "cpu": psutil.cpu_percent(interval=None)
    }

@st.cache_data(show_spinner="Running analytical aggregations inside BigQuery...")
def get_bigquery_seller_data():
    # Load environment configuration variables safely
    load_dotenv(dotenv_path='../../.env')
    client = bigquery.Client(project=os.getenv('GCP_PROJECT_ID'))
    dataset = os.getenv('TARGET_BIGQUERY_DATASET_ID')

    # Query identifying top seller cities, computing seller totals, and classifying them
    query = f"""
    WITH top_seller_cities AS (
        SELECT s.city_name
        FROM `{dataset}.fct_order_items` foi
        JOIN `{dataset}.dim_sellers` s ON foi.seller_id = s.seller_id
        GROUP BY s.city_name
        ORDER BY COUNT(DISTINCT foi.order_id) DESC
        LIMIT 3
    ),
    seller_lifetime_sales AS (
        SELECT 
            s.seller_id,
            s.city_name AS seller_city,
            SUM(foi.item_price_amount) AS total_seller_sales
        FROM `{dataset}.fct_order_items` foi
        JOIN `{dataset}.dim_orders` do ON foi.order_id = do.order_id
        JOIN `{dataset}.dim_sellers` s ON foi.seller_id = s.seller_id
        WHERE do.order_status = 'delivered'
          AND s.city_name IN (SELECT city_name FROM top_seller_cities)
        GROUP BY s.seller_id, s.city_name
    ),
    classified_sellers AS (
        SELECT 
            seller_city,
            total_seller_sales,
            CASE 
                WHEN total_seller_sales >= 3000 THEN 'Gold Seller'
                WHEN total_seller_sales >= 1000 AND total_seller_sales < 3000 THEN 'Silver Seller'
                ELSE 'Bronze Seller'
            END AS seller_tier
        FROM seller_lifetime_sales
    )
    SELECT 
        seller_city,
        seller_tier,
        ROUND(SUM(total_seller_sales), 2) AS tier_total_sales,
        COUNT(1) AS seller_count
    FROM classified_sellers
    GROUP BY seller_city, seller_tier
    ORDER BY seller_city, tier_total_sales DESC
    """
    # Pull the optimized summary table straight into local memory
    return client.query(query).to_dataframe()

# 1. START BACKEND TIMER
total_start = time.perf_counter()

# 2. CAPTURE RESOURCE PROFILING BASELINES
baseline_metrics = get_process_metrics()
proc_start = time.perf_counter()

# Run the cloud query process
summary_df = get_bigquery_seller_data()

# Calculate performance metrics
proc_duration = time.perf_counter() - proc_start
post_metrics = get_process_metrics()

memory_used_mb = max(0.0, post_metrics["memory"] - baseline_metrics["memory"])
cpu_utilization = psutil.cpu_percent(interval=None)

# Aggregate global tier statistics for the Pie Chart visualization component
pie_summary_df = summary_df.groupby("seller_tier")[["tier_total_sales", "seller_count"]].sum().reset_index()

# --- SIDEBAR PERFORMANCE METRICS ---
st.sidebar.header("⚙️ BigQuery Profile Metrics")
unique_cities = summary_df["seller_city"].unique().tolist()
st.sidebar.markdown(f"**Top 3 Seller Cities:**\n" + "\n".join([f"- {city}" for city in unique_cities]))
st.sidebar.metric("Cloud Compute Time", f"{proc_duration:.4f}s")
st.sidebar.metric("Local RAM Delta", f"{memory_used_mb:.2f} MB")
st.sidebar.metric("Local CPU Core Load", f"{cpu_utilization:.1f}%")

# --- VISUALIZATION TABS ---
st.subheader("📊 Seller Revenue Distribution by Tier")
col_pie, col_bar = st.columns(2)

# Custom color palette mapping for merchant tiers
color_palette = {
    "Gold Seller": "#FFD700",    # Metallic Gold
    "Silver Seller": "#C0C0C0",  # Metallic Silver
    "Bronze Seller": "#CD7F32"   # Matte Bronze
}

with col_pie:
    st.markdown("#### 🎯 Overall Volume Share per Seller Group")
    fig_pie = px.pie(
        pie_summary_df,
        names="seller_tier",
        values="tier_total_sales",
        color="seller_tier",
        color_discrete_map=color_palette,
        category_orders={"seller_tier": ["Gold Seller", "Silver Seller", "Bronze Seller"]},
        hole=0.4
    )
    fig_pie.update_traces(
        textinfo="percent+value",
        texttemplate="%{label}<br>%{percent}<br>$%{value:,.2f}"
    )
    fig_pie.update_layout(height=450, showlegend=False)
    st.plotly_chart(fig_pie, use_container_width=True)

with col_bar:
    st.markdown("#### 🏙️ Regional Performance Breakdown")
    fig_bar = px.bar(
        summary_df,
        x="seller_city",
        y="tier_total_sales",
        color="seller_tier",
        color_discrete_map=color_palette,
        category_orders={"seller_tier": ["Gold Seller", "Silver Seller", "Bronze Seller"]},
        barmode="group",
        text_auto='.2s',
        labels={
            "seller_city": "Seller City Hub",
            "tier_total_sales": "Aggregated Sales ($)",
            "seller_tier": "Performance Tier"
        }
    )
    fig_bar.update_layout(height=450, hovermode="x unified")
    st.plotly_chart(fig_bar, use_container_width=True)

# --- UNDERLYING METRICS INSPECTION ---
st.markdown("---")
st.markdown("### 📊 Consolidated Summary Matrices")

t_col1, t_col2 = st.columns([2, 1])
with t_col1:
    st.markdown("**Structured Aggregate Table View**")
    st.dataframe(summary_df, use_container_width=True)
with t_col2:
    st.markdown("**City Merchant Revenue Totals**")
    city_totals = summary_df.groupby("seller_city")["tier_total_sales"].sum().reset_index()
    for _, row in city_totals.iterrows():
        st.metric(label=f"Total Revenue: {row['seller_city']}", value=f"${row['tier_total_sales']:,.2f}")

total_pipeline_duration = time.perf_counter() - total_start
st.sidebar.metric("Total App Loop Time", f"{total_pipeline_duration:.2f}s")