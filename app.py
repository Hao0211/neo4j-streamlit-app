import streamlit as st
import pandas as pd
import os

# -------------------------------
# 基本设置
# -------------------------------
st.set_page_config(page_title="Transaction Graph Viewer", layout="wide")

st.title("💹 Transaction Graph Viewer")

UPLOAD_DIR = "uploaded_csvs"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# -------------------------------
# 上传 CSV
# -------------------------------
st.sidebar.header("📤 Upload CSV File")
uploaded_file = st.sidebar.file_uploader("Choose a CSV file", type=["csv"])

if uploaded_file:
    file_path = os.path.join(UPLOAD_DIR, uploaded_file.name)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    st.sidebar.success(f"✅ Uploaded: {uploaded_file.name}")

# -------------------------------
# 删除功能
# -------------------------------
st.sidebar.header("🗑️ Manage Uploaded Files")

existing_files = os.listdir(UPLOAD_DIR)
if existing_files:
    selected_file_to_delete = st.sidebar.selectbox("Select a file to delete", existing_files)
    if st.sidebar.button("Delete Selected File"):
        os.remove(os.path.join(UPLOAD_DIR, selected_file_to_delete))
        st.sidebar.success(f"🗑️ Deleted: {selected_file_to_delete}")
else:
    st.sidebar.info("No uploaded files yet.")

# -------------------------------
# 显示所有上传的 CSV
# -------------------------------
st.header("📂 Uploaded CSV Files")

csv_files = [f for f in os.listdir(UPLOAD_DIR) if f.endswith(".csv")]

if csv_files:
    selected_csv = st.selectbox("Select a CSV to view", csv_files)
    csv_path = os.path.join(UPLOAD_DIR, selected_csv)

    try:
        df = pd.read_csv(csv_path)
        st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.error(f"Error reading CSV: {e}")

else:
    st.info("No CSV files available yet. Upload one using the sidebar.")
