import streamlit as st
import pandas as pd

# ----------------------------------------------------
# 1. Page Config
# ----------------------------------------------------
st.set_page_config(
    page_title="Project Supplier Allocation Comparator",
    page_icon="⚖️",
    layout="wide"
)

st.title("⚖️ Project Supplier Allocation Comparator")
st.caption("Upload a single dataset containing records from two projects to compare supplier distribution and shares.")
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
            df = pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"Error loading file: {e}")
        st.stop()

    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Column Mapping")

    all_cols = list(df.columns)

    # Guess default columns if available
    def get_default_index(candidates, col_list):
        for candidate in candidates:
            for idx, col in enumerate(col_list):
                if candidate.lower() in col.lower():
                    return idx
        return 0

    proj_def_idx = get_default_index(["project", "study", "job"], all_cols)
    supp_def_idx = get_default_index(["supplier", "vendor", "panel", "source"], all_cols)
    status_def_idx = get_default_index(["status", "disposition"], all_cols)

    project_col = st.sidebar.selectbox("Project Identifier Column:", all_cols, index=proj_def_idx)
    supplier_col = st.sidebar.selectbox("Supplier / Vendor Column:", all_cols, index=supp_def_idx)

    # Optional complete status filter
    filter_completes = st.sidebar.checkbox("Filter by Complete Status?", value=False)
    if filter_completes:
        status_col = st.sidebar.selectbox("Status Column:", all_cols, index=status_def_idx)
        available_statuses = sorted(df[status_col].dropna().astype(str).unique())
        selected_status = st.sidebar.multiselect("Select 'Complete' statuses to keep:", available_statuses)
        if selected_status:
            df = df[df[status_col].astype(str).isin(selected_status)]

    # Clean missing identifiers
    df = df.dropna(subset=[project_col, supplier_col]).copy()
    df[project_col] = df[project_col].astype(str).str.strip()
    df[supplier_col] = df[supplier_col].astype(str).str.strip()

    available_projects = sorted(df[project_col].unique())

    if len(available_projects) < 2:
        st.warning(f"Found {len(available_projects)} unique project(s) in `{project_col}`. At least 2 projects are required for comparison.")
        st.stop()

    # ----------------------------------------------------
    # 3. Project Selector
    # ----------------------------------------------------
    st.sidebar.markdown("---")
    st.sidebar.header("🎯 Project Selection")

    col_proj_a = available_projects[0]
    col_proj_b = available_projects[1]

    proj_a = st.sidebar.selectbox("Baseline Project (Project A):", available_projects, index=0)
    proj_b = st.sidebar.selectbox(
        "Comparison Project (Project B):",
        available_projects,
        index=1 if proj_a != available_projects[1] else (0 if len(available_projects) > 1 else 0)
    )

    if proj_a == proj_b:
        st.warning("Please pick two distinct projects to compare.")
        st.stop()

    # Subset datasets
    df_a = df[df[project_col] == proj_a]
    df_b = df[df[project_col] == proj_b]

    tot_a = len(df_a)
    tot_b = len(df_b)

    # ----------------------------------------------------
    # 4. KPI Top Metrics
    # ----------------------------------------------------
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric(f"{proj_a} Total", f"{tot_a:,}")
    with k2:
        st.metric(f"{proj_b} Total", f"{tot_b:,}")
    with k3:
        st.metric("Total Records Analyzed", f"{tot_a + tot_b:,}")
    with k4:
        delta_records = tot_b - tot_a
        st.metric("Sample Size Difference", f"{abs(delta_records):,}", f"{delta_records:+} B vs A")

    st.markdown("---")

    # ----------------------------------------------------
    # 5. Allocation Comparison Engine
    # ----------------------------------------------------
    st.subheader(f"📊 Allocation Breakdown: {proj_a} vs {proj_b}")

    # Aggregate counts
    counts_a = df_a[supplier_col].value_counts()
    counts_b = df_b[supplier_col].value_counts()

    # Combine all unique suppliers across both projects
    all_suppliers = sorted(list(set(counts_a.index).union(set(counts_b.index))))

    comparison_data = []
    for supp in all_suppliers:
        n_a = int(counts_a.get(supp, 0))
        n_b = int(counts_b.get(supp, 0))

        pct_a = (n_a / tot_a * 100) if tot_a > 0 else 0.0
        pct_b = (n_b / tot_b * 100) if tot_b > 0 else 0.0
        pct_shift = pct_b - pct_a

        shift_flag = "🔺" if pct_shift > 0.5 else ("🔻" if pct_shift < -0.5 else "➖")

        comparison_data.append({
            "Supplier": supp,
            f"{proj_a} (N)": n_a,
            f"{proj_a} Share (%)": round(pct_a, 2),
            f"{proj_b} (N)": n_b,
            f"{proj_b} Share (%)": round(pct_b, 2),
            "Share Variance (B - A)": round(pct_shift, 2),
            "Direction": f"{shift_flag} {pct_shift:+.2f}%"
        })

    comp_df = pd.DataFrame(comparison_data).sort_values(by=f"{proj_a} (N)", ascending=False)

    # Display styled summary table
    st.dataframe(
        comp_df,
        column_config={
            f"{proj_a} Share (%)": st.column_config.NumberColumn(format="%.2f%%"),
            f"{proj_b} Share (%)": st.column_config.NumberColumn(format="%.2f%%"),
            "Share Variance (B - A)": st.column_config.NumberColumn(format="%+.2f%%"),
        },
        use_container_width=True,
        hide_index=True
    )

    # ----------------------------------------------------
    # 6. Share Comparison Chart
    # ----------------------------------------------------
    st.markdown("---")
    st.subheader("📈 Allocation Share Comparison (%)")

    chart_df = comp_df.set_index("Supplier")[[f"{proj_a} Share (%)", f"{proj_b} Share (%)"]]
    st.bar_chart(chart_df)

    # ----------------------------------------------------
    # 7. Discrepancy & Coverage Alert Box
    # ----------------------------------------------------
    only_in_a = [s for s in all_suppliers if counts_a.get(s, 0) > 0 and counts_b.get(s, 0) == 0]
    only_in_b = [s for s in all_suppliers if counts_b.get(s, 0) > 0 and counts_a.get(s, 0) == 0]

    if only_in_a or only_in_b:
        with st.expander("⚠️ Supplier Overlap & Coverage Notes", expanded=True):
            if only_in_a:
                st.write(f"- **Only used in {proj_a}**: {', '.join(only_in_a)}")
            if only_in_b:
                st.write(f"- **Only used in {proj_b}**: {', '.join(only_in_b)}")

else:
    st.info("👈 Upload your data file (CSV or Excel) in the sidebar to begin comparison.")