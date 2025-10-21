import streamlit as st
import pandas as pd
import requests
from pyvis.network import Network
import streamlit.components.v1 as components

# ======================================================
# ⚙️ GitHub Repo 配置
# ======================================================
GITHUB_USER = "Hao0211"
GITHUB_REPO = "neo4j-streamlit-app"
DATA_FOLDER = "data"
BRANCH = "main"

# ======================================================
# 🔄 从 GitHub 获取文件列表与数据
# ======================================================
@st.cache_data(ttl=300)
def list_github_files():
    """列出 GitHub data/ 目录下所有 CSV 文件"""
    api_url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{DATA_FOLDER}?ref={BRANCH}"
    r = requests.get(api_url)
    if r.status_code != 200:
        st.error("❌ 无法读取 GitHub 文件列表，请确认仓库是 public 并存在 data 文件夹。")
        return []
    return [item["name"] for item in r.json() if item["name"].endswith(".csv")]

@st.cache_data(ttl=300)
def load_github_csv(filename):
    """从 GitHub raw 链接读取 CSV 内容"""
    raw_url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{BRANCH}/{DATA_FOLDER}/{filename}"
    try:
        df = pd.read_csv(raw_url)
        return df
    except Exception as e:
        st.error(f"❌ 无法读取 CSV 文件: {e}")
        return pd.DataFrame()

# ======================================================
# 🏠 Streamlit 主程序
# ======================================================
st.set_page_config(page_title="Neo4j Streamlit Graph", layout="wide")
st.title("📊 Neo4j Streamlit Graph Viewer")

files = list_github_files()
if not files:
    st.warning("⚠️ 还没有上传 CSV 文件，请先在 GitHub 的 data 文件夹上传。")
    st.stop()

selected_file = st.selectbox("📂 选择要查看的 CSV 文件", files)
st.write(f"✅ 当前选择：`{selected_file}`")

# 加载 CSV
df = load_github_csv(selected_file)
if df.empty:
    st.warning("⚠️ CSV 文件为空或读取失败。")
    st.stop()

st.subheader("📋 数据预览")
st.dataframe(df.head(10), use_container_width=True)

# ======================================================
# 🕸️ 图形化视图（PyVis）
# ======================================================
st.header("🕸️ Transaction Graph Visualization")

# 检查是否有 Source / Target 字段
required_cols = {"Source", "Target"}
if not required_cols.issubset(df.columns):
    st.error("❌ CSV 必须包含 'Source' 和 'Target' 字段。")
    st.stop()

# 初始化网络图
net = Network(height="650px", width="100%", bgcolor="#FFFFFF", directed=True)

# 添加节点与连线
for _, row in df.iterrows():
    source = str(row["Source"])
    target = str(row["Target"])
    amount = row["Amount"] if "Amount" in df.columns else None

    net.add_node(source, label=source, color="#00AEEF")
    net.add_node(target, label=target, color="#FF7F0E")
    if amount:
        net.add_edge(source, target, title=f"Amount: {amount}")
    else:
        net.add_edge(source, target, title="Transaction")

# 生成 HTML 内容（不写入文件）
html_str = net.generate_html()

# 在 Streamlit 显示
components.html(html_str, height=700, scrolling=True)

# ======================================================
# ℹ️ 使用说明
# ======================================================
with st.expander("📘 使用说明"):
    st.markdown("""
    1. 打开 [你的 GitHub 仓库](https://github.com/Hao0211/neo4j-streamlit-app)
    2. 创建一个文件夹 `data/`
    3. 上传 CSV 文件（必须包含 `Source` 与 `Target` 两列，可选 `Amount`）
    4. 回到此页面刷新，即可选择新文件并查看关系图 🌐
    """)

st.success("✅ 应用已成功加载！可从 GitHub data 目录选择文件查看图表。")
