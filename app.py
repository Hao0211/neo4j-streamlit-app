import streamlit as st
import pandas as pd
import os
from datetime import datetime

# -------------------------------
# 页面基本设置
# -------------------------------
st.set_page_config(page_title="Transaction Graph Viewer", layout="wide")

st.title("💹 Transaction Graph Viewer")

UPLOAD_DIR = "uploaded_csvs"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# -------------------------------
# 上传 CSV 文件
# -------------------------------
st.sidebar.header("📤 Upload CSV File")
uploaded_file = st.sidebar.file_uploader("Choose a CSV file", type=["csv"])

if uploaded_file:
    file_path = os.path.join(UPLOAD_DIR, uploaded_file.name)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    st.sidebar.success(f"✅ Uploaded: {uploaded_file.name}")
    st.sidebar.info("File saved and shared successfully.")

# -------------------------------
# 删除文件功能
# -------------------------------
st.sidebar.header("🗑️ Manage Uploaded Files")

existing_files = [f for f in os.listdir(UPLOAD_DIR) if f.endswith(".csv")]

if existing_files:
    selected_file_to_delete = st.sidebar.selectbox("Select a file to delete", existing_files)
    if st.sidebar.button("Delete Selected File"):
        os.remove(os.path.join(UPLOAD_DIR, selected_file_to_delete))
        st.sidebar.success(f"🗑️ Deleted: {selected_file_to_delete}")
else:
    st.sidebar.info("No uploaded files yet.")

# -------------------------------
# 显示所有上传文件（按时间排序）
# -------------------------------
st.header("📂 Uploaded CSV Files")

csv_files = [f for f in os.listdir(UPLOAD_DIR) if f.endswith(".csv")]

if csv_files:
    # 获取文件的上传时间并排序（最新在最上方）
    file_info = []
    for f in csv_files:
        file_path = os.path.join(UPLOAD_DIR, f)
        upload_time = datetime.fromtimestamp(os.path.getmtime(file_path))
        file_info.append((f, upload_time))
    # 按时间倒序排列
    sorted_files = sorted(file_info, key=lambda x: x[1], reverse=True)

    # 仅显示文件名
    sorted_file_names = [f[0] for f in sorted_files]

    selected_csv = st.selectbox("Select a CSV to view", sorted_file_names)
    csv_path = os.path.join(UPLOAD_DIR, selected_csv)

    # 显示选中文件的上传时间
    selected_time = dict(sorted_files)[selected_csv]
    st.caption(f"🕒 Uploaded on: {selected_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # 显示 CSV 内容
    try:
        df = pd.read_csv(csv_path)
        st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.error(f"Error reading CSV: {e}")
else:
    st.info("No CSV files available yet. Upload one using the sidebar.")
