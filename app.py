import streamlit as st
import pandas as pd
import tempfile
from pathlib import Path
from pyvis.network import Network
import requests

# =========================================================
# 🔧 GitHub Repo 设定
# =========================================================
GITHUB_USER = "Hao0211"
GITHUB_REPO = "neo4j-streamlit-app"
DATA_FOLDER = "data"     # 你在 GitHub 里存 CSV 的目录
BRANCH = "main"
# =========================================================

st.set_page_config(page_title="Transaction Graph Viewer", layout="wide")
st.title("📊 Transaction Graph Viewer")

# =========================================================
# 📂 从 GitHub 读取 CSV 列表
# =========================================================
@st.cache_data(ttl=300)
def list_github_files():
    """列出 GitHub data/ 目录下所有 CSV 文件"""
    api_url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{DATA_FOLDER}?ref={BRANCH}"
    r = requests.get(api_url)
    if r.status_code != 200:
        st.error("❌ 无法读取 GitHub 文件列表，请确认仓库是 public 并存在 data 文件夹。")
        return []
    return [item["name"] for item in r.json() if item["name"].endswith(".csv")]

# =========================================================
# 📥 从 GitHub 下载并载入 CSV
# =========================================================
@st.cache_data(ttl=300)
def load_github_csv(filename):
    """从 GitHub raw 链接读取 CSV 内容"""
    raw_url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{BRANCH}/{DATA_FOLDER}/{filename}"
    df = pd.read_csv(raw_url)
    return df

# =========================================================
# 🧭 文件选择
# =========================================================
files = list_github_files()
if not files:
    st.warning("⚠️ 还没有上传 CSV 文件，请先在 GitHub 的 data 文件夹上传。")
    st.stop()

selected_filename = st.selectbox("Select a CSV file to load", files, index=0)
st.success(f"✅ Loaded: {selected_filename}")

df = load_github_csv(selected_filename)
st.dataframe(df.head(8), use_container_width=True)

# =========================================================
# 🧩 列名自动匹配
# =========================================================
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
    st.error(f"❌ CSV 缺少必要栏位: {', '.join(missing)}")
    st.stop()

if date_col:
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

# =========================================================
# 🎛️ Sidebar 筛选
# =========================================================
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

filtered = df[df[tracked_col] == selected_tracked].copy()
if filtered.empty:
    st.warning("⚠️ 没有符合条件的数据。")
    st.stop()

# =========================================================
# 🎨 绘制 PyVis 图表
# =========================================================
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

# 输出 HTML
tmp_dir = tempfile.gettempdir()
html_path = Path(tmp_dir) / "graph.html"
net.write_html(html_path)
st.components.v1.html(html_path.read_text(), height=820)
