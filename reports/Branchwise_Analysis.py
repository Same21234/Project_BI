import pandas as pd
import streamlit as st
from io import BytesIO

from utils.data_loader import get_data
from utils.report_helpers import format_indian, format_percent, format_crore, format_decimal
from utils.report_template import report_header


def _safe_sum(df, column_name):
    if column_name not in df.columns:
        return 0
    return pd.to_numeric(df[column_name], errors="coerce").fillna(0).sum()


def _find_column(df, candidates):
    for column in candidates:
        if column in df.columns:
            return column
    return None


def render_report(selected_month):

    # Report Header
    report_header(
        "🏢 Branch Wise Analysis",
        selected_month
    )

    # Load Data
    df = get_data(
        "branch_wise_analysis",
        selected_month
    )

    # KPI Cards (recomputed from dataframe per requirements)
    df_num = df.copy()

    # parse month values for comparisons if present
    if "Month" in df_num.columns:
        df_num["_month_dt"] = pd.to_datetime(df_num["Month"], errors="coerce")
    elif "mmm_yy" in df_num.columns:
        df_num["_month_dt"] = pd.to_datetime(df_num["mmm_yy"], format="%b-%y", errors="coerce")
    else:
        df_num["_month_dt"] = pd.NaT

    try:
        sel_month_dt = pd.to_datetime(selected_month, format="%b-%y", errors="coerce")
    except Exception:
        sel_month_dt = pd.to_datetime(selected_month, errors="coerce")

    loan_disb_col = _find_column(df_num, ["Loan Disb", "loan_disb"])
    loan_amt_col = _find_column(df_num, ["Loan Amt Disb", "Loan Amt. Disb.", "loan_amount_disbursed"])
    cumu_col = _find_column(df_num, ["Cumulative Disb", "Cumu. Loan Disb", "loan_amount_disbursed"])
    pos_col = _find_column(df_num, ["POS", "onus_pos"])
    par_gt0_col = _find_column(df_num, ["PAR GT0", "par_gt0"])
    par_30_col = _find_column(df_num, ["PAR 30 Plus", "par_30_plus"])
    par_writeoff_col = _find_column(df_num, ["PAR GT0 & Write_Off", "par_gt0_and_writeoff"])

    for col in [loan_disb_col, loan_amt_col, cumu_col, pos_col, par_gt0_col, par_30_col, par_writeoff_col]:
        if col and col in df_num.columns:
            df_num[col] = pd.to_numeric(df_num[col], errors="coerce").fillna(0)

    total_active_loan = int(_safe_sum(df_num, "Total Active Loans")) if "Total Active Loans" in df_num.columns else 0
    total_active_client = int(_safe_sum(df_num, "Total Active Client")) if "Total Active Client" in df_num.columns else 0

    if not pd.isna(sel_month_dt) and "_month_dt" in df_num.columns:
        mask_sel = (
            (df_num["_month_dt"].dt.year == sel_month_dt.year)
            & (df_num["_month_dt"].dt.month == sel_month_dt.month)
        )
    elif "Month" in df_num.columns:
        mask_sel = df_num["Month"].astype(str) == str(selected_month)
    else:
        mask_sel = (df_num["mmm_yy"] == selected_month) if "mmm_yy" in df_num.columns else pd.Series([False] * len(df_num))

    loan_disb_count = int(_safe_sum(df_num.loc[mask_sel], loan_disb_col)) if loan_disb_col else 0
    loan_amt_disb = float(_safe_sum(df_num.loc[mask_sel], loan_amt_col)) if loan_amt_col else 0

    if not pd.isna(sel_month_dt) and "_month_dt" in df_num.columns:
        mask_cumu = df_num["_month_dt"] <= sel_month_dt
    else:
        mask_cumu = pd.Series([True] * len(df_num))

    total_cumu_disb = float(_safe_sum(df_num.loc[mask_cumu], cumu_col)) if cumu_col else 0
    total_pos_raw = float(_safe_sum(df_num, pos_col)) if pos_col else 0

    par_gt0_sum = float(_safe_sum(df_num, par_gt0_col)) if par_gt0_col else 0
    par_30_sum = float(_safe_sum(df_num, par_30_col)) if par_30_col else 0
    par_gt0_writeoff_sum = float(_safe_sum(df_num, par_writeoff_col)) if par_writeoff_col else 0

    # Safe ratios
    par0_on_disb = (par_gt0_writeoff_sum / total_cumu_disb) if total_cumu_disb else 0
    par30_on_disb = (par_30_sum / total_cumu_disb) if total_cumu_disb else 0
    par0_on_pos = (par_gt0_sum / total_pos_raw) if total_pos_raw else 0
    par30_on_pos = (par_30_sum / total_pos_raw) if total_pos_raw else 0

    # Branch count / category counts (preserve existing behavior)
    branch_count = int(df["Branch With Code"].nunique(dropna=True)) if "Branch With Code" in df.columns else 0
    category_count = int(df["Branch Category"].nunique(dropna=True)) if "Branch Category" in df.columns else 0
    category_counts = None
    category_metrics = None
    if "Branch Category" in df.columns and "Branch With Code" in df.columns:
        category_counts = (
            df.groupby("Branch Category")["Branch With Code"]
            .nunique()
            .sort_values(ascending=False)
        )

        grouping = df_num.groupby("Branch Category")
        category_metrics = grouping.agg(
            category_count=("Branch With Code", "nunique"),
            cumu_sum=(cumu_col, "sum") if cumu_col else ("Branch With Code", "count"),
            pos_sum=(pos_col, "sum") if pos_col else ("Branch With Code", "count"),
            par_gt0_sum=(par_gt0_col, "sum") if par_gt0_col else ("Branch With Code", "count"),
            par_30_sum=(par_30_col, "sum") if par_30_col else ("Branch With Code", "count"),
            par_gt0_writeoff_sum=(par_writeoff_col, "sum") if par_writeoff_col else ("Branch With Code", "count"),
        )
        category_metrics = category_metrics.fillna(0)

    # Branch category summary card on the left
    left_card, right_card = st.columns([2, 4], gap=None, vertical_alignment="top")
    with left_card:
        if category_metrics is not None:
            category_rows = "".join(
                f"<tr>"
                f"<td style='padding:0.35rem 0.5rem; text-align:left; border-bottom:1px solid #cbd5e1;'>{cat}</td>"
                f"<td style='padding:0.35rem 0.5rem; text-align:right; border-bottom:1px solid #cbd5e1;'>{int(row.category_count):,}</td>"
                f"<td style='padding:0.35rem 0.5rem; text-align:right; border-bottom:1px solid #cbd5e1;'>{format_percent((row.par_gt0_writeoff_sum / row.cumu_sum) if row.cumu_sum else 0)}</td>"
                f"<td style='padding:0.35rem 0.5rem; text-align:right; border-bottom:1px solid #cbd5e1;'>{format_percent((row.par_30_sum / row.cumu_sum) if row.cumu_sum else 0)}</td>"
                f"<td style='padding:0.35rem 0.5rem; text-align:right; border-bottom:1px solid #cbd5e1;'>{format_percent((row.par_gt0_sum / row.pos_sum) if row.pos_sum else 0)}</td>"
                f"<td style='padding:0.35rem 0.5rem; text-align:right; border-bottom:1px solid #cbd5e1;'>{format_percent((row.par_30_sum / row.pos_sum) if row.pos_sum else 0)}</td>"
                f"</tr>"
                for cat, row in category_metrics.sort_values(by="category_count", ascending=False).iterrows()
            )
            total_category_branches = category_metrics["category_count"].sum()
            total_cumu = category_metrics["cumu_sum"].sum()
            total_pos = category_metrics["pos_sum"].sum()
            total_par0_disb = (category_metrics["par_gt0_writeoff_sum"].sum() / total_cumu) if total_cumu else 0
            total_par30_disb = (category_metrics["par_30_sum"].sum() / total_cumu) if total_cumu else 0
            total_par0_pos = (category_metrics["par_gt0_sum"].sum() / total_pos) if total_pos else 0
            total_par30_pos = (category_metrics["par_30_sum"].sum() / total_pos) if total_pos else 0
        else:
            category_rows = ""
            total_category_branches = 0
            total_par0_disb = total_par30_disb = total_par0_pos = total_par30_pos = 0

        st.markdown(
            f"<div style='padding:1rem; border-radius:1rem; background:#f8fafc; width:100%;'>"
            f"<div style='font-size:0.95rem; color:#334155; font-weight:700; margin-bottom:0.5rem;'>Branch Wise Catg. Count</div>"
            f"<table style='width:100%; border-collapse:collapse; font-size:0.82rem; table-layout:fixed; max-width:100%;'>"
            f"<colgroup>"
            f"<col style='width:31%;'/>"
            f"<col style='width:13%;'/>"
            f"<col style='width:13%;'/>"
            f"<col style='width:13%;'/>"
            f"<col style='width:15%;'/>"
            f"<col style='width:15%;'/>"
            f"</colgroup>"
            f"<thead><tr style='background:#ddd6fe; color:#1e293b; font-weight:700;'>"
            f"<th style='padding:0.35rem 0.45rem; text-align:left; white-space:normal; line-height:1.1; font-size:0.82rem;'>Category</th>"
            f"<th style='padding:0.35rem 0.45rem; text-align:center; white-space:normal; line-height:1.1; font-size:0.82rem;'>Count</th>"
            f"<th style='padding:0.35rem 0.45rem; text-align:center; white-space:normal; line-height:1.1; font-size:0.82rem;'>PAR 0% On DISB</th>"
            f"<th style='padding:0.35rem 0.45rem; text-align:center; white-space:normal; line-height:1.1; font-size:0.82rem;'>PAR 30% On Disb</th>"
            f"<th style='padding:0.35rem 0.45rem; text-align:center; white-space:normal; line-height:1.1; font-size:0.82rem;'>PAR 0% On POS</th>"
            f"<th style='padding:0.35rem 0.45rem; text-align:center; white-space:normal; line-height:1.1; font-size:0.82rem;'>PAR 30% On POS</th>"
            f"</tr></thead>"
            f"<tbody>{category_rows}"
            f"<tr style='background:#fde68a; font-weight:700;'>"
            f"<td style='padding:0.45rem 0.5rem; text-align:left; white-space:nowrap;'>Total</td>"
            f"<td style='padding:0.45rem 0.5rem; text-align:center; white-space:nowrap;'>{int(total_category_branches):,}</td>"
            f"<td style='padding:0.45rem 0.5rem; text-align:center; white-space:nowrap;'>{format_percent(total_par0_disb)}</td>"
            f"<td style='padding:0.45rem 0.5rem; text-align:center; white-space:nowrap;'>{format_percent(total_par30_disb)}</td>"
            f"<td style='padding:0.45rem 0.5rem; text-align:center; white-space:nowrap;'>{format_percent(total_par0_pos)}</td>"
            f"<td style='padding:0.45rem 0.5rem; text-align:center; white-space:nowrap;'>{format_percent(total_par30_pos)}</td>"
            f"</tr>"
            f"</tbody></table>"
            f"<div style='font-size:0.9rem; color:#475569; margin-top:0.6rem;'>Distinct Categories: {category_count}</div>"
            f"<div style='font-size:0.9rem; color:#475569; margin-top:0.2rem;'>Total Branches: {branch_count}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # Use the full right-side space for evenly distributed KPI cards.
    with right_card:
        kpi_values = [
            ("📊 Total Active Loan", format_indian(total_active_loan)),
            ("Loan Disb.", format_indian(loan_disb_count)),
            ("👥 Total Active Client", format_indian(total_active_client)),
            ("Loan Amt. Disb. (Cr.)", format_crore(loan_amt_disb)),
            ("Total Cumulative Disb. (Cr.)", format_crore(total_cumu_disb)),
            ("💰 POS in Cr.", format_crore(total_pos_raw)),
            ("PAR 0% On Disb", format_percent(par0_on_disb)),
            ("PAR 30% On Disb", format_percent(par30_on_disb)),
            ("PAR 0% On POS", format_percent(par0_on_pos)),
            ("PAR 30% On POS", format_percent(par30_on_pos)),
        ]
        for row_start in range(0, len(kpi_values), 5):
            kpi_row = st.columns(5, gap=None)
            for column, (label, value) in zip(kpi_row, kpi_values[row_start:row_start + 5]):
                column.markdown(
                    f"<div style='width:100%; padding:0 0.35rem 0.35rem 0; line-height:1.05;'>"
                    f"<div style='font-size:0.8rem; font-weight:700; white-space:normal;'>{label}</div>"
                    f"<div style='font-size:1.55rem; font-weight:700; margin-top:0.08rem;'>{value}</div>"
                    "</div>",
                    unsafe_allow_html=True,
                )
    st.markdown("---")

    # Show Record Count
    st.success(f"Total Records : {len(df):,}")

    # Prepare dataframe for display: add Sr. No. as first column (1-indexed)
    df_display = df.copy()
    df_display = df_display.reset_index(drop=True)
    df_display.insert(0, "Sr. No.", range(1, len(df_display) + 1))

    crore_columns = [
        "Cumulative Disb",
        "Loan Amt Disb",
        "POS",
        "PAR GT0",
        "PAR 30 Plus",
        "PAR GT0 & Write_Off",
    ]

    # Grand total row, calculated from the same displayed branch-level dataframe
    grand_total = {
        "Sr. No.": "Total",
        "Month": df["snapshot_date"].nunique(dropna=True) if "snapshot_date" in df.columns else "",
        "Branch With Code": df["Branch With Code"].nunique(dropna=True) if "Branch With Code" in df.columns else "",
        "Branch Type": df["Branch Type"].nunique(dropna=True) if "Branch Type" in df.columns else "",
        "Branch District": df["Branch District"].nunique(dropna=True) if "Branch District" in df.columns else "",
        "Branch State": df["Branch State"].nunique(dropna=True) if "Branch State" in df.columns else "",
        "Branch Category": df["Branch Category"].nunique(dropna=True) if "Branch Category" in df.columns else "",
        "Total Active Loans": pd.to_numeric(df["Total Active Loans"], errors="coerce").sum() if "Total Active Loans" in df.columns else "",
        "Total Active Client": pd.to_numeric(df["Total Active Client"], errors="coerce").sum() if "Total Active Client" in df.columns else "",
        "Loan Disb": pd.to_numeric(df["Loan Disb"], errors="coerce").sum() if "Loan Disb" in df.columns else "",
        "Cumulative Disb": pd.to_numeric(df["Cumulative Disb"], errors="coerce").sum() if "Cumulative Disb" in df.columns else "",
        "Loan Amt Disb": pd.to_numeric(df["Loan Amt Disb"], errors="coerce").sum() if "Loan Amt Disb" in df.columns else "",
        "POS": pd.to_numeric(df["POS"], errors="coerce").sum() if "POS" in df.columns else "",
        "PAR GT0": pd.to_numeric(df["PAR GT0"], errors="coerce").sum() if "PAR GT0" in df.columns else "",
        "PAR 30 Plus": pd.to_numeric(df["PAR 30 Plus"], errors="coerce").sum() if "PAR 30 Plus" in df.columns else "",
        "PAR GT0 & Write_Off": pd.to_numeric(df["PAR GT0 & Write_Off"], errors="coerce").sum() if "PAR GT0 & Write_Off" in df.columns else "",
    }
    for column in df_display.columns:
        if column not in grand_total:
            grand_total[column] = ""

    df_display = pd.concat(
        [pd.DataFrame([grand_total], columns=df_display.columns), df_display],
        ignore_index=True,
    )

    # Show Data (use the same final dataframe for display and Excel)
    integer_columns = [
        "Total Active Loans",
        "Total Active Client",
        "Loan Disb",
    ]
    display_style = df_display.style.format({
        **{column: lambda v: format_indian(pd.to_numeric(v, errors="coerce")) if pd.notna(pd.to_numeric(v, errors="coerce")) else "" for column in integer_columns},
        **{column: lambda v: format_decimal(pd.to_numeric(v, errors="coerce"), digits=2) if pd.notna(pd.to_numeric(v, errors="coerce")) else "" for column in crore_columns},
    }).apply(
        lambda row: ["font-weight:700; background-color:#FFE699" if row.name == 0 else "" for _ in row],
        axis=1,
    )
    st.dataframe(display_style, width="stretch")

    # Excel download (.xlsx) with Sr. No. and formatting
    try:
        import openpyxl  # ensure the Excel engine is installed and available

        towrite = BytesIO()
        sheet_name = "Branch_Wise_Analysis"
        with pd.ExcelWriter(towrite, engine="openpyxl") as writer:
            df_display.to_excel(writer, sheet_name=sheet_name, index=False)
            worksheet = writer.sheets[sheet_name]
            # Auto-adjust column widths
            from openpyxl.utils import get_column_letter

            for idx, col in enumerate(df_display.columns, 1):
                # compute max length in column safely
                col_values = df_display[col].fillna("").astype(str)
                max_value_len = col_values.map(lambda x: len(x) if isinstance(x, str) else len(str(x))).max() if len(col_values) else 0
                max_len = max(max_value_len, len(str(col)))
                adjusted_width = (max_len + 2)
                worksheet.column_dimensions[get_column_letter(idx)].width = adjusted_width
        towrite.seek(0)
        st.download_button(
            label="Download Excel",
            data=towrite.getvalue(),
            file_name="Branch_Wise_Analysis.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as exc:
        st.error(f"Unable to create Excel file for download: {exc}")