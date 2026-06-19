import os
import time
import psutil
import plotly.express as px
import streamlit as st
from google.cloud import bigquery
from dotenv import load_dotenv

# Initialize Streamlit configuration layout
st.set_page_config(page_title="Customer Spend Tiers & Ranges", layout="wide")

st.title("🏆 BigQuery Engine: Customer Tier Analysis & Volume")
st.markdown("Evaluating spending ranges, total revenue, and headcount metrics for Gold, Silver, and Bronze customers inside the top 3 cities.")

# Helper function to monitor local system resources
def get_process_metrics():
    process = psutil.Process(os.getpid())
    return {
        "memory": process.memory_info().rss / (1024 * 1024),
        "cpu": psutil.cpu_percent(interval=None)
    }

@st.cache_data(show_spinner="Computing spending metrics inside BigQuery...")
def get_bigquery_range_data():
    # Load background cloud credential environment variables safely
    load_dotenv(dotenv_path='../../.env')
    client = bigquery.Client(project=os.getenv('GCP_PROJECT_ID'))
    dataset = os.getenv('TARGET_BIGQUERY_DATASET_ID')

    # This SQL handles finding top cities, calculating customer totals, counting headcounts, and extracting min/max ranges
    query = f"""
    WITH top_cities AS (
        SELECT c.city_name
        FROM `{dataset}.fct_order_items` foi
        JOIN `{dataset}.dim_customers` c ON foi.customer_id = c.customer_id
        GROUP BY c.city_name
        ORDER BY SUM(foi.item_price_amount + foi.freight_cost_amount) DESC
        LIMIT 3
    ),
    customer_lifetime_spend AS (
        SELECT 
            c.customer_id,
            c.city_name AS customer_city,
            SUM(foi.item_price_amount + foi.freight_cost_amount) AS total_customer_spending
        FROM `{dataset}.fct_order_items` foi
        JOIN `{dataset}.dim_orders` do ON foi.order_id = do.order_id
        JOIN `{dataset}.dim_customers` c ON foi.customer_id = c.customer_id
        WHERE do.order_status = 'delivered'
          AND c.city_name IN (SELECT city_name FROM top_cities)
        GROUP BY c.customer_id, c.city_name
    ),
    classified_customers AS (
        SELECT 
            customer_city,
            total_customer_spending,
            CASE 
                WHEN total_customer_spending >= 500 THEN 'Gold Tier'
                WHEN total_customer_spending >= 150 AND total_customer_spending < 500 THEN 'Silver Tier'
                ELSE 'Bronze Tier'
            END AS customer_tier
        FROM customer_lifetime_spend
    )
    SELECT 
        customer_tier,
        COUNT(1) AS total_customers,
        ROUND(MIN(total_customer_spending), 2) AS min_spending,
        ROUND(MAX(total_customer_spending), 2) AS max_spending,
        ROUND(AVG(total_customer_spending), 2) AS avg_spending,
        ROUND(SUM(total_customer_spending), 2) AS total_tier_revenue
    FROM classified_customers
    GROUP BY customer_tier
    ORDER BY min_spending DESC
    """
    return client.query(query).to_dataframe()

# 1. START BACKEND TIMER
total_start = time.perf_counter()

# 2. RUN AND TIME BIGQUERY COMPUTE BLOCK
baseline_metrics = get_process_metrics()
proc_start = time.perf_counter()

# Ingest the metrics layout matrix directly from the warehouse
range_df = get_bigquery_range_data()

proc_duration = time.perf_counter() - proc_start
post_metrics = get_process_metrics()

memory_used_mb = max(0.0, post_metrics["memory"] - baseline_metrics["memory"])
cpu_utilization = psutil.cpu_percent(interval=None)

# --- SIDEBAR PERFORMANCE METRICS ---
st.sidebar.header("⚙️ BigQuery Profile Metrics")
st.sidebar.metric("Warehouse Compute Time", f"{proc_duration:.4f}s")
st.sidebar.metric("Local RAM Delta", f"{memory_used_mb:.2f} MB")
st.sidebar.metric("Local CPU Core Load", f"{cpu_utilization:.1f}%")

# --- HIGH LEVEL HEADCOUNT KPI METRICS ---
st.subheader("👥 Customer Volume Headcounts")
kpi_cols = st.columns(3)

# Force a dictionary search to cleanly parse metrics out regardless of row order returns
metrics_dict = range_df.set_index("customer_tier").to_dict(orient="index")

for idx, tier in enumerate(["Gold Tier", "Silver Tier", "Bronze Tier"]):
    with kpi_cols[idx]:
        if tier in metrics_dict:
            count = metrics_dict[tier]["total_customers"]
            rev = metrics_dict[tier]["total_tier_revenue"]
            st.metric(label=f"Total {tier} Customers", value=f"{count:,}", delta=f"${rev:,.2f} Total Spend", delta_color="normal")
        else:
            st.metric(label=f"Total {tier} Customers", value="0")

st.markdown("---")

# --- MAIN DASHBOARD VISUALIZATIONS ---
st.subheader("📊 Tier Spending & Range Breakdown")
col_chart, col_pie = st.columns([1, 1])

# Custom color palette matching the standard tier layout rules
color_palette = {
    "Gold Tier": "#FFD700",    # Gold Hex
    "Silver Tier": "#C0C0C0",  # Silver Hex
    "Bronze Tier": "#CD7F32"   # Bronze Hex
}

with col_chart:
    st.markdown("#### 💰 Average vs Max Spending Limits")
    # Melt dataframe columns to map min, max, and avg comparisons cleanly side by side
    melted_df = range_df.melt(
        id_vars=["customer_tier"], 
        value_vars=["min_spending", "avg_spending", "max_spending"],
        var_name="Metric", 
        value_name="Amount"
    )
    
    fig_bar = px.bar(
        melted_df,
        x="customer_tier",
        y="Amount",
        color="Metric",
        barmode="group",
        labels={"Amount": "Spending Value ($)", "customer_tier": "Customer Tier Group"},
        color_discrete_sequence=["#2ecc71", "#3498db", "#e74c3c"],
        text_auto='.2s'
    )
    fig_bar.update_layout(height=420)
    st.plotly_chart(fig_bar, use_container_width=True)

with col_pie:
    st.markdown("#### 🎯 Overall Revenue Share per Tier Group")
    fig_pie = px.pie(
        range_df,
        names="customer_tier",
        values="total_tier_revenue",
        color="customer_tier",
        color_discrete_map=color_palette,
        category_orders={"customer_tier": ["Gold Tier", "Silver Tier", "Bronze Tier"]},
        hole=0.4
    )
    fig_pie.update_traces(
        textinfo="percent+value",
        texttemplate="%{label}<br>%{percent}<br>$%{value:,.2f}"
    )
    fig_pie.update_layout(height=420, showlegend=False)
    st.plotly_chart(fig_pie, use_container_width=True)

# --- STRUCTURED DATA VIEWS ---
st.markdown("---")
st.markdown("### 📊 Consolidated Summary Statistics Table")

# Format columns for crisp display in the Streamlit UI table
formatted_df = range_df.copy()
formatted_df["min_spending"] = formatted_df["min_spending"].map("${:,.2f}".format)
formatted_df["max_spending"] = formatted_df["max_spending"].map("${:,.2f}".format)
formatted_df["avg_spending"] = formatted_df["avg_spending"].map("${:,.2f}".format)
formatted_df["total_tier_revenue"] = formatted_df["total_tier_revenue"].map("${:,.2f}".format)
formatted_df["total_customers"] = formatted_df["total_customers"].map("{:,}".format)

st.dataframe(formatted_df, use_container_width=True)

total_pipeline_duration = time.perf_counter() - total_start
st.sidebar.metric("Total App Loop Time", f"{total_pipeline_duration:.2f}s")