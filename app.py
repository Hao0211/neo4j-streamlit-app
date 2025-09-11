import streamlit as st
import pandas as pd
from neo4j import GraphDatabase
from pyvis.network import Network
import tempfile
import os
from pathlib import Path

# Neo4j Aura credentials
NEO4J_URI = "neo4j+s://2469831c.databases.neo4j.io"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "VZzJzRBADaHoeLuwJsib9fDY5BbxUW0xCakjjkFJCIk"
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

st.title("Neo4j Aura CSV Importer")
st.write("Upload a CSV file to import data into Neo4j, visualize relationships, and view user statistics.")

uploaded_file = st.file_uploader("Choose a CSV file", type="csv")

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    df['created_at'] = pd.to_datetime(df['created_at'])
    df['updated_at'] = pd.to_datetime(df['updated_at'])

    st.success("CSV file loaded successfully.")
    st.dataframe(df.head())

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

    st.subheader("User Aggregation Statistics")
    agg_df = df.groupby("id").agg({"reward_points": "sum", "ori_amount": "sum"}).reset_index()
    st.dataframe(agg_df)

    # Sidebar filters
    st.sidebar.header("Graph Filters")
    usernames = df['username'].unique().tolist()
    selected_user = st.sidebar.selectbox("Select username", ["All"] + usernames)
    rel_types = ["TRANSFER", "SPEND", "RECEIVED"]
    selected_rels = st.sidebar.multiselect("Select relationship types", rel_types, default=rel_types)
    min_date = df['created_at'].min()
    max_date = df['created_at'].max()
    date_range = st.sidebar.date_input("Select date range", [min_date, max_date])

    # Filter dataframe
    filtered_df = df.copy()
    if selected_user != "All":
        filtered_df = filtered_df[filtered_df['username'] == selected_user]

    filtered_df = filtered_df[
        (filtered_df['created_at'] >= pd.to_datetime(date_range[0])) &
        (filtered_df['created_at'] <= pd.to_datetime(date_range[1]))
    ]

    # Aggregation for tooltip enhancement
    spend_summary = df[(df['type'] == 'Out') & (df['target_type'] == 'rewardslink_payment_gateway')] \
        .groupby('packages_title')['ori_amount'].sum().to_dict()

    transfer_summary = df[(df['type'] == 'Out') & (df['target_type'].isin(['user', 'egg']))] \
        .groupby('target_id')['reward_points'].sum().to_dict()

    received_summary = df[df['type'] == 'In'] \
        .groupby('title')['reward_points'].sum().to_dict()

    # Graph visualization
    st.subheader("Graph Visualization")
    net = Network(height="800px", width="100%", notebook=False, bgcolor="#FFFFFF", font_color="#000000")
    net.force_atlas_2based(gravity=-50, central_gravity=0.01, spring_length=200, spring_strength=0.08, damping=0.4)

    for _, row in filtered_df.iterrows():
        sender = row['username']
        sender_title = f"Username: {sender}<br>User ID: {row['id']}"
        sender_url = f"https://yourdomain.com/user/{row['id']}"
        net.add_node(sender, label=sender, shape='ellipse', color='#FFF8DC', title=sender_title, url=sender_url)

        if row['type'] == 'Out' and row['target_type'] in ['user', 'egg'] and "TRANSFER" in selected_rels:
            receiver_row = df[df['id'] == row['target_id']]
            receiver = receiver_row['username'].values[0] if not receiver_row.empty else str(row['target_id'])
            total_transfer = transfer_summary.get(row['target_id'], row['reward_points'])
            receiver_title = f"Username: {receiver}<br>User ID: {row['target_id']}"
            receiver_url = f"https://yourdomain.com/user/{row['target_id']}"
            edge_title = f"TRANSFER<br>Points: {row['reward_points']}<br>Total TRANSFER: {total_transfer}<br>Created At: {row['created_at']}"
            net.add_node(receiver, label=receiver, shape='ellipse', color='#E0FFFF', title=receiver_title, url=receiver_url)
            net.add_edge(sender, receiver, label=f'TRANSFER ({row["reward_points"]})', color='#AAAAAA', title=edge_title)

        elif row['type'] == 'Out' and row['target_type'] == 'rewardslink_payment_gateway' and "SPEND" in selected_rels:
            tid = f"Target:{row['target_id']}"
            total_spend = spend_summary.get(row['packages_title'], row['ori_amount'])
            target_title = f"Target: {row['packages_title']}<br>Total SPEND: {total_spend} {row['ori_currency']}"
            target_url = f"https://yourdomain.com/target/{row['target_id']}"
            edge_title = f"SPEND<br>Amount: {row['ori_amount']} {row['ori_currency']}<br>Total SPEND: {total_spend}<br>Created At: {row['created_at']}"
            net.add_node(tid, label=row['packages_title'], shape='box', color='#FFE4E1', title=target_title, url=target_url)
            net.add_edge(sender, tid, label=f'SPEND ({row["ori_amount"]})', color='#AAAAAA', title=edge_title)

        elif row['type'] == 'In' and "RECEIVED" in selected_rels:
            sid = f"Source:{row['target_id']}"
            total_received = received_summary.get(row['title'], row['reward_points'])
            source_title = f"Source: {row['title']}<br>Total RECEIVED: {total_received}"
            source_url = f"https://yourdomain.com/source/{row['target_id']}"
            edge_title = f"RECEIVED<br>Points: {row['reward_points']}<br>Total RECEIVED: {total_received}<br>Created At: {row['created_at']}"
            net.add_node(sid, label=row['title'], shape='box', color='#F0FFF0', title=source_title, url=source_url)
            net.add_edge(sid, sender, label=f'RECEIVED ({row["reward_points"]})', color='#AAAAAA', title=edge_title)

    tmp_dir = tempfile.gettempdir()
    html_path = os.path.join(tmp_dir, "graph.html")
    net.write_html(html_path)
    st.components.v1.html(Path(html_path).read_text(), height=800)
