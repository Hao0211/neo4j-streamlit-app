import os
import streamlit as st
import pandas as pd
from pyvis.network import Network
import streamlit.components.v1 as components

st.set_page_config(page_title="Neo4j Graph Viewer", layout="wide")

# ========== 初始化 session state ==========
if "current_file" not in st.session_state:
    st.session_state.current_file = None
if "confirm_delete" not in st.session_state:
    st.session_state.confirm_delete = False

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# ========== 侧边栏文件管理 ==========
st.sidebar.header("📂 Manage Files")

# 获取 CSV 文件列表
csv_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".csv")]

selected_file = st.sidebar.selectbox("Select CSV File", csv_files, index=0 if csv_files else None)

# 当切换文件时自动载入
if selected_file and selected_file != st.session_state.current_file:
    st.session_state.current_file = selected_file

# 删除按钮
if selected_file:
    if st.sidebar.button("🗑️ Delete selected file"):
        st.session_state.confirm_delete = True

# 删除确认弹窗
if st.session_state.confirm_delete:
    st.dialog("⚠️ Confirm Deletion")  # ✅ 使用 dialog 而不是 modal
    st.write(f"Are you sure you want to delete **{st.session_state.current_file}**?")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Yes, delete"):
            try:
                os.remove(os.path.join(DATA_DIR, st.session_state.current_file))
                st.success(f"File **{st.session_state.current_file}** deleted successfully.")
                st.session_state.current_file = None
            except Exception as e:
                st.error(f"Error deleting file: {e}")
            st.session_state.confirm_delete = False
            st.experimental_rerun()
    with col2:
        if st.button("❌ Cancel"):
            st.session_state.confirm_delete = False
            st.experimental_rerun()

# ========== 加载 CSV 数据 ==========
if st.session_state.current_file:
    file_path = os.path.join(DATA_DIR, st.session_state.current_file)
    df = pd.read_csv(file_path)
    st.subheader(f"📄 Loaded File: {st.session_state.current_file}")
    st.dataframe(df.head())
else:
    st.warning("Please select or upload a CSV file first.")
    st.stop()

# ========== 图形参数 ==========
st.sidebar.header("🧠 Graph Settings")
from_col = st.sidebar.selectbox("From column", df.columns)
to_col = st.sidebar.selectbox("To column", df.columns)
level_col = st.sidebar.selectbox("Optional Level column (for sorting)", [None] + list(df.columns))

# ========== 图形可视化 ==========
st.header("📊 Graph Visualization")

try:
    agg = df.groupby([from_col, to_col]).size().reset_index(name="count")

    # ✅ 修复 AttributeError (排序安全)
    if level_col:
        sort_by = [level_col] if isinstance(level_col, str) else level_col
        try:
            last_to = str(agg.sort_values(by=sort_by).iloc[-1][to_col])
        except Exception:
            last_to = None
    else:
        last_to = None

    # 创建网络图
    net = Network(height="650px", width="100%", bgcolor="#FFFFFF", font_color="black", directed=True)

    # 添加节点和边
    for _, row in agg.iterrows():
        net.add_node(row[from_col], label=row[from_col])
        net.add_node(row[to_col], label=row[to_col])
        net.add_edge(row[from_col], row[to_col], title=f"Count: {row['count']}")

    if last_to:
        net.add_node(last_to, color="red", shape="star", size=25)

    net.repulsion(node_distance=180, spring_length=200)
    net.save_graph("graph.html")

    components.html(open("graph.html", "r", encoding="utf-8").read(), height=700)

except Exception as e:
    st.error(f"Graph generation failed: {e}")
