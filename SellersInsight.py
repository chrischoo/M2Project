import os
from google.cloud import bigquery
from dotenv import load_dotenv
import polars as pl

load_dotenv(dotenv_path='../../.env')
client = bigquery.Client(project=os.getenv('GCP_PROJECT_ID'))
dataset = os.getenv('TARGET_BIGQUERY_DATASET_ID')

query = f"""
SELECT mql.mql_id, cd.seller_id
FROM `{dataset}.olist_marketing_qualified_leads_dataset` mql
LEFT JOIN `{dataset}.olist_closed_deals_dataset` cd ON mql.mql_id = cd.mql_id
"""
df = pl.from_arrow(client.query(query).to_arrow())

leads = df["mql_id"].n_unique()
signups = df.filter(pl.col("seller_id").is_not_null())["seller_id"].n_unique()
rate = (signups / leads) * 100

print(f"Total Leads: {leads:,}")
print(f"Total Sign-ups: {signups:,}")
print(f"Sign-up Rate: {rate:.2f}%")