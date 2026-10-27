import streamlit as st
import pandas as pd

# ----------------------------------------------------
# 1. Page Configuration & Layout
# ----------------------------------------------------
st.set_page_config(
    page_title="Project Allocation Comparator",
    page_icon="⚖️",
    layout="wide"
)

st.title("⚖️ Project Supplier Allocation Comparator")
st.caption("Compare supplier shares and volume between two waves/projects without horizontal scrolling.")
st.markdown("---")

# ----------------------------------------------------
# 2. File Upload & Ingestion
# ----------------------------------------------------
st.sidebar.header("📁 Ingestion")
uploaded_file = st.sidebar.file_uploader("Upload CSV or Excel file", type=["csv", "xlsx", "xls"])

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file, low_memory=False)
        else:
            excel_file = pd.ExcelFile(uploaded_file)
            selected_sheet = (
                st.sidebar.selectbox("Select Sheet:", excel_file.sheet_names)
                if len(excel_file.sheet_names) > 1
                else excel_file.sheet_names[0]
            )
            df = pd.read_excel(uploaded_file, sheet_name=selected_sheet)
    except Exception as e:
        st.error(f"Error loading file: {e}")
        st.stop()

    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Column Mapping")
    all_cols = list(df.columns)

    def get_default_index(candidates, col_list):
        for candidate in candidates:
            for idx, col in enumerate(col_list):
                if candidate.lower() in col.lower():
                    return idx
        return 0

    proj_def_idx = get_default_index(["project", "study", "job", "wave"], all_cols)
    # Prefer name over ID if present
    supp_def_idx = get_default_index(["supplier name", "vendor name", "panel name", "supplier", "vendor"], all_cols)
    status_def_idx = get_default_index(["status", "disposition"], all_cols)

    project_col = st.sidebar.selectbox("Project / Wave Column:", all_cols, index=proj_def_idx)
    supplier_col = st.sidebar.selectbox("Supplier Column (Pick Name if available):", all_cols, index=supp_def_idx)

    # Optional complete status filter
    filter_completes = st.sidebar.checkbox("Filter by Complete Status?", value=False)
    if filter_completes:
        status_col = st.sidebar.selectbox("Status Column:", all_cols, index=status_def_idx)
        available_statuses = sorted(df[status_col].dropna().astype(str).unique())
        selected_status = st.sidebar.multiselect("Select 'Complete' statuses to keep:", available_statuses)
        if selected_status:
            df = df[df[status_col].astype(str).isin(selected_status)]

    # Clean identifiers
    df = df.dropna(subset=[project_col, supplier_col]).copy()
    df[project_col] = df[project_col].astype(str).str.strip()
    df[supplier_col] = df[supplier_col].astype(str).str.strip()

    available_projects = sorted(df[project_col].unique())

    if len(available_projects) < 2:
        st.warning(f"Found {len(available_projects)} unique project(s) in `{project_col}`. At least 2 projects are required.")
        st.stop()

    # ----------------------------------------------------
    # 3. Project Selection
    # ----------------------------------------------------
    st.sidebar.markdown("---")
    st.sidebar.header("🎯 Wave / Project Selection")

    proj_a = st.sidebar.selectbox("Baseline (Wave A):", available_projects, index=0)
    proj_b = st.sidebar.selectbox(
        "Comparison (Wave B):",
        available_projects,
        index=1 if proj_a != available_projects[1] else (0 if len(available_projects) > 1 else 0)
    )

    if proj_a == proj_b:
        st.warning("Please choose two different projects to compare.")
        st.stop()

    # Optional shorthand labels so column headers stay tiny
    use_custom_labels = st.sidebar.checkbox("Use short column labels (keeps table narrow)", value=True)
    if use_custom_labels:
        col_name_a = st.sidebar.text_input("Short Name for Wave A:", value="Wave A")
        col_name_b = st.sidebar.text_input("Short Name for Wave B:", value="Wave B")
    else:
        col_name_a = proj_a[:20] + "..." if len(proj_a) > 20 else proj_a
        col_name_b = proj_b[:20] + "..." if len(proj_b) > 20 else proj_b

    # Subset datasets
    df_a = df[df[project_col] == proj_a]
    df_b = df[df[project_col] == proj_b]
    tot_a = len(df_a)
    tot_b = len(df_b)

    # ----------------------------------------------------
    # 4. KPI Top Summary
    # ----------------------------------------------------
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric(f"{col_name_a} Total (N)", f"{tot_a:,}")
        st.caption(f"📌 *{proj_a}*")
    with k2:
        st.metric(f"{col_name_b} Total (N)", f"{tot_b:,}")
        st.caption(f"📌 *{proj_b}*")
    with k3:
        st.metric("Total Completes", f"{tot_a + tot_b:,}")
    with k4:
        delta_records = tot_b - tot_a
        st.metric("Sample Variance", f"{abs(delta_records):,}", f"{delta_records:+} {col_name_b} vs {col_name_a}")

    st.markdown("---")

    # ----------------------------------------------------
    # 5. Table View Display Controls
    # ----------------------------------------------------
    c_title, c_toggle = st.columns([2, 1])
    with c_title:
        st.subheader("📊 Supplier Allocation Comparison")
    with c_toggle:
        metric_view = st.radio(
            "Display Metrics:",
            options=["Share Only (%)", "Both (N & %)", "Counts Only (N)"],
            index=0,  # Default to % only so it fits on 1 screen with zero scrolling
            horizontal=True
        )

    # Calculate allocations
    counts_a = df_a[supplier_col].value_counts()
    counts_b = df_b[supplier_col].value_counts()
    all_suppliers = sorted(list(set(counts_a.index).union(set(counts_b.index))))

    rows = []
    for supp in all_suppliers:
        n_a = int(counts_a.get(supp, 0))
        n_b = int(counts_b.get(supp, 0))

        pct_a = (n_a / tot_a * 100) if tot_a > 0 else 0.0
        pct_b = (n_b / tot_b * 100) if tot_b > 0 else 0.0
        variance = pct_b - pct_a

        shift_flag = "🔺" if variance > 0.5 else ("🔻" if variance < -0.5 else "➖")

        row = {"Supplier": supp}

        if metric_view in ["Both (N & %)", "Counts Only (N)"]:
            row[f"{col_name_a} (N)"] = n_a
            row[f"{col_name_b} (N)"] = n_b

        if metric_view in ["Both (N & %)", "Share Only (%)"]:
            row[f"{col_name_a} (%)"] = pct_a
            row[f"{col_name_b} (%)"] = pct_b
            row["Variance (B - A)"] = variance
            row["Trend"] = f"{shift_flag} {variance:+.1f}%"

        rows.append(row)

    comp_df = pd.DataFrame(rows)

    # Sort descending by wave A volume or share
    sort_target = f"{col_name_a} (%)" if f"{col_name_a} (%)" in comp_df.columns else f"{col_name_a} (N)"
    comp_df = comp_df.sort_values(by=sort_target, ascending=False)

    # Column configuration for compact auto-formatting
    col_configs = {
        "Supplier": st.column_config.TextColumn("Supplier", width="medium"),
    }
    if f"{col_name_a} (%)" in comp_df.columns:
        col_configs[f"{col_name_a} (%)"] = st.column_config.NumberColumn(f"{col_name_a} (%)", format="%.2f%%")
        col_configs[f"{col_name_b} (%)"] = st.column_config.NumberColumn(f"{col_name_b} (%)", format="%.2f%%")
        col_configs["Variance (B - A)"] = st.column_config.NumberColumn("Variance", format="%+.2f%%")

    # Render table fitting container width
    st.dataframe(
        comp_df,
        column_config=col_configs,
        use_container_width=True,
        hide_index=True
    )

    # ----------------------------------------------------
    # 6. Share Comparison Bar Chart
    # ----------------------------------------------------
    st.markdown("---")
    st.subheader("📈 Visual Allocation Spread")

    chart_prep = []
    for supp in all_suppliers:
        pct_a = (counts_a.get(supp, 0) / tot_a * 100) if tot_a > 0 else 0.0
        pct_b = (counts_b.get(supp, 0) / tot_b * 100) if tot_b > 0 else 0.0
        chart_prep.append({
            "Supplier": supp,
            f"{col_name_a} (%)": round(pct_a, 2),
            f"{col_name_b} (%)": round(pct_b, 2),
        })

    chart_df = pd.DataFrame(chart_prep).set_index("Supplier")
    st.bar_chart(chart_df)

    # ----------------------------------------------------
    # 7. Unmatched Suppliers Alert
    # ----------------------------------------------------
    only_in_a = [s for s in all_suppliers if counts_a.get(s, 0) > 0 and counts_b.get(s, 0) == 0]
    only_in_b = [s for s in all_suppliers if counts_b.get(s, 0) > 0 and counts_a.get(s, 0) == 0]

    if only_in_a or only_in_b:
        with st.expander("⚠️ Supplier Exclusivity Alert", expanded=False):
            if only_in_a:
                st.write(f"- **Only in {col_name_a}**: {', '.join(only_in_a)}")
            if only_in_b:
                st.write(f"- **Only in {col_name_b}**: {', '.join(only_in_b)}")

else:
    st.info("👈 Upload your tracker Excel or CSV file in the sidebar to begin.")
