import streamlit as st
import pandas as pd
import os
import tempfile
from pathlib import Path
from pyvis.network import Network

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
    selected_file = st.sidebar.selectbox("Select file to view", files, index=0, key="file_select")
    st.session_state["selected_file"] = selected_file

    # 删除按钮 + 确认弹窗
    if st.sidebar.button("🗑️ Delete selected file"):
        with st.sidebar:
            st.warning(f"⚠️ Are you sure you want to delete `{selected_file}`?")
            confirm = st.button("✅ Confirm Delete")
            cancel = st.button("❌ Cancel")
            if confirm:
                os.remove(UPLOAD_DIR / selected_file)
                st.success(f"Deleted {selected_file}")
                st.experimental_rerun()
            elif cancel:
                st.info("Delete cancelled.")
else:
    st.sidebar.info("No uploaded CSV files yet.")
    st.stop()

# -------------------------------
# 加载 CSV 文件
# -------------------------------
selected_filename = st.session_state.get("selected_file", files[0] if files else None)
if not selected_filename:
    st.info("No CSV selected.")
    st.stop()

csv_path = UPLOAD_DIR / selected_filename

try:
    df = pd.read_csv(csv_path)
except Exception as e:
    st.error(f"❌ Failed to read CSV: {e}")
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
# Sidebar: 过滤器
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
st.markdown("## **Graph Visualization**", unsafe_allow_html=True)

net = Network(height="780px", width="100%", bgcolor="#FFFFFF", directed=True)
net.force_atlas_2based(
    gravity=-100,
    central_gravity=0.01,
    spring_length=220,
    spring_strength=0.03,
    damping=0.6
)

# 设置视觉样式（文字加大加粗）
net.set_options("""
{
  "nodes": {
    "font": {
      "size": 20,
      "face": "arial",
      "color": "#000000",
      "bold": true
    },
    "shape": "dot",
    "scaling": {
      "min": 10,
      "max": 40
    }
  },
  "edges": {
    "color": {
      "color": "rgba(80,80,80,0.7)",
      "highlight": "rgba(255,0,0,0.8)"
    },
    "arrows": {
      "to": {
        "enabled": true,
        "scaleFactor": 0.7
      }
    },
    "smooth": false
  },
  "physics": {
    "enabled": true,
    "stabilization": {
      "enabled": true,
      "iterations": 1000
    }
  },
  "interaction": {
    "hover": true,
    "tooltipDelay": 150,
    "zoomView": true
  }
}
""")

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
        net.add_node(from_user, label=from_user, size=18, color="#87CEFA")
        nodes_added.add(from_user)
    if to_user not in nodes_added:
        net.add_node(to_user, label=to_user, size=18, color="#90EE90")
        nodes_added.add(to_user)

    edge_width = max(2, min(10, total_amt / 10000))
    net.add_edge(
        from_user,
        to_user,
        label=label,
        title=f"{from_user} → {to_user}\n{label}",
        color="rgba(80,80,80,0.85)",
        width=edge_width
    )

# 高亮 tracked 用户
net.add_node(selected_tracked, label=selected_tracked, size=30, color="#FFD700")

tmp_dir = tempfile.gettempdir()
html_path = os.path.join(tmp_dir, "graph.html")
net.write_html(html_path)
st.components.v1.html(Path(html_path).read_text(), height=790)
