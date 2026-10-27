# ==========================================================
# ATS DISB MoM
# ==========================================================

import streamlit as st
import pandas as pd
from sqlalchemy import text
from io import BytesIO

from config.db import engine


# ==========================================================
# CONDITIONAL FORMATTING FUNCTIONS
# ==========================================================

def get_cell_color(value, low_limit, high_limit):

    try:
        value = float(value)

        if value >= high_limit:
            return "background-color: #C6EFCE; color: #006100;"

        elif value >= low_limit:
            return "background-color: #FFF2CC; color: #9C6500;"

        else:
            return "background-color: #FCE4D6; color: #C65911;"

    except Exception:
        return ""


def apply_matrix_formatting(df):

    """
    Conditional formatting:

    High       -> Green
    Medium     -> Yellow
    Very Low   -> Orange

    TOTAL row is kept separately.
    """

    if df.empty:
        return df.style

    # ------------------------------------------------------
    # Numeric values excluding TOTAL row
    # ------------------------------------------------------

    data_rows = df.copy()

    if "Loan Amount Bucket" in data_rows.columns:

        data_rows = data_rows[
            data_rows["Loan Amount Bucket"].astype(str).str.upper()
            != "TOTAL"
        ]

    numeric_values = []

    for col in data_rows.columns[1:]:

        values = pd.to_numeric(
            data_rows[col],
            errors="coerce"
        ).dropna()

        numeric_values.extend(
            values[values > 0].tolist()
        )

    # ------------------------------------------------------
    # No numeric values
    # ------------------------------------------------------

    if not numeric_values:

        return df.style

    numeric_series = pd.Series(
        numeric_values,
        dtype="float64"
    )

    # ------------------------------------------------------
    # Dynamic thresholds
    # ------------------------------------------------------

    low_limit = numeric_series.quantile(0.33)
    high_limit = numeric_series.quantile(0.67)

    # ------------------------------------------------------
    # Apply formatting
    # ------------------------------------------------------

    def style_dataframe(row):

        styles = []

        is_total = (
            str(row.iloc[0]).upper() == "TOTAL"
        )

        for index, value in enumerate(row):

            # Loan Amount Bucket column
            if index == 0:

                if is_total:
                    styles.append(
                        """
                        background-color: #FFF2CC;
                        font-weight: bold;
                        color: #000000;
                        """
                    )
                else:
                    styles.append("")

                continue

            # TOTAL row
            if is_total:

                styles.append(
                    """
                    background-color: #FFF2CC;
                    font-weight: bold;
                    color: #000000;
                    """
                )

            else:

                styles.append(
                    get_cell_color(
                        value,
                        low_limit,
                        high_limit
                    )
                )

        return styles

    return df.style.apply(
        style_dataframe,
        axis=1
    )


# ==========================================================
# MAIN REPORT FUNCTION
# ==========================================================

def ATS_Disb_MoM(selected_month):

    # ======================================================
    # PAGE TITLE
    # ======================================================

    st.title("📈 ATS Disb MoM")

    st.caption(
        f"Selected Snapshot Month: {selected_month}"
    )

    # ======================================================
    # LOAD DATA
    # ======================================================

    query = text("""
        SELECT
            "Month",
            "Disb Month",
            disb_month_sort,
            "Loan Amount Bucket",
            bucket_sort,
            "Loan Disb Count",
            "Amt Disb (Cr)"
        FROM warburg_mom."ATS_Disb_MoM"
        WHERE "Month" = :selected_month
        ORDER BY
            disb_month_sort DESC,
            bucket_sort ASC
    """)

    try:

        df = pd.read_sql(
            query,
            engine,
            params={
                "selected_month": selected_month
            }
        )

    except Exception as e:

        st.error(
            f"Unable to load ATS Disb MoM data: {e}"
        )

        return

    # ======================================================
    # EMPTY CHECK
    # ======================================================

    if df.empty:

        st.warning(
            "No ATS Disb MoM data found for the selected month."
        )

        return

    # ======================================================
    # NUMERIC CONVERSION
    # ======================================================

    df["Loan Disb Count"] = pd.to_numeric(
        df["Loan Disb Count"],
        errors="coerce"
    ).fillna(0)

    df["Amt Disb (Cr)"] = pd.to_numeric(
        df["Amt Disb (Cr)"],
        errors="coerce"
    ).fillna(0)

    df["bucket_sort"] = pd.to_numeric(
        df["bucket_sort"],
        errors="coerce"
    )

    df["disb_month_sort"] = pd.to_numeric(
        df["disb_month_sort"],
        errors="coerce"
    )

    # ======================================================
    # SORT
    # ======================================================

    df = df.sort_values(
        [
            "bucket_sort",
            "disb_month_sort"
        ],
        ascending=[
            True,
            False
        ]
    )

    # ======================================================
    # KPI
    # ======================================================

    total_loan_count = int(
        df["Loan Disb Count"].sum()
    )

    total_disb_cr = float(
        df["Amt Disb (Cr)"].sum()
    )

    total_disb_months = int(
        df["Disb Month"].nunique()
    )

    # ======================================================
    # KPI DISPLAY
    # ======================================================

    col1, col2, col3 = st.columns(3)

    with col1:

        st.markdown(
            "**Loan Disb Count**"
        )

        st.markdown(
            f"### {total_loan_count:,.0f}"
        )

    with col2:

        st.markdown(
            "**Amt Disb (Cr)**"
        )

        st.markdown(
            f"### {total_disb_cr:,.2f}"
        )

    with col3:

        st.markdown(
            "**Disb Months**"
        )

        st.markdown(
            f"### {total_disb_months:,.0f}"
        )

    st.divider()

    # ======================================================
    # MONTH ORDER - LATEST MONTH FIRST
    # ======================================================

    month_order = (
        df[
            [
                "Disb Month",
                "disb_month_sort"
            ]
        ]
        .drop_duplicates()
        .sort_values(
            "disb_month_sort",
            ascending=False
        )
    )

    # ------------------------------------------------------
    # Latest month will always be LEFT
    #
    # Example:
    # Sep-26 | Aug-26 | Jul-26 | Jun-26 | ...
    #
    # After next refresh:
    # Sep-26 automatically becomes first
    # ------------------------------------------------------

    ordered_months = (
        month_order[
            "Disb Month"
        ]
        .tolist()
    )

    # ======================================================
    # MONTHLY LOAN DISBURSEMENT COUNT
    # ======================================================

    st.subheader(
        "📊 Monthly Loan Disbursement Count"
    )

    count_matrix = df.pivot_table(
        index=[
            "Loan Amount Bucket",
            "bucket_sort"
        ],
        columns="Disb Month",
        values="Loan Disb Count",
        aggfunc="sum",
        fill_value=0
    )

    # Latest month first
    count_matrix = count_matrix.reindex(
        columns=ordered_months,
        fill_value=0
    )

    # Reset index
    count_matrix = (
        count_matrix
        .reset_index()
        .sort_values(
            "bucket_sort"
        )
    )

    # Remove sort column
    count_matrix = count_matrix.drop(
        columns=[
            "bucket_sort"
        ]
    )

    # ======================================================
    # COUNT TOTAL
    # ======================================================

    count_total = (
        count_matrix
        .drop(
            columns=[
                "Loan Amount Bucket"
            ]
        )
        .sum()
    )

    count_total_row = pd.DataFrame(
        [
            ["TOTAL"] +
            count_total.tolist()
        ],
        columns=count_matrix.columns
    )

    count_display = pd.concat(
        [
            count_matrix,
            count_total_row
        ],
        ignore_index=True
    )

    # ======================================================
    # COUNT DISPLAY FORMAT
    # ======================================================

    count_display_formatted = count_display.copy()

    for col in count_display_formatted.columns[1:]:

        count_display_formatted[col] = (
            pd.to_numeric(
                count_display_formatted[col],
                errors="coerce"
            )
            .fillna(0)
            .map(
                lambda x:
                f"{x:,.0f}"
            )
        )

    # ======================================================
    # COUNT CONDITIONAL FORMATTING
    # ======================================================

    count_styled = apply_matrix_formatting(
        count_display
    )

    # Replace values with formatted values
    count_styled = (
        count_styled
        .hide(axis="index")
    )

    # Use formatted data with styling
    count_styled = apply_matrix_formatting(
        count_display_formatted
    )

    st.dataframe(
        count_styled,
        use_container_width=True,
        hide_index=True,
        height=470
    )

    # ======================================================
    # LEGEND
    # ======================================================

    st.markdown(
        """
        🟢 **High Disbursement** &nbsp;&nbsp;
        🟡 **Medium / Lower Disbursement** &nbsp;&nbsp;
        🟠 **Very Low Disbursement**
        """
    )

    # ======================================================
    # MONTHLY DISBURSEMENT AMOUNT
    # ======================================================

    st.subheader(
        "💵 Monthly Disbursement Amount (₹ Cr)"
    )

    amount_matrix = df.pivot_table(
        index=[
            "Loan Amount Bucket",
            "bucket_sort"
        ],
        columns="Disb Month",
        values="Amt Disb (Cr)",
        aggfunc="sum",
        fill_value=0
    )

    # Latest month first
    amount_matrix = amount_matrix.reindex(
        columns=ordered_months,
        fill_value=0
    )

    # Reset index
    amount_matrix = (
        amount_matrix
        .reset_index()
        .sort_values(
            "bucket_sort"
        )
    )

    # Remove sort column
    amount_matrix = amount_matrix.drop(
        columns=[
            "bucket_sort"
        ]
    )

    # ======================================================
    # AMOUNT TOTAL
    # ======================================================

    amount_total = (
        amount_matrix
        .drop(
            columns=[
                "Loan Amount Bucket"
            ]
        )
        .sum()
    )

    amount_total_row = pd.DataFrame(
        [
            ["TOTAL"] +
            amount_total.tolist()
        ],
        columns=amount_matrix.columns
    )

    amount_display = pd.concat(
        [
            amount_matrix,
            amount_total_row
        ],
        ignore_index=True
    )

    # ======================================================
    # AMOUNT DISPLAY FORMAT
    # ======================================================

    amount_display_formatted = amount_display.copy()

    for col in amount_display_formatted.columns[1:]:

        amount_display_formatted[col] = (
            pd.to_numeric(
                amount_display_formatted[col],
                errors="coerce"
            )
            .fillna(0)
            .map(
                lambda x:
                f"{x:,.2f}"
            )
        )

    # ======================================================
    # AMOUNT CONDITIONAL FORMATTING
    # ======================================================

    amount_styled = apply_matrix_formatting(
        amount_display_formatted
    )

    st.dataframe(
        amount_styled,
        use_container_width=True,
        hide_index=True,
        height=470
    )

    # ======================================================
    # RAW MV DATA
    # ======================================================

    with st.expander(
        "🔎 View ATS Disb MoM Data"
    ):

        raw_df = df[
            [
                "Month",
                "Disb Month",
                "Loan Amount Bucket",
                "Loan Disb Count",
                "Amt Disb (Cr)"
            ]
        ].copy()

        st.dataframe(
            raw_df,
            use_container_width=True,
            hide_index=True
        )

    # ======================================================
    # EXCEL DOWNLOAD
    # ======================================================

    output = BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:

        # --------------------------------------------------
        # Count Matrix
        # --------------------------------------------------

        count_matrix.to_excel(
            writer,
            sheet_name="Loan Disb Count",
            index=False
        )

        # --------------------------------------------------
        # Amount Matrix
        # --------------------------------------------------

        amount_matrix.to_excel(
            writer,
            sheet_name="Amt Disb Cr",
            index=False
        )

        # --------------------------------------------------
        # Raw Data
        # --------------------------------------------------

        raw_df.to_excel(
            writer,
            sheet_name="MV Data",
            index=False
        )

        # ==================================================
        # EXCEL FORMATTING
        # ==================================================

        from openpyxl.styles import (
            Font,
            PatternFill,
            Alignment
        )

        from openpyxl.formatting.rule import ColorScaleRule

        yellow_fill = PatternFill(
            fill_type="solid",
            fgColor="FFF2CC"
        )

        # --------------------------------------------------
        # Loop worksheets
        # --------------------------------------------------

        for ws in writer.book.worksheets:

            # ----------------------------------------------
            # Header
            # ----------------------------------------------

            for cell in ws[1]:

                cell.font = Font(
                    bold=True,
                    size=12
                )

                cell.alignment = Alignment(
                    horizontal="center",
                    vertical="center"
                )

            # ----------------------------------------------
            # TOTAL ROW
            # ----------------------------------------------

            total_row_number = None

            for row in ws.iter_rows():

                if (
                    row[0].value is not None
                    and str(
                        row[0].value
                    ).upper() == "TOTAL"
                ):

                    total_row_number = row[0].row

                    for cell in row:

                        cell.font = Font(
                            bold=True,
                            size=12
                        )

                        cell.fill = yellow_fill

                        cell.alignment = Alignment(
                            horizontal="center",
                            vertical="center"
                        )

            # ----------------------------------------------
            # Conditional formatting
            # ----------------------------------------------

            if (
                ws.title in [
                    "Loan Disb Count",
                    "Amt Disb Cr"
                ]
                and ws.max_column > 1
                and ws.max_row > 2
            ):

                start_row = 2

                end_row = (
                    total_row_number - 1
                    if total_row_number
                    else ws.max_row
                )

                if end_row >= start_row:

                    start_col = 2

                    end_col = ws.max_column

                    from openpyxl.utils import (
                        get_column_letter
                    )

                    cell_range = (
                        f"{get_column_letter(start_col)}"
                        f"{start_row}:"
                        f"{get_column_letter(end_col)}"
                        f"{end_row}"
                    )

                    # --------------------------------------
                    # Green = High
                    # Yellow = Medium
                    # Orange = Very Low
                    # --------------------------------------

                    color_rule = ColorScaleRule(
                        start_type="percentile",
                        start_value=33,
                        start_color="FCE4D6",

                        mid_type="percentile",
                        mid_value=50,
                        mid_color="FFF2CC",

                        end_type="percentile",
                        end_value=67,
                        end_color="C6EFCE"
                    )

                    ws.conditional_formatting.add(
                        cell_range,
                        color_rule
                    )

            # ----------------------------------------------
            # Column Width
            # ----------------------------------------------

            for column_cells in ws.columns:

                max_length = 0

                column_letter = (
                    column_cells[0]
                    .column_letter
                )

                for cell in column_cells:

                    if cell.value is not None:

                        max_length = max(
                            max_length,
                            len(
                                str(
                                    cell.value
                                )
                            )
                        )

                ws.column_dimensions[
                    column_letter
                ].width = min(
                    max(
                        max_length + 2,
                        12
                    ),
                    25
                )

    output.seek(0)

    # ======================================================
    # DOWNLOAD BUTTON
    # ======================================================

    st.download_button(
        label="⬇️ Download Excel",
        data=output.getvalue(),
        file_name="ATS_Disb_MoM.xlsx",
        mime=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        )
    )