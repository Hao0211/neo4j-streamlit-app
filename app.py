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
# Sidebar: 上传与文件管理 (修复版)
# -------------------------------
st.sidebar.header("📤 Upload CSV")
uploaded_file = st.sidebar.file_uploader("Drag and drop or browse to upload CSV", type=["csv"])
if uploaded_file:
    save_path = UPLOAD_DIR / uploaded_file.name
    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    st.sidebar.success(f"✅ Saved: {uploaded_file.name}")
    # 自动把上传的文件设为被选择的文件并重新渲染
    st.session_state["selected_file"] = uploaded_file.name
    st.experimental_rerun()

st.sidebar.header("📂 Manage files")

def get_sorted_files():
    return sorted([p.name for p in UPLOAD_DIR.glob("*.csv")], reverse=True)

files = get_sorted_files()

if not files:
    st.sidebar.info("No uploaded CSV files yet.")
else:
    # 使用 key 让 Streamlit 管理 selectbox 的状态
    selected = st.sidebar.selectbox("Select file to delete / load", files, key="selected_file")
    if st.sidebar.button("🗑️ Delete selected file"):
        target_path = UPLOAD_DIR / selected
        if target_path.exists():
            try:
                target_path.unlink()  # 更稳妥的删除方法
                st.sidebar.success(f"Deleted {selected}")
            except Exception as e:
                st.sidebar.error(f"Failed to delete {selected}: {e}")
            # 清除 session_state 中对已删除文件的引用，避免后续访问旧对象
            if "selected_file" in st.session_state:
                st.session_state.pop("selected_file", None)
            # 立刻刷新页面，selectbox 会重新用最新文件列表渲染
            st.experimental_rerun()
        else:
            st.sidebar.warning(f"File {selected} not found (may have been removed).")
            if "selected_file" in st.session_state:
                st.session_state.pop("selected_file", None)
            st.experimental_rerun()

# -------------------------------
# 主区：选择并加载 CSV
# -------------------------------
st.header("📁 Uploaded CSV Files")

files = get_sorted_files()
if not files:
    st.info("No CSV files available. Upload one from the sidebar to begin.")
    st.stop()

# 这里也用 key="selected_file"，这样左侧 selectbox 与这里保持同一状态
# 如果 session_state["selected_file"] 在上传时已被设置，selectbox 会自动选中它
selected_filename = st.selectbox("Select an uploaded CSV to load", files, index=0, key="selected_file")
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
missing = [c for c, v in zip(["tracked_username","from_username","to_username","total_amount_received","distinct_txn_count","level"], required) if v is None]
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
# 默认选第一个（不要 "All"），如果 session_state 有值则 selectbox 会使用
default_index = 0
if "selected_file" in st.session_state and st.session_state["selected_file"] in tracked_candidates:
    # 不改默认_index；tracked selection separate from file name
    pass

# 使用一个不同的 key 管理 tracked_username 的选择
selected_tracked = st.sidebar.selectbox("Filter · tracked_username", tracked_candidates, index=default_index, key="tracked_select")

if date_col and df[date_col].notna().any():
    min_date = df[date_col].min().date()
    max_date = df[date_col].max().date()
    # 给用户合理默认范围
    two_years_ago = datetime.today().date() - timedelta(days=730)
    default_start = max(two_years_ago, min_date)
    default_end = max_date
    date_range = st.sidebar.date_input("Select date range", [default_start, default_end], key="date_range")
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
if selected_tracked:
    filtered = filtered[filtered[tracked_col].astype(str) == str(selected_tracked)]
if start_ts is not None and end_ts is not None:
    filtered = filtered[(filtered[date_col] >= start_ts) & (filtered[date_col] <= end_ts)]

if filtered.empty:
    st.warning("No records match the selected filters.")
    st.stop()

# -------------------------------
# 聚合数据 (按 level 保持顺序)
# -------------------------------
# 对于相同 level，保持现有顺序；我们会用 level 列来构造链状关系
filtered = filtered.sort_values(by=level_col)
agg = (
    filtered
    .groupby([tracked_col, from_col, to_col, level_col], dropna=True, as_index=False)
    .agg({
        total_amt_col: "sum",
        txn_count_col: "sum"
    })
)

# -------------------------------
# 建立 PyVis 图表
# -------------------------------
st.subheader(f"Graph Visualization for '{selected_tracked}'")

net = Network(height="780px", width="100%", bgcolor="#FFFFFF", directed=True)
net.force_atlas_2based(gravity=-50, central_gravity=0.02, spring_length=150, spring_strength=0.05, damping=0.4)

def fmt_amount(v):
    try:
        if abs(v - round(v)) < 1e-9:
            return f"{int(round(v))}RP"
        return f"{v:,.2f}RP"
    except Exception:
        return str(v)

nodes_added = set()

# 逐行添加 edge: from -> to，label 格式为 "NNN RP (count)"
for _, row in agg.iterrows():
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

    net.add_edge(from_user, to_user, label=label, title=f"{from_user} → {to_user}\n{label}", color="#666666")

# 把 tracked_username 作为突出节点（若尚未添加）
if selected_tracked not in nodes_added:
    net.add_node(selected_tracked, label=selected_tracked, size=30, color="#FFD700")

# 可选：把最后一层的节点连到 tracked_username（若 to_user 不是 tracked）
# 如果数据本身最后一层的 to_user 就是 tracked_username，这一步会重复但 safe
# 这里检查并添加 edge from last-level to tracked if needed
# 找出最后一层的 to_user
last_level_rows = agg.sort_values(by=level_col, ascending=False).head(1)
if not last_level_rows.empty:
    # 添加边从最后 to -> tracked（如果 last to 不是 tracked already）
    last_to = str(last_level_rows.iloc[0][to_col])
    if last_to != selected_tracked:
        # 聚合金额/txn for last_to -> tracked (可以是 0 or no-op)
        net.add_edge(last_to, selected_tracked, label="", color="#BBBBBB")

tmp_dir = tempfile.gettempdir()
html_path = os.path.join(tmp_dir, "graph.html")
net.write_html(html_path)
st.components.v1.html(Path(html_path).read_text(), height=790)
