import streamlit as st
import pandas as pd
import requests
from pathlib import Path
from pyvis.network import Network
from datetime import datetime

# -------------------------------
# 页面配置
# -------------------------------
st.set_page_config(page_title="Transaction Graph Viewer", layout="wide")
st.title("📊 Transaction Graph Viewer")

# -------------------------------
# GitHub 仓库设置
# -------------------------------
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/Hao0211/neo4j-streamlit-app/main/data/"

# -------------------------------
# 获取 data 文件夹下的文件列表
# -------------------------------
@st.cache_data(ttl=300)
def list_github_files():
    api_url = "https://api.github.com/repos/Hao0211/neo4j-streamlit-app/contents/data"
    r = requests.get(api_url)
    if r.status_code != 200:
        st.error("❌ 无法从 GitHub 获取文件列表，请检查仓库名称或路径。")
        return []
    data = r.json()
    csv_files = [item["name"] for item in data if item["name"].endswith(".csv")]
    return sorted(csv_files, reverse=True)

files = list_github_files()

# -------------------------------
# 文件选择
# -------------------------------
st.sidebar.header("📁 Select CSV from GitHub")
if not files:
    st.sidebar.warning("GitHub /data 文件夹中没有 CSV 文件。请先上传文件到仓库。")
    st.stop()

selected_filename = st.sidebar.selectbox("Choose CSV file", files)
csv_url = f"{GITHUB_RAW_BASE}{selected_filename}"

# -------------------------------
# 加载 CSV
# -------------------------------
@st.cache_data(ttl=300)
def load_csv_from_github(url):
    return pd.read_csv(url)

try:
    df = load_csv_from_github(csv_url)
    st.success(f"✅ Loaded: {selected_filename}")
    st.dataframe(df.head(8), use_container_width=True)
except Exception as e:
    st.error(f"读取 GitHub CSV 文件失败：{e}")
    st.stop()

# -------------------------------
# 列名检测
# -------------------------------
col_map = {c.lower(): c for c in df.columns}
def colname(*candidates):
    for c in candidates:
        if c.lower() in col_map:
            return col_map[c.lower()]
    return None

tracked_col = colname("tracked_username")
from_col = colname("from_username")
to_col = colname("to_username")
total_amt_col = colname("total_amount_received")
txn_count_col = colname("distinct_txn_count")
level_col = colname("level")
date_col = colname("last_received_at", "first_received_at", "date")

required = [tracked_col, from_col, to_col, total_amt_col, txn_count_col, level_col]
missing = [c for c, v in zip(
    ["tracked_username","from_username","to_username","total_amount_received","distinct_txn_count","level"], 
    required
) if v is None]

if missing:
    st.error(f"CSV missing required columns: {', '.join(missing)}.")
    st.stop()

if date_col:
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

# -------------------------------
# Sidebar Filters
# -------------------------------
st.sidebar.header("🔍 Graph Filters")

tracked_candidates = sorted(df[tracked_col].dropna().astype(str).unique().tolist())
selected_tracked = st.sidebar.selectbox("Filter · tracked_username", tracked_candidates, index=0)

if date_col and df[date_col].notna().any():
    min_date = df[date_col].min().date()
    max_date = df[date_col].max().date()
    date_range = st.sidebar.date_input("Select date range", [min_date, max_date])
    start_ts = pd.to_datetime(date_range[0])
    end_ts = pd.to_datetime(date_range[1]) + pd.Timedelta(days=1)
    df = df[(df[date_col] >= start_ts) & (df[date_col] < end_ts)]

# -------------------------------
# 根据 tracked_username 过滤数据
# -------------------------------
filtered = df[df[tracked_col] == selected_tracked].copy()
if filtered.empty:
    st.warning("No data for selected tracked_username.")
    st.stop()

# -------------------------------
# 绘制 PyVis 图表
# -------------------------------
st.markdown(
    f"<h2 style='font-weight: 800; font-size: 28px;'>📈 Graph Visualization for <span style=\"color:#B8B8B8\">{selected_tracked}</span></h2>",
    unsafe_allow_html=True
)

net = Network(height="800px", width="100%", bgcolor="#FFFFFF", directed=True)
net.force_atlas_2based(
    gravity=-100,
    central_gravity=0.01,
    spring_length=220,
    spring_strength=0.03,
    damping=0.6
)

def fmt_amount(v):
    try:
        if abs(v - round(v)) < 1e-9:
            return f"{int(round(v))}RP"
        return f"{v:,.2f}RP"
    except Exception:
        return str(v)

filtered = filtered.sort_values(by=level_col)
nodes_added = set()

for _, row in filtered.iterrows():
    from_user = str(row[from_col])
    to_user = str(row[to_col])
    total_amt = float(row[total_amt_col]) if pd.notna(row[total_amt_col]) else 0.0
    txn_count = int(row[txn_count_col]) if pd.notna(row[txn_count_col]) else 0
    label = f"{fmt_amount(total_amt)} ({txn_count})"

    if from_user not in nodes_added:
        net.add_node(from_user, label=from_user, size=20, color="#87CEFA", font={"size": 22, "bold": True})
        nodes_added.add(from_user)
    if to_user not in nodes_added:
        net.add_node(to_user, label=to_user, size=20, color="#90EE90", font={"size": 22, "bold": True})
        nodes_added.add(to_user)

    edge_width = max(2, min(12, total_amt / 10000))
    net.add_edge(from_user, to_user, label=label, title=f"{from_user} → {to_user}\n{label}", color="rgba(80,80,80,0.85)", width=edge_width)

# 高亮 tracked_username
net.add_node(selected_tracked, label=selected_tracked, size=35, color="#FFD700", font={"size": 26, "bold": True})

# -------------------------------
# 直接显示 HTML，不写文件
# -------------------------------
try:
    html_str = net.generate_html()
    st.components.v1.html(html_str, height=820, scrolling=True)
except Exception as e:
    st.error(f"Graph rendering failed: {e}")
