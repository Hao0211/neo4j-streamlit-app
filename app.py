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
st.title("💹 Transaction Graph Viewer")

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
    if st.sidebar.button("🗑️ Delete selected file"):
        os.remove(UPLOAD_DIR / file_to_delete)
        st.sidebar.success(f"Deleted {file_to_delete}")
        st.experimental_rerun()
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

st.success(f"Loaded: {selected_filename}")
st.dataframe(df.head(8), use_container_width=True)

# -------------------------------
# 预处理：确认并规范列
# -------------------------------
col_map = {c.lower(): c for c in df.columns}

def colname(*candidates):
    for c in candidates:
        if c in col_map:
            return col_map[c]
        if c.lower() in col_map:
            return col_map[c.lower()]
    return None

tracked_col = colname("tracked_username", "tracked_user", "tracked")
from_col = colname("from_username", "from_user", "from")
total_amt_col = colname("total_amount_received", "total_amount", "amount", "total_received")
txn_count_col = colname("distinct_txn_count", "txn_count", "distinct_count", "count")
first_date_col = colname("first_received_at", "first_received", "first_date")
last_date_col = colname("last_received_at", "last_received", "last_date", "date")

missing = []
for name, var in [
    ("tracked_username", tracked_col),
    ("from_username", from_col),
    ("total_amount_received", total_amt_col),
    ("distinct_txn_count", txn_count_col)
]:
    if var is None:
        missing.append(name)

if missing:
    st.error(f"CSV missing required columns: {', '.join(missing)}.")
    st.stop()

date_col = last_date_col or first_date_col
if date_col:
    try:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    except Exception:
        df[date_col] = pd.to_datetime(df[date_col].astype(str), errors="coerce")
else:
    df["__noop_date__"] = pd.NaT
    date_col = "__noop_date__"

# -------------------------------
# Sidebar: Graph filters
# -------------------------------
st.sidebar.header("🔍 Graph Filters")

tracked_candidates = df[tracked_col].dropna().astype(str).unique().tolist()
tracked_candidates_sorted = sorted(tracked_candidates)
if not tracked_candidates_sorted:
    st.sidebar.error("No tracked_username values found.")
    st.stop()

selected_tracked = st.sidebar.selectbox("Filter · tracked_username", ["All"] + tracked_candidates_sorted, index=0)

today = datetime.today().date()
two_years_ago = today - timedelta(days=730)
if df[date_col].notna().any():
    min_date = df[date_col].min().date()
    max_date = df[date_col].max().date()
    default_start = max(two_years_ago, min_date)
    default_end = max_date
    date_range = st.sidebar.date_input("Select date range", [default_start, default_end])
    start_ts = pd.to_datetime(date_range[0])
    end_ts = pd.to_datetime(date_range[1]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
else:
    st.sidebar.info("No date column found — date filtering disabled.")
    start_ts = None
    end_ts = None

# -------------------------------
# 过滤数据
# -------------------------------
filtered = df.copy()
if selected_tracked != "All":
    filtered = filtered[filtered[tracked_col].astype(str) == str(selected_tracked)]
if start_ts is not None and end_ts is not None:
    filtered = filtered[(filtered[date_col] >= start_ts) & (filtered[date_col] <= end_ts)]

if filtered.empty:
    st.warning("No records match the selected filters.")
    st.stop()

# -------------------------------
# 聚合数据
# -------------------------------
agg = (
    filtered
    .groupby([tracked_col, from_col], dropna=True, as_index=False)
    .agg({
        total_amt_col: "sum",
        txn_count_col: "sum"
    })
)

tracked_values_in_data = agg[tracked_col].unique().tolist()

# -------------------------------
# 建立 PyVis 图表
# -------------------------------
st.subheader("Graph Visualization")

net = Network(height="780px", width="100%", notebook=False, bgcolor="#FFFFFF", font_color="#000000", directed=True)
net.force_atlas_2based(gravity=-50, central_gravity=0.02, spring_length=150, spring_strength=0.05, damping=0.4)

def fmt_amount(v):
    try:
        if abs(v - round(v)) < 1e-9:
            return f"{int(round(v)):,}"
        return f"{v:,.2f}"
    except Exception:
        return str(v)

for tracked in tracked_values_in_data:
    center_id = f"tracked::{tracked}"
    net.add_node(center_id, label=str(tracked), title=f"Tracked: {tracked}", size=30, color="#FFD700")
    sub = agg[agg[tracked_col].astype(str) == str(tracked)]
    for _, r in sub.iterrows():
        from_user = str(r[from_col])
        from_id = f"from::{from_user}"
        total_amt = float(r[total_amt_col]) if pd.notna(r[total_amt_col]) else 0.0
        txn_count = int(r[txn_count_col]) if pd.notna(r[txn_count_col]) else 0
        label = f"{fmt_amount(total_amt)} ({txn_count})"
        net.add_node(from_id, label=from_user, size=18, color="#87CEFA")
        net.add_edge(from_id, center_id, label=label, title=f"{from_user} → {tracked}\n{label}", arrows="to", color="#666666")

if len(tracked_values_in_data) == 1:
    net.toggle_physics(True)

tmp_dir = tempfile.gettempdir()
html_path = os.path.join(tmp_dir, "graph.html")
net.write_html(html_path)
st.components.v1.html(Path(html_path).read_text(), height=790)
