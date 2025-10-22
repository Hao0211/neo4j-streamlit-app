import streamlit as st
import requests
import pandas as pd
from pyvis.network import Network
import os

# 安全导入 BeautifulSoup
try:
    from bs4 import BeautifulSoup
except ImportError:
    st.error("缺少 BeautifulSoup4，请在 requirements.txt 中添加 beautifulsoup4 并重新部署。")

# ----------------------------------------
# 配置
# ----------------------------------------
GITHUB_USERNAME = "Hao0211"
GITHUB_REPO = "neo4j-streamlit-app"
BRANCH = "main"

# ----------------------------------------
# 获取仓库文件列表
# ----------------------------------------
def get_repo_files():
    api_url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/"
    try:
        response = requests.get(api_url)
        if response.status_code == 200:
            data = response.json()
            return [item["name"] for item in data if item["type"] == "file"]
        else:
            raise Exception("GitHub API 无法访问")
    except Exception as e:
        st.warning("⚠️ GitHub API 无法访问，尝试使用网页解析模式...")
        html_url = f"https://github.com/{GITHUB_USERNAME}/{GITHUB_REPO}/tree/{BRANCH}"
        response = requests.get(html_url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            return [a.text.strip() for a in soup.select("a.js-navigation-open.Link--primary")]
        else:
            st.error("❌ 无法访问 GitHub 仓库网页，请检查网络或仓库设置。")
            return []

# ----------------------------------------
# 显示文件内容
# ----------------------------------------
def show_file_content(file_name):
    file_url = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPO}/{BRANCH}/{file_name}"
    response = requests.get(file_url)
    if response.status_code == 200:
        st.code(response.text, language="python")
    else:
        st.error(f"无法读取文件：{file_name}")

# ----------------------------------------
# Streamlit 页面布局
# ----------------------------------------
st.set_page_config(page_title="📈 GitHub 文件浏览器", layout="wide")

st.title("📘 GitHub 文件可视化浏览器")

files = get_repo_files()
if files:
    selected_file = st.selectbox("选择要查看的文件：", files)
    if selected_file:
        show_file_content(selected_file)
else:
    st.error("未找到任何文件，请确认仓库名称和分支是否正确。")
