import streamlit as st
import pandas as pd
import re
import os

# ----------------------------------------------------
# 1. Page Configuration & Layout
# ----------------------------------------------------
st.set_page_config(
    page_title="Wave Allocation Comparator",
    page_icon="⚖️",
    layout="wide"
)

st.title("⚖️ Wave & Supplier Allocation Comparator")
st.caption("Compare supplier allocations between waves and benchmark against David's UK Master Blend Target Rules.")
st.markdown("---")

# ----------------------------------------------------
# 2. Master Blend Target Parser (David Column)
# ----------------------------------------------------
@st.cache_data
def load_david_targets(rule_file_source=None):
    """
    Parses columns 0 to 3 of the 'Blend' sheet (David Column targets)
    """
    try:
        if rule_file_source is not None:
            raw = pd.read_excel(rule_file_source, sheet_name="Blend")
        elif os.path.exists("internal_master_rules.xlsx"):
            raw = pd.read_excel("internal_master_rules.xlsx", sheet_name="Blend")
        else:
            return pd.DataFrame(), {}

        # First 4 columns: Country, Group (David), Supplier, Allocation
        df_rules = raw.iloc[:, [0, 1, 2, 3]].copy()
        df_rules.columns = ['Country', 'Group', 'Supplier', 'Allocation']
        df_rules['Country'] = df_rules['Country'].ffill()

        target_allocations = []
        supplier_mapping = {}
        current_group = None

        for _, row in df_rules.iterrows():
            country = str(row['Country']).strip()
            grp = str(row['Group']).strip()
            supp = str(row['Supplier']).strip()
            alloc = row['Allocation']

            if grp.lower() == "group assignments" or country.lower() == "nan":
                continue

            if grp != "nan":
                current_group = grp
                try:
                    alloc_val = float(alloc)
                    target_allocations.append({
                        "Country": country,
                        "Supplier Group": current_group,
                        "Target Allocation": alloc_val
                    })
                except (ValueError, TypeError):
                    pass

            if supp != "nan" and current_group:
                supplier_mapping[(country.lower(), supp.lower())] = current_group

        return pd.DataFrame(target_allocations), supplier_mapping
    except Exception as e:
        st.sidebar.error(f"Error loading master rules: {e}")
        return pd.DataFrame(), {}

# ----------------------------------------------------
# 3. Sidebar Ingestion & Data Preparation
# ----------------------------------------------------
st.sidebar.header("📁 Ingestion")
uploaded_file = st.sidebar.file_uploader("Upload Tracker CSV or Excel", type=["csv", "xlsx", "xls"])

# Optional manual upload for master rules if not in repo
rule_file = st.sidebar.file_uploader("Upload Master Rules Excel (Optional)", type=["xlsx", "xls"], key="rules_uploader")
target_df, master_supplier_map = load_david_targets(rule_file)

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
    # 4. Wave Definition (Multiselect Picker)
    # ----------------------------------------------------
    st.sidebar.markdown("---")
    st.sidebar.header("🎯 Wave Selection")

    label_prev = st.sidebar.text_input("Baseline Wave Name:", value="Previous Wave")
    default_a = [unique_projects[0]] if unique_projects else []
    projects_a = st.sidebar.multiselect("Select project(s) for Baseline Wave:", options=unique_projects, default=default_a)

    label_recent = st.sidebar.text_input("Comparison Wave Name:", value="Recent Wave")
    default_b = [unique_projects[1]] if len(unique_projects) > 1 else []
    projects_b = st.sidebar.multiselect("Select project(s) for Comparison Wave:", options=unique_projects, default=default_b)

    if not projects_a or not projects_b:
        st.warning("Please ensure at least one project/segment is selected for both waves.")
        st.stop()

    # ----------------------------------------------------
    # 5. Group Classification (Rules Alignment)
    # ----------------------------------------------------
    def clean_group(supp_name):
        s = str(supp_name).lower()
        if "prime insights" in s:
            return "Group 1"
        elif any(f in s for f in ["fusion", "social loop"]):
            return "Group 2"
        return "Group MP"

    df['Blend Group'] = df[supplier_col].apply(clean_group)

    df_prev = df[df[project_col].isin(projects_a)]
    df_recent = df[df[project_col].isin(projects_b)]

    tot_prev = len(df_prev)
    tot_recent = len(df_recent)

    # ----------------------------------------------------
    # 6. KPI Summary Cards
    # ----------------------------------------------------
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric(f"{label_prev} (N)", f"{tot_prev:,}")
        st.caption(f"{len(projects_a)} segment(s)")
    with k2:
        st.metric(f"{label_recent} (N)", f"{tot_recent:,}")
        st.caption(f"{len(projects_b)} segment(s)")
    with k3:
        st.metric("Total Completes", f"{tot_prev + tot_recent:,}")
    with k4:
        delta_records = tot_recent - tot_prev
        st.metric("Sample Difference", f"{abs(delta_records):,}", f"{delta_records:+} Comparison vs Baseline")

    st.markdown("---")

    # ----------------------------------------------------
    # 7. Alignment vs David's UK Target Rules
    # ----------------------------------------------------
    uk_targets = {
        "Group 1": 0.25,
        "Group 2": 0.35,
        "Group MP": 0.40
    }

    # Override if loaded dynamically from master rules file
    if not target_df.empty:
        uk_df = target_df[target_df['Country'].str.lower().isin(['united kingdom', 'uk'])]
        if not uk_df.empty:
            uk_targets = dict(zip(uk_df['Supplier Group'], uk_df['Target Allocation']))

    st.subheader(f"🎯 Target Alignment vs David's UK Blend Rules ({label_recent})")
    st.caption("David's Target Quota: Group 1 (25%), Group 2 (35%), Group MP (40%). Tolerance: ±3.0%")

    grp_counts_recent = df_recent['Blend Group'].value_counts()
    
    align_cols = st.columns(3)
    target_kpi_info = {}

    for idx, (grp, target_pct) in enumerate(uk_targets.items()):
        achieved_n = int(grp_counts_recent.get(grp, 0))
        achieved_pct = (achieved_n / tot_recent * 100) if tot_recent > 0 else 0.0
        target_display = target_pct * 100
        delta = achieved_pct - target_display

        status = "🟢 Aligned" if abs(delta) <= 3.0 else ("🟡 Over Target" if delta > 3.0 else "🔴 Under Target")
        target_kpi_info[grp] = {
            "target": target_display,
            "achieved": achieved_pct,
            "delta": delta,
            "status": status
        }

        with align_cols[idx % 3]:
            st.metric(
                label=f"{grp} (Target {target_display:.0f}%)",
                value=f"{achieved_pct:.1f}%",
                delta=f"{delta:+.1f}% vs Target"
            )

    st.markdown("---")

    # ----------------------------------------------------
    # 8. 3-Group Blend Summary Table
    # ----------------------------------------------------
    st.subheader(f"🏢 3-Group Blend Summary Table")
    st.caption("Consolidated rollup across waves with benchmark comparison against David's UK Targets.")

    group_order = ["Group 1", "Group 2", "Group MP"]
    grp_counts_prev = df_prev['Blend Group'].value_counts()

    group_rows = []
    for g in group_order:
        g_n_prev = int(grp_counts_prev.get(g, 0))
        g_n_rec = int(grp_counts_recent.get(g, 0))

        g_pct_prev = (g_n_prev / tot_prev * 100) if tot_prev > 0 else 0.0
        g_pct_rec = (g_n_rec / tot_recent * 100) if tot_recent > 0 else 0.0
        g_diff = g_pct_rec - g_pct_prev

        t_pct = uk_targets.get(g, 0.0) * 100
        t_var = g_pct_rec - t_pct

        g_flag = "🔺" if g_diff > 0.5 else ("🔻" if g_diff < -0.5 else "➖")

        group_rows.append({
            "Supplier Group": g,
            "David Target (%)": t_pct,
            f"{label_prev} (N)": g_n_prev,
            f"{label_prev} (%)": g_pct_prev,
            f"{label_recent} (N)": g_n_rec,
            f"{label_recent} (%)": g_pct_rec,
            "Wave Shift": g_diff,
            "Shift Direction": f"{g_flag} {g_diff:+.1f}%",
            "Target Variance": t_var,
            "Quota Status": target_kpi_info.get(g, {}).get("status", "—")
        })

    group_df = pd.DataFrame(group_rows)

    st.dataframe(
        group_df,
        column_config={
            "David Target (%)": st.column_config.NumberColumn(format="%.1f%%"),
            f"{label_prev} (%)": st.column_config.NumberColumn(format="%.2f%%"),
            f"{label_recent} (%)": st.column_config.NumberColumn(format="%.2f%%"),
            "Wave Shift": st.column_config.NumberColumn(format="%+.2f%%"),
            "Target Variance": st.column_config.NumberColumn(format="%+.2f%%"),
        },
        use_container_width=True,
        hide_index=True
    )

    st.markdown("---")

    # ----------------------------------------------------
    # 9. Granular Supplier Table
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
            "group": clean_group(supp),
            "n_prev": n_prev,
            "pct_prev": pct_prev,
            "n_recent": n_recent,
            "pct_recent": pct_recent,
            "variance": variance
        })

        row = {
            "Supplier": supp,
            "Assigned Group": clean_group(supp)
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
        "Assigned Group": st.column_config.TextColumn("Assigned Group", width="small"),
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
    # 10. Automated Executive Notes & Quota Guidance
    # ----------------------------------------------------
    st.markdown("---")
    st.subheader("📝 Strategic Alignment & Operational Notes")

    shifts_df = pd.DataFrame(shifts)
    gainers = shifts_df[shifts_df["variance"] >= 1.0].sort_values(by="variance", ascending=False)
    cutbacks = shifts_df[shifts_df["variance"] <= -1.0].sort_values(by="variance", ascending=True)

    with st.container(border=True):
        st.markdown(f"#### 🔎 David's Quota Health & Blend Movements:")

        # Target Alignment Summary
        align_bullets = []
        action_bullets = []
        for grp, info in target_kpi_info.items():
            align_bullets.append(
                f"**{grp}**: Achieved **{info['achieved']:.1f}%** vs David's target **{info['target']:.0f}%** ({info['status']}, {info['delta']:+.1f}%)"
            )
            if info['delta'] > 3.0:
                action_bullets.append(f"Cap / Throttle intake for **{grp}** (running {info['delta']:+.1f}% over quota).")
            elif info['delta'] < -3.0:
                action_bullets.append(f"Boost / Prioritize sample into **{grp}** (running {info['delta']:+.1f}% below quota).")

        st.markdown("1. **Target Quota Deviations (UK Market):**\n   * " + "\n   * ".join(align_bullets))

        if action_bullets:
            st.markdown("2. **Recommended Corrective Steering:**\n   * " + "\n   * ".join(action_bullets))
        else:
            st.markdown("2. **Recommended Corrective Steering:**\n   * ✅ All supplier groups are within the acceptable ±3.0% tolerance band.")

        if not gainers.empty:
            gain_bullets = [
                f"**{r['supplier']}** ({r['group']}): Rose **{r['variance']:+.1f}%** (from {r['pct_prev']:.1f}% to {r['pct_recent']:.1f}%)"
                for _, r in gainers.iterrows()
            ]
            st.markdown("3. **Top Individual Increases (Boosted Vendors):**\n   * " + "\n   * ".join(gain_bullets))

        if not cutbacks.empty:
            cut_bullets = [
                f"**{r['supplier']}** ({r['group']}): Fell **{r['variance']:.1f}%** (from {r['pct_prev']:.1f}% to {r['pct_recent']:.1f}%)"
                for _, r in cutbacks.iterrows()
            ]
            st.markdown("4. **Top Individual Decreases (Throttled Vendors):**\n   * " + "\n   * ".join(cut_bullets))

else:
    st.info("👈 Upload your tracker Excel or CSV file in the sidebar to begin.")
