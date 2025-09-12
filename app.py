from pyvis.network import Network
import streamlit as st
import pandas as pd
import os
import tempfile
from pathlib import Path
from neo4j import GraphDatabase
import datetime

# Neo4j Aura credentials
NEO4J_URI = "neo4j+s://2469831c.databases.neo4j.io"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "VZzJzRBADaHoeLuwJsib9fDY5BbxUW0xCakjjkFJCIk"
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

# CSV 上传
uploaded_file = st.file_uploader("Upload your CSV file", type=["csv"])
if uploaded_file is not None:
    df = pd.read_csv(uploaded_file, parse_dates=["created_at", "updated_at"])
    st.success("CSV file loaded successfully.")
    if "title" in df.columns and "body" in df.columns:
        st.subheader("Template Preview")
        st.dataframe(df, height=300, use_container_width=True)
else:
    st.warning("Please upload a CSV file to proceed.")
    st.stop()

# 导入 Neo4j
def import_to_neo4j(tx, row):
    tx.run("""
    MERGE (u:User {id: $user_id})
    ON CREATE SET u.username = $username
    MERGE (tx:Txn {order_id: $order_id})
    ON CREATE SET tx.title = $title, tx.created_at = datetime($created_at), tx.updated_at = datetime($updated_at)
    WITH u, tx
    FOREACH (_ IN CASE WHEN $ttype = 'Out' AND $tgt_type IN ['user','egg'] THEN [1] ELSE [] END |
        MERGE (v:User {id: $tgt_id})
        MERGE (u)-[r:TRANSFER {order_id: $order_id}]->(v)
        ON CREATE SET r.points = $reward_points, r.created_at = datetime($created_at)
        MERGE (u)-[:HAS_TXN]->(tx)
        MERGE (tx)-[:TO]->(v)
    )
    FOREACH (_ IN CASE WHEN $ttype = 'Out' AND $tgt_type = 'rewardslink_payment_gateway' THEN [1] ELSE [] END |
        MERGE (t:Target {key: $key_spend})
        ON CREATE SET t.type = $tgt_type, t.name = $packages_title
        MERGE (u)-[s:SPEND {order_id: $order_id}]->(t)
        ON CREATE SET s.amount = $amount, s.currency = $currency, s.ori_amount = $ori_amount, s.ori_currency = $ori_currency, s.created_at = datetime($created_at)
        MERGE (u)-[:HAS_TXN]->(tx)
        MERGE (tx)-[:TO]->(t)
    )
    FOREACH (_ IN CASE WHEN $ttype = 'In' THEN [1] ELSE [] END |
        MERGE (src:Source {key: $key_spend})
        ON CREATE SET src.type = $tgt_type, src.name = $title
        MERGE (src)-[rin:RECEIVED {order_id: $order_id}]->(u)
        ON CREATE SET rin.points = $reward_points, rin.created_at = datetime($created_at)
        MERGE (u)-[:HAS_TXN]->(tx)
    )
    """, {
        "user_id": int(row["id"]),
        "username": row["username"],
        "order_id": row["order_id"],
        "title": row["title"],
        "packages_title": row["packages_title"],
        "ttype": row["type"],
        "tgt_type": row["target_type"],
        "tgt_id": int(row["target_id"]) if pd.notna(row["target_id"]) else 0,
        "currency": row["currency"],
        "amount": float(row["amount"]) if pd.notna(row["amount"]) else 0.0,
        "ori_currency": row["ori_currency"],
        "ori_amount": float(row["ori_amount"]) if pd.notna(row["ori_amount"]) else 0.0,
        "reward_points": float(row["reward_points"]) if pd.notna(row["reward_points"]) else 0.0,
        "created_at": row["created_at"].strftime('%Y-%m-%dT%H:%M:%S'),
        "updated_at": row["updated_at"].strftime('%Y-%m-%dT%H:%M:%S'),
        "key_spend": f"{row['target_type']}:{int(row['target_id'])}" if pd.notna(row["target_id"]) else row["title"]
    })

if st.button("Import to Neo4j"):
    with driver.session() as session:
        for _, row in df.iterrows():
            session.write_transaction(import_to_neo4j, row)
    st.success("Data imported into Neo4j successfully.")

# Sidebar filters
st.sidebar.header("Graph Filters")
usernames = df['username'].unique().tolist()
usernames_with_all = ["All"] + usernames
selected_users = st.sidebar.multiselect("Select username(s)", usernames_with_all, default=["All"])
rel_types = ["TRANSFER", "SPEND", "RECEIVED"]
selected_rels = st.sidebar.multiselect("Select relationship types", rel_types, default=rel_types)
today = datetime.date.today()
two_years_ago = today - datetime.timedelta(days=730)
date_range = st.sidebar.date_input("Select date range", [two_years_ago, today])

# Filter dataframe
filtered_df = df.copy()
if selected_user != "All":
    filtered_df = filtered_df[filtered_df['username'] == selected_user]
filtered_df = filtered_df[
    (filtered_df['created_at'] >= pd.to_datetime(date_range[0])) &
    (filtered_df['created_at'] <= pd.to_datetime(date_range[1]))
]

# 图谱初始化
st.subheader("Graph Visualization")
net = Network(height="780px", width="100%", notebook=False, bgcolor="#FFFFFF", font_color="#000000", directed=True)
net.force_atlas_2based(gravity=-50, central_gravity=0.01, spring_length=200, spring_strength=0.08, damping=0.4)

# SPEND
if "SPEND" in selected_rels:
    spend_grouped = filtered_df[
        (filtered_df['type'] == 'Out') & (filtered_df['target_type'] == 'rewardslink_payment_gateway')
    ].groupby(['id', 'username', 'packages_title', 'target_id', 'ori_currency'])['ori_amount'].sum().round(2).reset_index()
    for _, row in spend_grouped.iterrows():
        sender = f"{row['username']}_{row['id']}"
        tid = f"Target:{row['target_id']}_{row['packages_title']}"
        net.add_node(sender, label=row['username'], shape='ellipse', color='#FFF8DC')
        net.add_node(tid, label=row['packages_title'], shape='box', color='#FFE4E1')
        net.add_edge(sender, tid,
                     label=f'SPEND ({row["ori_amount"]} {row["ori_currency"]})',
                     title=f'SPEND {row["ori_amount"]} {row["ori_currency"]} to {row["packages_title"]}',
                     color='#AAAAAA', arrows='to')

# TRANSFER
if "TRANSFER" in selected_rels:
    transfer_grouped = filtered_df[
        (filtered_df['type'] == 'Out') & (filtered_df['target_type'].isin(['user', 'egg']))
    ].groupby(['id', 'username', 'target_id', 'title'])['reward_points'].sum().round(2).reset_index()
    for _, row in transfer_grouped.iterrows():
        sender = f"{row['username']}_{row['id']}"
        receiver_node = f"User_{row['target_id']}_{row['title']}"
        net.add_node(sender, label=row['username'], shape='ellipse', color='#FFF8DC')
        net.add_node(receiver_node, label=row['title'], shape='ellipse', color='#E0FFFF')
        net.add_edge(sender, receiver_node,
                     label=f'TRANSFER ({row["reward_points"]} points)',
                     title=f'TRANSFER {row["reward_points"]} reward points to {row["target_id"]}',
                     color='#AAAAAA', arrows='to')

# RECEIVED
if "RECEIVED" in selected_rels:
    received_grouped = filtered_df[
        (filtered_df['type'] == 'In')
    ].groupby(['id', 'username', 'title', 'target_id'])['reward_points'].sum().round(2).reset_index()
    for _, row in received_grouped.iterrows():
        receiver = f"{row['username']}_{row['id']}"
        source_node = f"Source:{row['target_id']}_{row['title']}"
        net.add_node(receiver, label=row['username'], shape='ellipse', color='#FFF8DC')
        net.add_node(source_node, label=row['title'], shape='box', color='#F0FFF0')
        net.add_edge(source_node, receiver,
                     label=f'RECEIVED ({row["reward_points"]} points)',
                     title=f'RECEIVED {row["reward_points"]} reward points from {row["title"]}',
                     color='#AAAAAA', arrows='to')

# 输出图谱 HTML
tmp_dir = tempfile.gettempdir()
html_path = os.path.join(tmp_dir, "graph.html")
net.write_html(html_path)
st.components.v1.html(Path(html_path).read_text(), height=790)
with open(html_path, "rb") as f:
    st.download_button("Download Graph as HTML", f, file_name="graph_visualization.html")
