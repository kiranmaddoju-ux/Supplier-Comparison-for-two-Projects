import streamlit as st
import pandas as pd
import re

# ----------------------------------------------------
# 1. Page Configuration & Layout
# ----------------------------------------------------
st.set_page_config(
    page_title="CRM Supplier Allocation Comparator",
    page_icon="⚖️",
    layout="wide"
)

st.title("⚖️ CRM Supplier Allocation Comparator")
st.caption("Side-by-side supplier share comparison and automated key shift insights.")
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
    status_def_idx = get_default_index(["status", "disposition"], all_cols)

    project_col = st.sidebar.selectbox("Project / CRM Column:", all_cols, index=proj_def_idx)
    supplier_col = st.sidebar.selectbox("Supplier Column (Name or ID):", all_cols, index=supp_def_idx)

    # Optional status filter
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
    # 3. CRM Project Identification & Selection
    # ----------------------------------------------------
    st.sidebar.markdown("---")
    st.sidebar.header("🎯 CRM Selection")

    # Smart default finder for 131932 (Prev) and 149464 (Recent)
    idx_prev = 0
    idx_recent = 1 if len(available_projects) > 1 else 0

    for idx, p in enumerate(available_projects):
        if "131932" in p:
            idx_prev = idx
        elif "149464" in p:
            idx_recent = idx

    proj_prev = st.sidebar.selectbox("Previous CRM / Wave:", available_projects, index=idx_prev)
    proj_recent = st.sidebar.selectbox("Recent CRM / Wave:", available_projects, index=idx_recent)

    if proj_prev == proj_recent:
        st.warning("Please choose two distinct CRMs to compare.")
        st.stop()

    # Helper function to extract short labels (e.g., 5-6 digit CRM numbers)
    def clean_label(full_val, fallback):
        match = re.search(r"\b\d{5,6}\b", full_val)
        return match.group(0) if match else fallback

    crm_num_prev = clean_label(proj_prev, "Previous")
    crm_num_recent = clean_label(proj_recent, "Recent")

    label_prev = f"{crm_num_prev} (Prev)"
    label_recent = f"{crm_num_recent} (Recent)"

    # Subset datasets
    df_prev = df[df[project_col] == proj_prev]
    df_recent = df[df[project_col] == proj_recent]
    tot_prev = len(df_prev)
    tot_recent = len(df_recent)

    # ----------------------------------------------------
    # 4. KPI Top Summary Cards
    # ----------------------------------------------------
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric(f"{label_prev} Total", f"{tot_prev:,}")
        st.caption(f"📌 *{proj_prev}*")
    with k2:
        st.metric(f"{label_recent} Total", f"{tot_recent:,}")
        st.caption(f"📌 *{proj_recent}*")
    with k3:
        st.metric("Combined Completes", f"{tot_prev + tot_recent:,}")
    with k4:
        delta_records = tot_recent - tot_prev
        st.metric("Sample Variance", f"{abs(delta_records):,}", f"{delta_records:+} Recent vs Prev")

    st.markdown("---")

    # ----------------------------------------------------
    # 5. Table View & Metric Calculations
    # ----------------------------------------------------
    c_title, c_toggle = st.columns([2, 1])
    with c_title:
        st.subheader(f"📊 Allocation Breakdown: {crm_num_prev} vs {crm_num_recent}")
    with c_toggle:
        metric_view = st.radio(
            "Display Metrics:",
            options=["Share Only (%)", "Both (N & %)", "Counts Only (N)"],
            index=0,  # Zero horizontal scrolling
            horizontal=True
        )

    counts_prev = df_prev[supplier_col].value_counts()
    counts_recent = df_recent[supplier_col].value_counts()
    all_suppliers = sorted(list(set(counts_prev.index).union(set(counts_recent.index))))

    rows = []
    shifts = []  # To feed the summary engine

    for supp in all_suppliers:
        n_prev = int(counts_prev.get(supp, 0))
        n_recent = int(counts_recent.get(supp, 0))

        pct_prev = (n_prev / tot_prev * 100) if tot_prev > 0 else 0.0
        pct_recent = (n_recent / tot_recent * 100) if tot_recent > 0 else 0.0
        variance = pct_recent - pct_prev

        shift_flag = "🔺" if variance > 0.5 else ("🔻" if variance < -0.5 else "➖")

        shifts.append({
            "supplier": supp,
            "n_prev": n_prev,
            "pct_prev": pct_prev,
            "n_recent": n_recent,
            "pct_recent": pct_recent,
            "variance": variance
        })

        row = {"Supplier": supp}

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

    # Sort descending by Recent share (or Recent count)
    sort_target = f"{label_recent} (%)" if f"{label_recent} (%)" in comp_df.columns else f"{label_recent} (N)"
    comp_df = comp_df.sort_values(by=sort_target, ascending=False)

    # Column configuration for compact display
    col_configs = {
        "Supplier": st.column_config.TextColumn("Supplier", width="medium"),
    }
    if f"{label_prev} (%)" in comp_df.columns:
        col_configs[f"{label_prev} (%)"] = st.column_config.NumberColumn(f"{label_prev} (%)", format="%.2f%%")
        col_configs[f"{label_recent} (%)"] = st.column_config.NumberColumn(f"{label_recent} (%)", format="%.2f%%")
        col_configs["Variance"] = st.column_config.NumberColumn(f"Shift ({crm_num_recent} - {crm_num_prev})", format="%+.2f%%")

    st.dataframe(
        comp_df,
        column_config=col_configs,
        use_container_width=True,
        hide_index=True
    )

    # ----------------------------------------------------
    # 6. Automated Executive Summary & Reading Guide
    # ----------------------------------------------------
    st.markdown("---")
    st.subheader("📝 Executive Summary & Shift Analysis")
    st.caption("Plain-language breakdown of key sample movements between the two waves.")

    # Convert shifts to DataFrame for quick ranking
    shifts_df = pd.DataFrame(shifts)

    # 1. Top Contributors in Recent Wave
    top_recent = shifts_df.sort_values(by="pct_recent", ascending=False).head(3)
    top_recent_text = ", ".join(
        [f"**{r['supplier']}** ({r['pct_recent']:.1f}% share, {r['n_recent']:,} completes)" for _, r in top_recent.iterrows() if r['pct_recent'] > 0]
    )

    # 2. Significant Increases (Gainers >= +1.0%)
    gainers = shifts_df[shifts_df["variance"] >= 1.0].sort_values(by="variance", ascending=False)
    # 3. Significant Decreases (Cutbacks <= -1.0%)
    cutbacks = shifts_df[shifts_df["variance"] <= -1.0].sort_values(by="variance", ascending=True)

    # 4. Exclusive Suppliers
    only_in_prev = [s for s in all_suppliers if counts_prev.get(s, 0) > 0 and counts_recent.get(s, 0) == 0]
    only_in_recent = [s for s in all_suppliers if counts_recent.get(s, 0) > 0 and counts_prev.get(s, 0) == 0]

    with st.container(border=True):
        st.markdown(f"#### 🔎 What the numbers are telling us:")

        # Summary item 1: Volume Drivers
        st.markdown(f"1. **Primary Volume Drivers in {crm_num_recent}:**\n   * The largest contributors in the recent wave are {top_recent_text if top_recent_text else 'None'}.")

        # Summary item 2: Major Increases
        if not gainers.empty:
            gain_bullets = [
                f"**{r['supplier']}**: Increased by **{r['variance']:+.1f}%** (rose from {r['pct_prev']:.1f}% to {r['pct_recent']:.1f}%)"
                for _, r in gainers.iterrows()
            ]
            st.markdown(f"2. **Increased Supplier Allocation (Shifted Up):**\n   * " + "\n   * ".join(gain_bullets))
        else:
            st.markdown(f"2. **Increased Supplier Allocation:**\n   * No supplier gained more than 1.0% share.")

        # Summary item 3: Major Decreases
        if not cutbacks.empty:
            cut_bullets = [
                f"**{r['supplier']}**: Dropped by **{r['variance']:.1f}%** (fell from {r['pct_prev']:.1f}% to {r['pct_recent']:.1f}%)"
                for _, r in cutbacks.iterrows()
            ]
            st.markdown(f"3. **Reduced Supplier Allocation (Shifted Down):**\n   * " + "\n   * ".join(cut_bullets))
        else:
            st.markdown(f"3. **Reduced Supplier Allocation:**\n   * No supplier dropped by more than 1.0% share.")

        # Summary item 4: Exclusivity & Turnover
        if only_in_recent or only_in_prev:
            st.markdown(f"4. **Panel Composition Turnover:**")
            if only_in_recent:
                st.markdown(f"   * 🟢 **New in {crm_num_recent}**: {', '.join([f'**{s}**' for s in only_in_recent])} (was not used in {crm_num_prev}).")
            if only_in_prev:
                st.markdown(f"   * 🔴 **Inactive in {crm_num_recent}**: {', '.join([f'**{s}**' for s in only_in_prev])} (only used in {crm_num_prev}).")
        else:
            st.markdown(f"4. **Panel Composition Turnover:**\n   * ✅ Consistent supplier set: Both waves used the exact same supplier list.")

else:
    st.info("👈 Upload your tracker Excel or CSV file in the sidebar to begin.")
