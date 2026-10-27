import streamlit as st
import pandas as pd

from sqlalchemy import text
from html import escape
from io import BytesIO

from config.db import engine


# ==========================================================
# INDIAN NUMBER FORMAT
# ==========================================================

def indian_number(value, decimals=0):

    try:
        value = float(value)
    except (TypeError, ValueError):
        return "0"

    negative = value < 0
    value = abs(value)

    if decimals > 0:

        formatted = f"{value:.{decimals}f}"

        integer_part, decimal_part = formatted.split(".")

    else:

        integer_part = f"{value:.0f}"
        decimal_part = ""

    # Indian comma formatting
    if len(integer_part) > 3:

        last_three = integer_part[-3:]
        remaining = integer_part[:-3]

        groups = []

        while len(remaining) > 2:

            groups.insert(
                0,
                remaining[-2:]
            )

            remaining = remaining[:-2]

        if remaining:

            groups.insert(
                0,
                remaining
            )

        integer_part = ",".join(
            groups + [last_three]
        )

    result = integer_part

    if decimals > 0:

        result = (
            result
            + "."
            + decimal_part
        )

    if negative:

        result = "-" + result

    return result


# ==========================================================
# EXCEL FILE CREATION
# ==========================================================

def create_excel_file(
    df,
    selected_month_date,
    total_mob,
    total_loan_count,
    total_pos,
    total_cumulative_disb,
    total_par_0_disb
):

    from openpyxl.styles import (
        Font,
        PatternFill,
        Alignment,
        Border,
        Side
    )

    # ------------------------------------------------------
    # COPY DATA
    # ------------------------------------------------------

    excel_df = df.copy()

    # ------------------------------------------------------
    # REMOVE TECHNICAL COLUMN
    # ------------------------------------------------------

    if "bucket_sort" in excel_df.columns:

        excel_df = excel_df.drop(
            columns=["bucket_sort"]
        )

    # ------------------------------------------------------
    # RENAME COLUMNS
    # ------------------------------------------------------

    excel_df = excel_df.rename(
        columns={
            "Loan Bucket": "Loan Amount",
            "POS": "POS (Cr)",
            "Cumulative Disb":
                "Cumulative Disb (Cr)",
            "PAR 0% on DISB":
                "PAR 0% on DISB"
        }
    )

    # ------------------------------------------------------
    # REQUIRED COLUMN ORDER
    #
    # Month ALREADY EXISTS IN df.
    # DO NOT INSERT IT AGAIN.
    # ------------------------------------------------------

    required_columns = [
        "Month",
        "Loan Amount",
        "MOB",
        "Loan Count",
        "POS (Cr)",
        "Cumulative Disb (Cr)",
        "PAR 0% on DISB"
    ]

    existing_columns = [
        column
        for column in required_columns
        if column in excel_df.columns
    ]

    excel_df = excel_df[
        existing_columns
    ]

    # ------------------------------------------------------
    # FORMAT MONTH
    # ------------------------------------------------------

    if "Month" in excel_df.columns:

        excel_df["Month"] = pd.to_datetime(
            excel_df["Month"],
            errors="coerce"
        ).dt.strftime(
            "%Y-%m-%d"
        )

    # ------------------------------------------------------
    # TOTAL ROW
    # ------------------------------------------------------

    total_df = pd.DataFrame(
        [{
            "Month":
                selected_month_date.strftime(
                    "%Y-%m-%d"
                ),

            "Loan Amount":
                "Total",

            "MOB":
                round(
                    total_mob,
                    2
                ),

            "Loan Count":
                int(
                    total_loan_count
                ),

            "POS (Cr)":
                round(
                    total_pos,
                    2
                ),

            "Cumulative Disb (Cr)":
                round(
                    total_cumulative_disb,
                    2
                ),

            "PAR 0% on DISB":
                round(
                    total_par_0_disb,
                    2
                )
        }]
    )

    # ------------------------------------------------------
    # COMBINE
    # ------------------------------------------------------

    excel_df = pd.concat(
        [
            excel_df,
            total_df
        ],
        ignore_index=True
    )

    # ------------------------------------------------------
    # CREATE EXCEL
    # ------------------------------------------------------

    output = BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:

        excel_df.to_excel(
            writer,
            index=False,
            sheet_name="ATS Analysis"
        )

        worksheet = writer.sheets[
            "ATS Analysis"
        ]

        # ==================================================
        # FILLS
        # ==================================================

        header_fill = PatternFill(
            fill_type="solid",
            fgColor="D9EAF7"
        )

        total_fill = PatternFill(
            fill_type="solid",
            fgColor="FFE680"
        )

        # ==================================================
        # BORDER
        # ==================================================

        thin_side = Side(
            style="thin",
            color="D9D9D9"
        )

        thin_border = Border(
            bottom=thin_side
        )

        # ==================================================
        # HEADER
        # ==================================================

        for cell in worksheet[1]:

            cell.font = Font(
                name="Arial",
                size=16,
                bold=True
            )

            cell.fill = header_fill

            cell.alignment = Alignment(
                horizontal="center",
                vertical="center"
            )

            cell.border = thin_border

        worksheet.row_dimensions[
            1
        ].height = 30

        # ==================================================
        # BODY
        # ==================================================

        total_row_number = (
            worksheet.max_row
        )

        for row in worksheet.iter_rows(
            min_row=2,
            max_row=total_row_number
        ):

            for cell in row:

                cell.font = Font(
                    name="Arial",
                    size=12
                )

                cell.border = thin_border

                cell.alignment = Alignment(
                    vertical="center"
                )

        # ==================================================
        # TOTAL ROW
        # ==================================================

        for cell in worksheet[
            total_row_number
        ]:

            cell.font = Font(
                name="Arial",
                size=16,
                bold=True
            )

            cell.fill = total_fill

            cell.alignment = Alignment(
                horizontal="center",
                vertical="center"
            )

        worksheet.row_dimensions[
            total_row_number
        ].height = 30

        # ==================================================
        # COLUMN MAP
        # ==================================================

        column_map = {}

        for cell in worksheet[1]:

            column_map[
                cell.value
            ] = cell.column

        # ==================================================
        # MOB FORMAT
        # ==================================================

        if "MOB" in column_map:

            col = column_map["MOB"]

            for row_number in range(
                2,
                total_row_number + 1
            ):

                worksheet.cell(
                    row=row_number,
                    column=col
                ).number_format = "0.00"

        # ==================================================
        # LOAN COUNT FORMAT
        # ==================================================

        if "Loan Count" in column_map:

            col = column_map[
                "Loan Count"
            ]

            for row_number in range(
                2,
                total_row_number + 1
            ):

                worksheet.cell(
                    row=row_number,
                    column=col
                ).number_format = "#,##0"

        # ==================================================
        # POS FORMAT
        # ==================================================

        if "POS (Cr)" in column_map:

            col = column_map[
                "POS (Cr)"
            ]

            for row_number in range(
                2,
                total_row_number + 1
            ):

                worksheet.cell(
                    row=row_number,
                    column=col
                ).number_format = "#,##0.00"

        # ==================================================
        # CUMULATIVE DISB FORMAT
        # ==================================================

        if "Cumulative Disb (Cr)" in column_map:

            col = column_map[
                "Cumulative Disb (Cr)"
            ]

            for row_number in range(
                2,
                total_row_number + 1
            ):

                worksheet.cell(
                    row=row_number,
                    column=col
                ).number_format = "#,##0.00"

        # ==================================================
        # PAR 0% ON DISB
        #
        # Database value = 1.22
        # Excel percentage = 1.22%
        #
        # Excel internally needs 0.0122
        # ==================================================

        if "PAR 0% on DISB" in column_map:

            col = column_map[
                "PAR 0% on DISB"
            ]

            for row_number in range(
                2,
                total_row_number + 1
            ):

                cell = worksheet.cell(
                    row=row_number,
                    column=col
                )

                try:

                    value = float(
                        cell.value
                    )

                    cell.value = (
                        value / 100
                    )

                    cell.number_format = (
                        "0.00%"
                    )

                except (
                    TypeError,
                    ValueError
                ):

                    pass

        # ==================================================
        # EXCEL COLUMN WIDTH
        # ==================================================

        column_widths = {

            "A": 15,   # Month

            "B": 26,   # Loan Amount

            "C": 12,   # MOB

            "D": 18,   # Loan Count

            "E": 16,   # POS

            "F": 24,   # Cumulative Disb

            "G": 22    # PAR
        }

        for column, width in column_widths.items():

            worksheet.column_dimensions[
                column
            ].width = width

        # ==================================================
        # ALIGNMENT
        # ==================================================

        for row in worksheet.iter_rows(
            min_row=2,
            max_row=total_row_number
        ):

            # Month
            row[0].alignment = Alignment(
                horizontal="center",
                vertical="center"
            )

            # Loan Amount
            row[1].alignment = Alignment(
                horizontal="left",
                vertical="center"
            )

            # Numeric columns
            for cell in row[2:]:

                cell.alignment = Alignment(
                    horizontal="right",
                    vertical="center"
                )

        # ==================================================
        # FREEZE HEADER
        # ==================================================

        worksheet.freeze_panes = "A2"

        # ==================================================
        # FILTER
        # ==================================================

        worksheet.auto_filter.ref = (
            worksheet.dimensions
        )

    output.seek(0)

    return output.getvalue()


# ==========================================================
# ATS ANALYSIS
# ==========================================================

def ATS_Analysis(selected_month):

    # ======================================================
    # TITLE
    # ======================================================

    st.markdown(
        "## 💰 ATS Analysis"
    )

    # ======================================================
    # SELECTED MONTH
    # ======================================================

    try:

        selected_month_date = (
            pd.to_datetime(
                selected_month
            ).date()
        )

    except Exception:

        st.error(
            f"Invalid selected month: "
            f"{selected_month}"
        )

        return

    # ======================================================
    # SQL
    #
    # IMPORTANT:
    # These are the ACTUAL MV columns.
    # ======================================================

    query = text(
        """
        SELECT

            "Month",

            "Loan Bucket",

            "MOB",

            "Loan Count",

            "POS",

            "Cumulative Disb",

            "PAR 0% on DISB",

            bucket_sort

        FROM warburg_mom.ats_analysis

        WHERE "Month" = :selected_month

        ORDER BY
            bucket_sort ASC
        """
    )

    # ======================================================
    # LOAD DATA
    # ======================================================

    try:

        df = pd.read_sql_query(
            query,
            engine,
            params={
                "selected_month":
                    selected_month_date
            }
        )

    except Exception as exc:

        st.error(
            f"Unable to load ATS Analysis: "
            f"{exc}"
        )

        return

    # ======================================================
    # NO DATA
    # ======================================================

    if df.empty:

        st.warning(
            f"No ATS data available for "
            f"{selected_month_date.strftime('%d-%b-%Y')}."
        )

        return

    # ======================================================
    # SORT
    # ======================================================

    df = (
        df
        .sort_values(
            "bucket_sort"
        )
        .reset_index(
            drop=True
        )
    )

    # ======================================================
    # NUMERIC CONVERSION
    # ======================================================

    numeric_columns = [
        "MOB",
        "Loan Count",
        "POS",
        "Cumulative Disb",
        "PAR 0% on DISB"
    ]

    for column in numeric_columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        ).fillna(0)

    # ======================================================
    # TOTAL POS
    # ======================================================

    total_pos = df[
        "POS"
    ].sum()

    # ======================================================
    # TOTAL CUMULATIVE DISB
    # ======================================================

    total_cumulative_disb = df[
        "Cumulative Disb"
    ].sum()

    # ======================================================
    # TOTAL LOAN COUNT
    # ======================================================

    total_loan_count = df[
        "Loan Count"
    ].sum()

    # ======================================================
    # TOTAL MOB
    #
    # Weighted Average MOB
    # using Cumulative Disb
    # ======================================================

    if total_cumulative_disb > 0:

        total_mob = (

            (
                df["MOB"]
                *
                df["Cumulative Disb"]
            ).sum()

            /

            total_cumulative_disb

        )

    else:

        total_mob = 0

    # ======================================================
    # TOTAL PAR 0% ON DISB
    # ======================================================

    if total_cumulative_disb > 0:

        total_par_0_disb = (

            (
                df["PAR 0% on DISB"]
                *
                df["Cumulative Disb"]
            ).sum()

            /

            total_cumulative_disb

        )

    else:

        total_par_0_disb = 0

    # ======================================================
    # CSS
    # ======================================================

    st.markdown(
        """
        <style>

        /* =================================================
           KPI
           ================================================= */

        .ats-kpi-container {

            width: 100%;

            display: flex;

            justify-content: space-between;

            gap: 35px;

            margin-top: 5px;

            margin-bottom: 25px;
        }


        .ats-kpi {

            flex: 1;
        }


        .ats-kpi-label {

            font-size: 16px;

            font-weight: 800;

            color: #172033;

            margin-bottom: 7px;
        }


        .ats-kpi-value {

            font-size: 30px;

            font-weight: 500;

            color: #172033;

            line-height: 1.1;
        }


        .ats-divider {

            border-top: 1px solid #dddddd;

            margin: 15px 0 28px 0;
        }


        /* =================================================
           DOWNLOAD BUTTON
           ================================================= */

        .ats-download {

            margin-top: 0px;

            margin-bottom: 12px;
        }


        /* =================================================
           TABLE
           ================================================= */

        .ats-table-wrapper {
            width: 100%;
            overflow: hidden;
            margin-top: 5px;
            margin-bottom: 10px;
        }

        .ats-table {
            width: 100%;
            border-collapse: collapse;
            table-layout: fixed;
            font-family: Arial, sans-serif;
            font-size: 13px;
            border: 1px solid #d9d9d9;
            border-radius: 7px;
            overflow: hidden;
        }

        .ats-table thead th {
            background: #f5f7fa;
            color: #344054;
            font-size: 14px;
            font-weight: 700;
            padding: 8px 10px;
            border-bottom: 1px solid #d9d9d9;
            text-align: right;
            white-space: nowrap;
        }

        .ats-table thead th:first-child,
        .ats-table tbody td:first-child {
            text-align: left;
        }

        .ats-table tbody td {
            padding: 7px 10px;
            border-bottom: 1px solid #eeeeee;
            color: #344054;
            text-align: right;
            white-space: nowrap;
        }

        .ats-table th:nth-child(1), .ats-table td:nth-child(1) { width: 22%; }
        .ats-table th:nth-child(2), .ats-table td:nth-child(2) { width: 11%; }
        .ats-table th:nth-child(3), .ats-table td:nth-child(3) { width: 13%; }
        .ats-table th:nth-child(4), .ats-table td:nth-child(4) { width: 15%; }
        .ats-table th:nth-child(5), .ats-table td:nth-child(5) { width: 18%; }
        .ats-table th:nth-child(6), .ats-table td:nth-child(6) { width: 14%; }

        .ats-total-row td {
            background-color: #ffe680 !important;
            color: #1f2937 !important;
            font-weight: 800 !important;
            font-size: 14px !important;
            border-top: 2px solid #d4b000 !important;
            border-bottom: none !important;
            padding-top: 8px !important;
            padding-bottom: 8px !important;
        }

        </style>
        """,
        unsafe_allow_html=True
    )

    # ======================================================
    # KPI HTML
    # ======================================================

    kpi_html = f"""

    <div class="ats-kpi-container">

        <div class="ats-kpi">

            <div class="ats-kpi-label">
                POS (Cr)
            </div>

            <div class="ats-kpi-value">
                {indian_number(
                    total_pos,
                    2
                )}
            </div>

        </div>


        <div class="ats-kpi">

            <div class="ats-kpi-label">
                Cumulative Disb (Cr)
            </div>

            <div class="ats-kpi-value">
                {indian_number(
                    total_cumulative_disb,
                    2
                )}
            </div>

        </div>


        <div class="ats-kpi">

            <div class="ats-kpi-label">
                Loan Count
            </div>

            <div class="ats-kpi-value">
                {indian_number(
                    total_loan_count,
                    0
                )}
            </div>

        </div>


        <div class="ats-kpi">

            <div class="ats-kpi-label">
                PAR 0% on DISB
            </div>

            <div class="ats-kpi-value">
                {total_par_0_disb:.2f}%
            </div>

        </div>

    </div>

    <div class="ats-divider"></div>

    """

    st.html(
        kpi_html
    )

    # ======================================================
    # TITLE + DOWNLOAD BUTTON
    # ======================================================

    title_col, download_col = st.columns(
        [7, 1]
    )

    with title_col:

        st.markdown(
            "### New Book - ATS"
        )

    # ======================================================
    # CREATE EXCEL
    # ======================================================

    excel_data = create_excel_file(
        df,
        selected_month_date,
        total_mob,
        total_loan_count,
        total_pos,
        total_cumulative_disb,
        total_par_0_disb
    )

    with download_col:

        st.download_button(
            label="📥 Excel",
            data=excel_data,
            file_name=(
                "ATS_Analysis_"
                f"{selected_month_date.strftime('%b-%Y')}.xlsx"
            ),
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            use_container_width=True
        )

    # ======================================================
    # TABLE ROWS
    # ======================================================

    rows_html = ""

    for _, row in df.iterrows():
        bucket = escape(str(row["Loan Bucket"]))
        mob = indian_number(row["MOB"], 2)
        loan_count = indian_number(row["Loan Count"], 0)
        pos = indian_number(row["POS"], 2)
        cumulative_disb = indian_number(row["Cumulative Disb"], 2)
        par_value = float(row["PAR 0% on DISB"])
        par = "-" if par_value == 0 else f"{par_value:.2f}%"
        rows_html += f"""
        <tr><td>{bucket}</td><td>{mob}</td><td>{loan_count}</td>
        <td>{pos}</td><td>{cumulative_disb}</td><td>{par}</td></tr>
        """

    total_row = f"""
    <tr class="ats-total-row">
        <td>Total</td>
        <td>{indian_number(total_mob, 2)}</td>
        <td>{indian_number(total_loan_count, 0)}</td>
        <td>{indian_number(total_pos, 2)}</td>
        <td>{indian_number(total_cumulative_disb, 2)}</td>
        <td>{total_par_0_disb:.2f}%</td>
    </tr>
    """

    table_html = f"""
    <div class="ats-table-wrapper">
        <table class="ats-table">
            <thead><tr>
                <th>Loan Amount</th><th>MOB</th><th>Loan Count</th>
                <th>POS (Cr)</th><th>Cumulative Disb (Cr)</th>
                <th>PAR 0% on DISB</th>
            </tr></thead>
            <tbody>{rows_html}{total_row}</tbody>
        </table>
    </div>
    """
    st.html(table_html)
