# -------------------------------
# 绘制 PyVis 图表
# -------------------------------
st.subheader(f"Graph Visualization for '{selected_tracked}'")

net = Network(height="780px", width="100%", bgcolor="#FFFFFF", directed=True)
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
        net.add_node(from_user, label=from_user, size=18, color="#87CEFA")
        nodes_added.add(from_user)
    if to_user not in nodes_added:
        net.add_node(to_user, label=to_user, size=18, color="#90EE90")
        nodes_added.add(to_user)

    # 让线条宽阔
    edge_width = max(2, min(10, total_amt / 10000))
    net.add_edge(
        from_user,
        to_user,
        label=label,
        title=f"{from_user} → {to_user}\n{label}",
        color="rgba(80,80,80,0.85)",
        width=edge_width
    )

# tracked_username 高亮
net.add_node(selected_tracked, label=selected_tracked, size=30, color="#FFD700")

tmp_dir = tempfile.gettempdir()
html_path = os.path.join(tmp_dir, "graph.html")
net.write_html(html_path)
st.components.v1.html(Path(html_path).read_text(), height=790)
