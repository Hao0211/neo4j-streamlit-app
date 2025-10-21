import streamlit as st
import pandas as pd
import os
import tempfile
from pathlib import Path
from pyvis.network import Network
from datetime import datetime, timedelta

# -------------------------------
# 页面配置
# -------------------------------
st.set_page_config(page_title="Transaction Graph Viewer", layout="wide")
st.title("📊 Transaction Graph Viewer")

# -------------------------------
# 上传文件目录（多人共享）
# -------------------------------
UPLOAD_DIR = Path("uploaded_data")
UPLOAD_DIR.mkdir(exist_ok=True)

# -------------------------------
# Sidebar: 上传与文件管理
# -------------------------------
st.sidebar.header("📤 Upload CSV")
uploaded_file = st.sidebar.file_uploader("Drag and drop or browse to upload CSV", type=["csv"])
if uploaded_file:
    save_path = UPLOAD_DIR / uploaded_file.name
    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    st.sidebar.success(f"✅ Saved: {uploaded_file.name}")
    st.session_state["selected_file"] = uploaded_file.name

st.sidebar.header("📂 Manage files")
files = sorted([f.name for f in UPLOAD_DIR.glob("*.csv")], reverse=True)
if files:
    file_to_delete = st.sidebar.selectbox("Select file to delete", files)

    # 删除确认弹窗
    if st.sidebar.button("🗑️ Delete selected file"):
        with st.sidebar:
            st.warning(f"⚠️ Are you sure you want to delete `{file_to_delete}`?")
            confirm = st.button("✅ Yes, delete permanently")
            cancel = st.button("❌ Cancel")

            if confirm:
                os.remove(UPLOAD_DIR / file_to_delete)
                st.success(f"Deleted {file_to_delete}")
                st.experimental_rerun()
            elif cancel:
                st.info("Deletion cancelled.")
else:
    st.sidebar.info("No uploaded CSV files yet.")

# -------------------------------
# 主区：选择并加载 CSV
# -------------------------------
st.header("📁 Uploaded CSV Files")

files = sorted([f.name for f in UPLOAD_DIR.glob("*.csv")], reverse=True)
if not files:
    st.info("No CSV files available. Upload one from the sidebar to begin.")
    st.stop()

selected_filename = st.selectbox("Select an uploaded CSV to load", files, index=0)
csv_path = UPLOAD_DIR / selected_filename

# 尝试解析并显示部分内容
try:
    df = pd.read_csv(csv_path)
except Exception as e:
    st.error(f"Failed to read CSV: {e}")
    st.stop()

st.success(f"✅ Loaded: {selected_filename}")
st.dataframe(df.head(8), use_container_width=True)

# -------------------------------
# 列名检查
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
# Sidebar: Filters
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

    # 线条粗细根据金额变化
    edge_width = max(2, min(12, total_amt / 10000))
    net.add_edge(
        from_user,
        to_user,
        label=label,
        title=f"{from_user} → {to_user}\n{label}",
        color="rgba(80,80,80,0.85)",
        width=edge_width
    )

# 高亮 tracked_username
net.add_node(selected_tracked, label=selected_tracked, size=35, color="#FFD700", font={"size": 26, "bold": True})

# -------------------------------
# ✅ 修正的安全输出方式（不写入文件）
# -------------------------------
try:
    html_str = net.generate_html()  # 直接生成 HTML 字符串
    st.components.v1.html(html_str, height=820, scrolling=True)
except Exception as e:
    st.error(f"Graph rendering failed: {e}")
