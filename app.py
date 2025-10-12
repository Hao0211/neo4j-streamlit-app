import streamlit as st
import pandas as pd
import os
import tempfile
from pathlib import Path
from neo4j import GraphDatabase
import datetime
from pyvis.network import Network

# -----------------------
# 🔐 Neo4j Credentials
# -----------------------
NEO4J_URI = st.secrets.get("NEO4J_URI", "neo4j+s://2469831c.databases.neo4j.io")
NEO4J_USERNAME = st.secrets.get("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = st.secrets.get("NEO4J_PASSWORD", "VZzJzRBADaHoeLuwJsib9fDY5BbxUW0xCakjjkFJCIk")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

# -----------------------
# 📁 文件保存目录
# -----------------------
UPLOAD_DIR = Path("uploaded_data")
UPLOAD_DIR.mkdir(exist_ok=True)

st.title("📊 Neo4j Transaction Graph Viewer")

# -----------------------
# 📤 上传 CSV 并保存
# -----------------------
uploaded_file = st.file_uploader("Upload a CSV file", type=["csv"])
if uploaded_file:
    save_path = UPLOAD_DIR / uploaded_file.name
    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    st.success(f"✅ File '{uploaded_file.name}' uploaded and saved.")
    st.session_state["selected_file"] = uploaded_file.name

# -----------------------
# 📜 选择或删除历史文件
# -----------------------
st.sidebar.header("📂 File Management")

files = sorted([f.name for f in UPLOAD_DIR.glob("*.csv")])
if files:
    selected_file = st.sidebar.selectbox("Select a saved CSV file", files, index=0)
    delete_btn = st.sidebar.button(f"🗑️ Delete '{selected_file}'")
    if delete_btn:
        os.remove(UPLOAD_DIR / selected_file)
        st.sidebar.success(f"Deleted '{selected_file}'")
        st.rerun()
else:
    st.sidebar.warning("No uploaded files yet.")
    st.stop()

# -----------------------
# 📊 读取所选 CSV
# -----------------------
csv_path = UPLOAD_DIR / selected_file
df = pd.read_csv(csv_path, parse_dates=["created_at", "updated_at"])
st.success(f"Loaded '{selected_file}' successfully.")
st.dataframe(df, height=300, use_container_width=True)

# -----------------------
# 🚀 导入 Neo4j (与之前相同)
# -----------------------
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

# -----------------------
# 🕸️ Graph Visualization（同原版）
# -----------------------
st.subheader("Graph Visualization")

# ...（保留你原本的 pyvis 网络图逻辑，这里略）...
