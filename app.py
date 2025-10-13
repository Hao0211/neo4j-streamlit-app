import streamlit as st
import pandas as pd
import os
from datetime import datetime
from pyvis.network import Network
import tempfile

st.set_page_config(page_title="Transaction Graph Viewer", layout="wide")

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

st.title("💹 Transaction Graph Viewer")

# ========== 上传区 ==========
with st.sidebar:
    st.header("📤 Upload CSV")
    uploaded_file = st.file_uploader(
        "Drag and drop file here", 
        type=["csv"],
        label_visibility="collapsed"
    )
    if uploaded_file is not None:
        file_path = os.path.join(UPLOAD_DIR, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.success(f"✅ Saved: {uploaded_file.name}")

# ========== 管理文件区 ==========
with st.sidebar:
    st.header("📂 Manage Files")

    files = [f for f in os.listdir(UPLOAD_DIR) if f.endswith(".csv")]
    selected_file = st.selectbox("Select file", files if files else ["(no files)"])

    if "delete_confirm" not in st.session_state:
        st.session_state.delete_confirm = False

    # 删除文件按钮
    if st.button("🗑️ Delete selected file", use_container_width=True):
        if selected_file and selected_file != "(no files)":
            st.session_state.delete_confirm = True

    # 弹出确认删除 modal
    if st.session_state.delete_confirm:
        with st.modal("⚠️ Confirm Deletion"):
            st.warning(f"Are you sure you want to delete **{selected_file}**?")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Yes, delete it"):
                    file_path = os.path.join(UPLOAD_DIR, selected_file)
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        st.success(f"{selected_file} deleted successfully!")
                    st.session_state.delete_confirm = False
                    st.session_state.pop("df", None)
                    st.rerun()
            with col2:
                if st.button("❌ Cancel"):
                    st.session_state.delete_confirm = False
                    st.rerun()

# ========== 载入 CSV ==========
if selected_file and selected_file != "(no files)":
    csv_path = os.path.join(UPLOAD_DIR, selected_file)
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path)
        st.session_state.df = df
    elif "df" in st.session_state:
        df = st.session_state.df
    else:
        df = None
else:
    df = None

# ========== 图表过滤条件 ==========
if df is not None:
    with st.sidebar:
        st.header("🔍 Graph Filters")

        tracked_list = sorted(df["tracked_username"].dropna().unique().tolist())
        tracked_selected = st.selectbox("Filter · tracked_username", tracked_list)

        min_date = pd.to_datetime(df["first_received_at"].min(), errors="coerce")
        max_date = pd.to_datetime(df["last_received_at"].max(), errors="coerce")

        start_date, end_date = st.date_input(
            "Select date range",
            [min_date.date() if not pd.isna(min_date) else datetime(2024, 1, 1),
             max_date.date() if not pd.isna(max_date) else datetime.today()]
        )

    # ========== 筛选数据 ==========
    filtered_df = df[
        (df["tracked_username"] == tracked_selected)
        & (pd.to_datetime(df["first_received_at"], errors="coerce") >= pd.to_datetime(start_date))
        & (pd.to_datetime(df["last_received_at"], errors="coerce") <= pd.to_datetime(end_date))
        & (df["relationship"] == "transfer")
    ]

    st.subheader(f"📊 {tracked_selected}'s Transaction Network")

    # ========== 构建图形 ==========
    net = Network(height="750px", width="100%", bgcolor="#F8FAFC", font_color="black", directed=True)
    net.barnes_hut()

    central_node = tracked_selected
    net.add_node(central_node, label=central_node, color="#2563EB", size=30)

    for _, row in filtered_df.iterrows():
        sender = row["from_username"]
        total_amt = row["total_amount_received"]
        txn_count = row["distinct_txn_count"]

        label = f"{total_amt:,.0f} ({txn_count})"
        net.add_node(sender, label=sender, color="#34D399", size=20)
        net.add_edge(sender, central_node, label=label, color="#9CA3AF")

    # ========== 显示图形 ==========
    with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp_file:
        net.save_graph(tmp_file.name)
        with open(tmp_file.name, "r", encoding="utf-8") as f:
            html_content = f.read()
        st.components.v1.html(html_content, height=750, scrolling=True)

else:
    st.info("Please upload a CSV file to begin.")
