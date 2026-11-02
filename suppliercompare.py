import streamlit as st
import pandas as pd
import re

# ----------------------------------------------------
# 1. Page Configuration & Layout
# ----------------------------------------------------
st.set_page_config(
    page_title="Wave Allocation Comparator",
    page_icon="⚖️",
    layout="wide"
)

st.title("⚖️ Wave & Supplier Allocation Comparator")
st.caption("Upload tracking files to compare supplier blends across any two waves or project segments.")
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

    proj_def_idx = get_default_index(["project", "study", "crm", "job", "wave"], all_cols)
    supp_def_idx = get_default_index(["supplier name", "vendor name", "panel name", "supplier", "vendor"], all_cols)
    status_def_idx = get_default_index(["status", "disposition", "resp_status"], all_cols)

    project_col = st.sidebar.selectbox("Project / Wave Column:", all_cols, index=proj_def_idx)
    supplier_col = st.sidebar.selectbox("Supplier Column (Name or ID):", all_cols, index=supp_def_idx)

    # Optional complete status filter
    filter_completes = st.sidebar.checkbox("Filter by Complete Status (e.g. 21)?", value=True)
    if filter_completes:
        status_col = st.sidebar.selectbox("Status Column:", all_cols, index=status_def_idx)
        available_statuses = sorted([str(s).split('.')[0].strip() for s in df[status_col].dropna().unique()])
        default_status = [s for s in available_statuses if s.lower() in ['21', 'complete', 'completed']]
        selected_status = st.sidebar.multiselect(
            "Select Status to keep:", 
            options=available_statuses,
            default=default_status if default_status else None
        )
        if selected_status:
            clean_status_col = df[status_col].astype(str).str.split('.').str[0].str.strip()
            df = df[clean_status_col.isin(selected_status)].copy()

    # Clean identifiers
    df = df.dropna(subset=[project_col, supplier_col]).copy()
    df[project_col] = df[project_col].astype(str).str.strip()
    df[supplier_col] = df[supplier_col].astype(str).str.strip()

    unique_projects = sorted(df[project_col].unique())

    # ----------------------------------------------------
    # 3. Flexible Wave Grouping (Universal for Any File)
    # ----------------------------------------------------
    st.sidebar.markdown("---")
    st.sidebar.header("🎯 Wave / Study Grouping")

    group_mode = st.sidebar.radio(
        "Wave Definition Method:",
        ["Select Project Segments (Multiselect)", "Match by Keyword / CRM ID"],
        index=0
    )

    if group_mode == "Select Project Segments (Multiselect)":
        label_prev = st.sidebar.text_input("Baseline Wave Name:", value="Wave Baseline")
        # Defaults to the first item
        projects_a = st.sidebar.multiselect(
            "Select project(s) for Baseline Wave:", 
            options=unique_projects,
            default=[unique_projects[0]] if unique_projects else []
        )

        label_recent = st.sidebar.text_input("Comparison Wave Name:", value="Wave Comparison")
        # Defaults to remaining items if available
        default_b = [unique_projects[1]] if len(unique_projects) > 1 else []
        projects_b = st.sidebar.multiselect(
            "Select project(s) for Comparison Wave:", 
            options=unique_projects,
            default=default_b
        )
    else:
        label_prev = st.sidebar.text_input("Baseline Keyword / CRM:", value="108685")
        label_recent = st.sidebar.text_input("Comparison Keyword / CRM:", value="124897")

        projects_b = [p for p in unique_projects if label_recent.lower() in p.lower()]
        projects_a = [p for p in unique_projects if label_prev.lower() in p.lower() and p not in projects_b]

        st.sidebar.caption(f"**'{label_prev}' matched:** {len(projects_a)} segment(s)")
        st.sidebar.caption(f"**'{label_recent}' matched:** {len(projects_b)} segment(s)")

    if not projects_a or not projects_b:
        st.warning("Please ensure at least one project/segment is selected for both waves.")
        st.stop()

    # ----------------------------------------------------
    # 4. Supplier 3-Group Blend Mapping
    # ----------------------------------------------------
    def map_to_group(supp_name):
        s = str(supp_name).lower()
        if "prime insights" in s:
            return "Group 1 (Prime Insights)"
        elif any(f in s for f in ["fusion", "social loop"]):
            return "Group 2 (Fusion & Social Loop)"
        else:
            return "Group 3 (Group MP / Marketplace)"

    df['Blend Group'] = df[supplier_col].apply(map_to_group)

    df_prev = df[df[project_col].isin(projects_a)]
    df_recent = df[df[project_col].isin(projects_b)]

    tot_prev = len(df_prev)
    tot_recent = len(df_recent)

    # ----------------------------------------------------
    # 5. KPI Cards
    # ----------------------------------------------------
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric(f"{label_prev} Total (N)", f"{tot_prev:,}")
        st.caption(f"{len(projects_a)} segment(s)")
    with k2:
        st.metric(f"{label_recent} Total (N)", f"{tot_recent:,}")
        st.caption(f"{len(projects_b)} segment(s)")
    with k3:
        st.metric("Total Records Analyzed", f"{tot_prev + tot_recent:,}")
    with k4:
        delta_records = tot_recent - tot_prev
        st.metric("Sample Variance", f"{abs(delta_records):,}", f"{delta_records:+} Comparison vs Baseline")

    st.markdown("---")

    # ----------------------------------------------------
    # 6. 3-Group Blend Summary Table
    # ----------------------------------------------------
    st.subheader(f"🏢 3-Group Blend Summary: {label_prev} vs {label_recent}")
    st.caption("Consolidated rollup matching standard allocation rules: Group 1, Group 2, and Group 3.")

    group_order = [
        "Group 1 (Prime Insights)",
        "Group 2 (Fusion & Social Loop)",
        "Group 3 (Group MP / Marketplace)"
    ]

    grp_counts_prev = df_prev['Blend Group'].value_counts()
    grp_counts_recent = df_recent['Blend Group'].value_counts()

    group_rows = []
    for g in group_order:
        g_n_prev = int(grp_counts_prev.get(g, 0))
        g_n_rec = int(grp_counts_recent.get(g, 0))

        g_pct_prev = (g_n_prev / tot_prev * 100) if tot_prev > 0 else 0.0
        g_pct_rec = (g_n_rec / tot_recent * 100) if tot_recent > 0 else 0.0
        g_diff = g_pct_rec - g_pct_prev

        g_flag = "🔺" if g_diff > 0.5 else ("🔻" if g_diff < -0.5 else "➖")

        group_rows.append({
            "Supplier Group": g,
            f"{label_prev} (N)": g_n_prev,
            f"{label_prev} (%)": g_pct_prev,
            f"{label_recent} (N)": g_n_rec,
            f"{label_recent} (%)": g_pct_rec,
            "Shift": g_diff,
            "Direction": f"{g_flag} {g_diff:+.1f}%"
        })

    group_df = pd.DataFrame(group_rows)

    st.dataframe(
        group_df,
        column_config={
            f"{label_prev} (%)": st.column_config.NumberColumn(format="%.2f%%"),
            f"{label_recent} (%)": st.column_config.NumberColumn(format="%.2f%%"),
            "Shift": st.column_config.NumberColumn(format="%+.2f%%"),
        },
        use_container_width=True,
        hide_index=True
    )

    st.markdown("---")

    # ----------------------------------------------------
    # 7. Detailed Individual Supplier Table
    # ----------------------------------------------------
    c_title, c_toggle = st.columns([2, 1])
    with c_title:
        st.subheader("📋 Granular Supplier Breakdown")
    with c_toggle:
        metric_view = st.radio(
            "Display Metrics:",
            options=["Share Only (%)", "Both (N & %)", "Counts Only (N)"],
            index=0,
            horizontal=True
        )

    counts_prev = df_prev[supplier_col].value_counts()
    counts_recent = df_recent[supplier_col].value_counts()
    all_suppliers = sorted(list(set(counts_prev.index).union(set(counts_recent.index))))

    rows = []
    shifts = []

    for supp in all_suppliers:
        n_prev = int(counts_prev.get(supp, 0))
        n_recent = int(counts_recent.get(supp, 0))

        pct_prev = (n_prev / tot_prev * 100) if tot_prev > 0 else 0.0
        pct_recent = (n_recent / tot_recent * 100) if tot_recent > 0 else 0.0
        variance = pct_recent - pct_prev

        shift_flag = "🔺" if variance > 0.5 else ("🔻" if variance < -0.5 else "➖")

        shifts.append({
            "supplier": supp,
            "group": map_to_group(supp),
            "n_prev": n_prev,
            "pct_prev": pct_prev,
            "n_recent": n_recent,
            "pct_recent": pct_recent,
            "variance": variance
        })

        row = {
            "Supplier": supp,
            "Assigned Group": map_to_group(supp)
        }

        if metric_view in ["Both (N & %)", "Counts Only (N)"]:
            row[f"{label_prev} (N)"] = n_prev
            row[f"{label_recent} (N)"] = n_recent

        if metric_view in ["Both (N & %)", "Share Only (%)"]:
            row[f"{label_prev} (%)"] = pct_prev
            row[f"{label_recent} (%)"] = pct_recent
            row["Variance"] = variance
            row["Trend"] = f"{shift_flag} {variance:+.1f}%"

        rows.append(row)

    comp_df = pd.DataFrame(rows)
    sort_target = f"{label_recent} (%)" if f"{label_recent} (%)" in comp_df.columns else f"{label_recent} (N)"
    comp_df = comp_df.sort_values(by=sort_target, ascending=False)

    col_configs = {
        "Supplier": st.column_config.TextColumn("Supplier", width="medium"),
        "Assigned Group": st.column_config.TextColumn("Assigned Group", width="medium"),
    }
    if f"{label_prev} (%)" in comp_df.columns:
        col_configs[f"{label_prev} (%)"] = st.column_config.NumberColumn(f"{label_prev} (%)", format="%.2f%%")
        col_configs[f"{label_recent} (%)"] = st.column_config.NumberColumn(f"{label_recent} (%)", format="%.2f%%")
        col_configs["Variance"] = st.column_config.NumberColumn("Shift", format="%+.2f%%")

    st.dataframe(
        comp_df,
        column_config=col_configs,
        use_container_width=True,
        hide_index=True
    )

    # ----------------------------------------------------
    # 8. Executive Summary & Insights
    # ----------------------------------------------------
    st.markdown("---")
    st.subheader("📝 Executive Summary & Shift Analysis")

    shifts_df = pd.DataFrame(shifts)

    g1_shift = group_df[group_df['Supplier Group'].str.contains("Group 1")]["Shift"].values[0]
    g2_shift = group_df[group_df['Supplier Group'].str.contains("Group 2")]["Shift"].values[0]
    g3_shift = group_df[group_df['Supplier Group'].str.contains("Group 3")]["Shift"].values[0]

    gainers = shifts_df[shifts_df["variance"] >= 1.0].sort_values(by="variance", ascending=False)
    cutbacks = shifts_df[shifts_df["variance"] <= -1.0].sort_values(by="variance", ascending=True)

    with st.container(border=True):
        st.markdown(f"#### 🔎 Strategic Blend Insights ({label_recent} vs {label_prev}):")

        st.markdown(f"""
1. **3-Group Blend Movement Dynamics:**
   * **Group 1 (Prime Insights)**: Shifted by **{g1_shift:+.1f}%** relative to baseline.
   * **Group 2 (Fusion & Social Loop)**: Shifted by **{g2_shift:+.1f}%**.
   * **Group 3 (Group MP / Marketplace)**: Shifted by **{g3_shift:+.1f}%**.
        """)

        if not gainers.empty:
            gain_bullets = [
                f"**{r['supplier']}** ({r['group']}): Rose **{r['variance']:+.1f}%** (from {r['pct_prev']:.1f}% to {r['pct_recent']:.1f}%)"
                for _, r in gainers.iterrows()
            ]
            st.markdown(f"2. **Top Individual Increases (Boosted Panels):**\n   * " + "\n   * ".join(gain_bullets))

        if not cutbacks.empty:
            cut_bullets = [
                f"**{r['supplier']}** ({r['group']}): Fell **{r['variance']:.1f}%** (from {r['pct_prev']:.1f}% to {r['pct_recent']:.1f}%)"
                for _, r in cutbacks.iterrows()
            ]
            st.markdown(f"3. **Top Individual Reductions (Throttled Panels):**\n   * " + "\n   * ".join(cut_bullets))

else:
    st.info("👈 Upload your tracker Excel or CSV file in the sidebar to begin.")
