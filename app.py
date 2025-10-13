import streamlit as st
import pandas as pd
from pathlib import Path
from pyvis.network import Network
from datetime import datetime, timedelta
import tempfile
import os

# ---------- Page config ----------
st.set_page_config(page_title="Transaction Graph Viewer", layout="wide")
st.title("💹 Transaction Graph Viewer")

# ---------- Upload dir ----------
UPLOAD_DIR = Path("uploaded_data")
UPLOAD_DIR.mkdir(exist_ok=True)

# ---------- Helpers ----------
def get_sorted_files():
    # return filenames sorted by modification time (newest first)
    files = [p for p in UPLOAD_DIR.glob("*.csv")]
    files_sorted = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
    return [p.name for p in files_sorted]

def safe_read_csv(path):
    try:
        return pd.read_csv(path)
    except Exception as e:
        st.error(f"Failed to read CSV: {e}")
        return None

def fmt_amount(v):
    try:
        v = float(v)
        if abs(v - round(v)) < 1e-9:
            return f"{int(round(v))}RP"
        return f"{v:,.2f}RP"
    except Exception:
        return str(v)

# ---------- Sidebar: upload ----------
st.sidebar.header("📤 Upload CSV")
uploaded_file = st.sidebar.file_uploader("Drag and drop or browse to upload CSV", type=["csv"], label_visibility="collapsed")
if uploaded_file is not None:
    dest = UPLOAD_DIR / uploaded_file.name
    with open(dest, "wb") as f:
        f.write(uploaded_file.getbuffer())
    st.sidebar.success(f"Saved: {uploaded_file.name}")
    # Set the uploaded file as selected and refresh UI
    st.session_state["selected_file"] = uploaded_file.name
    st.rerun()

# ---------- Sidebar: file management ----------
st.sidebar.header("📂 Manage files")
files = get_sorted_files()
if files:
    # keep selected filename in session_state so upload/delete sync works
    if "selected_file" not in st.session_state or st.session_state.get("selected_file") not in files:
        st.session_state["selected_file"] = files[0]

    selected_file = st.sidebar.selectbox("Select file", files, key="selected_file_selectbox")
    # Keep session state value in sync with selectbox so main area uses it
    st.session_state["selected_file"] = selected_file

    # Delete flow: set a pending confirm target
    if st.sidebar.button("🗑️ Delete selected file", use_container_width=True):
        st.session_state["confirm_delete_target"] = selected_file

    # If a delete target exists, show inline confirmation UI
    if st.session_state.get("confirm_delete_target"):
        target = st.session_state["confirm_delete_target"]
        st.sidebar.warning(f"Confirm delete: **{target}**")
        col1, col2 = st.sidebar.columns(2)
        with col1:
            if st.button("✅ Confirm Delete", key="confirm_delete"):
                path = UPLOAD_DIR / target
                try:
                    if path.exists():
                        path.unlink()
                        st.sidebar.success(f"Deleted {target}")
                    else:
                        st.sidebar.info(f"{target} not found.")
                except Exception as e:
                    st.sidebar.error(f"Failed to delete {target}: {e}")
                # cleanup state and refresh
                st.session_state.pop("confirm_delete_target", None)
                # clear selected_file if it was the deleted one
                if st.session_state.get("selected_file") == target:
                    st.session_state.pop("selected_file", None)
                st.rerun()
        with col2:
            if st.button("❌ Cancel", key="cancel_delete"):
                st.session_state.pop("confirm_delete_target", None)
                st.rerun()
else:
    st.sidebar.info("No uploaded CSV files yet.")

# ---------- Main area: load selected file ----------
st.header("📁 Uploaded CSV Files")
files = get_sorted_files()
if not files:
    st.info("No CSV files available. Upload one from the sidebar to begin.")
    st.stop()

# Ensure selected_file exists in session_state and in files
selected_filename = st.session_state.get("selected_file") or files[0]
if selected_filename not in files:
    selected_filename = files[0]
    st.session_state["selected_file"] = selected_filename

# Show selectbox in main area too (keeps synced)
selected_filename = st.selectbox("Select an uploaded CSV to load", files, index=files.index(selected_filename), key="main_selectbox")
# Sync to session_state
st.session_state["selected_file"] = selected_filename

csv_path = UPLOAD_DIR / selected_filename
df = safe_read_csv(csv_path)
if df is None:
    st.stop()

st.success(f"Loaded: {selected_filename}")
st.dataframe(df.head(8), use_container_width=True)

# ---------- Column name resolution ----------
col_map = {c.lower(): c for c in df.columns}
def colname(*candidates):
    for c in candidates:
        if c.lower() in col_map:
            return col_map[c.lower()]
    return None

tracked_col = colname("tracked_username")
from_col = colname("from_username")
to_col = colname("to_username")
total_amt_col = colname("total_amount_received", "total_amount", "amount", "total_received")
txn_count_col = colname("distinct_txn_count", "txn_count", "distinct_count", "count")
date_first_col = colname("first_received_at", "first_received", "first_date")
date_last_col = colname("last_received_at", "last_received", "last_date", "date")
relationship_col = colname("relationship")

required = []
for name, var in [("tracked_username", tracked_col), ("from_username", from_col),
                  ("to_username", to_col), ("total_amount_received", total_amt_col),
                  ("distinct_txn_count", txn_count_col)]:
    if var is None:
        required.append(name)
if required:
    st.error(f"CSV missing required columns: {', '.join(required)}.")
    st.stop()

# prefer last date if available
date_col = date_last_col or date_first_col
if date_col:
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

# ---------- Sidebar: graph filters ----------
st.sidebar.header("🔍 Graph Filters (per file)")

# tracked_username list (default to first)
tracked_values = sorted(df[tracked_col].dropna().astype(str).unique().tolist())
if not tracked_values:
    st.sidebar.error("No tracked_username values found.")
    st.stop()

# default index is 0 (first item)
default_idx = 0
if "tracked_select" not in st.session_state:
    st.session_state["tracked_select"] = tracked_values[default_idx]

# show selectbox and sync
selected_tracked = st.sidebar.selectbox("Filter · tracked_username", tracked_values, index=tracked_values.index(st.session_state["tracked_select"]))
st.session_state["tracked_select"] = selected_tracked

# Date range filter (if date column exists)
if date_col and df[date_col].notna().any():
    min_date = df[date_col].min().date()
    max_date = df[date_col].max().date()
    two_years_ago = datetime.today().date() - timedelta(days=730)
    default_start = max(two_years_ago, min_date)
    default_end = max_date
    date_range = st.sidebar.date_input("Select date range", [default_start, default_end], key="date_range")
    start_ts = pd.to_datetime(date_range[0])
    end_ts = pd.to_datetime(date_range[1]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
else:
    start_ts = None
    end_ts = None

# ---------- Filter dataframe ----------
filtered = df.copy()
# filter by tracked
filtered = filtered[filtered[tracked_col].astype(str) == str(selected_tracked)]
# optional relationship filter: only transfer
if relationship_col:
    filtered = filtered[filtered[relationship_col].astype(str).str.lower() == "transfer"]
# date filter
if start_ts is not None and end_ts is not None and date_col:
    filtered = filtered[(filtered[date_col] >= start_ts) & (filtered[date_col] <= end_ts)]

if filtered.empty:
    st.warning("No records match the selected filters.")
    st.stop()

# ---------- Aggregate (by level ordering if present) ----------
level_col = colname("level")
if level_col:
    filtered = filtered.sort_values(by=level_col)
agg_cols = [tracked_col, from_col, to_col]
agg = filtered.groupby(agg_cols, dropna=True, as_index=False).agg({
    total_amt_col: "sum",
    txn_count_col: "sum"
})

# ---------- Build PyVis graph ----------
st.subheader(f"Graph Visualization for '{selected_tracked}'")
net = Network(height="780px", width="100%", notebook=False, bgcolor="#FFFFFF", font_color="#000000", directed=True)
net.force_atlas_2based(gravity=-50, central_gravity=0.02, spring_length=150, spring_strength=0.05, damping=0.4)

nodes_added = set()
# Add edges from -> to with label "NNN RP (count)"
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

# ensure tracked node is present and prominent
if selected_tracked not in nodes_added:
    net.add_node(selected_tracked, label=selected_tracked, size=30, color="#FFD700")

# optionally connect last-level to tracked if not already present
if not agg.empty:
    last_to = str(agg.sort_values(by=(level_col if level_col else []).copy() or []).iloc[-1][to_col]) if level_col else None
    if last_to and last_to != selected_tracked:
        # add light edge
        net.add_edge(last_to, selected_tracked, label="", color="#BBBBBB")

# ---------- Render graph ----------
tmp_dir = tempfile.gettempdir()
html_path = os.path.join(tmp_dir, "graph.html")
net.write_html(html_path)
st.components.v1.html(Path(html_path).read_text(), height=790)
