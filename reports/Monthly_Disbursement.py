
import os
import time
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from config.db import engine


# ==========================================================
# CONFIGURATION
# ==========================================================

PREVIEW_LIMIT = 500
BATCH_SIZE = 2000
EXCEL_MAX_DATA_ROWS = 1_048_575
EXPORT_VERSION = "v3"


# ==========================================================
# DATABASE QUERY HELPER
# ==========================================================

def execute_query(query, params=None):

    for attempt in range(2):
        try:
            with engine.connect() as conn:
                return pd.read_sql_query(
                    query,
                    conn,
                    params=params or {}
                )

        except OperationalError:
            if attempt == 0:
                engine.dispose()
                time.sleep(1)
            else:
                raise


# ==========================================================
# COMMON DEDUPLICATION QUERY
# One row per non-null Account No. for the selected month
# ==========================================================

def unique_accounts_sql():

    return """
        SELECT DISTINCT ON ("Account No.") *
        FROM warburg_mom."Monthly Disbursement"
        WHERE "Month" = CAST(:selected_month AS date)
          AND "Account No." IS NOT NULL
        ORDER BY "Account No."
    """


# ==========================================================
# 1. KPI
# ==========================================================

@st.cache_data(ttl=300, show_spinner=False)
def load_monthly_kpis(month_key):

    query = text("""
        WITH account_level AS
        (
            SELECT
                "Account No.",
                MAX("Loan Amt. Disb"::numeric) AS disb_amount
            FROM warburg_mom."Monthly Disbursement"
            WHERE "Month" = CAST(:selected_month AS date)
              AND "Account No." IS NOT NULL
            GROUP BY "Account No."
        )
        SELECT
            COUNT(*) AS loan_count,
            COALESCE(SUM(disb_amount), 0) AS total_disbursed,
            COALESCE(
                SUM(disb_amount) / NULLIF(COUNT(*), 0),
                0
            ) AS ats
        FROM account_level
    """)

    result = execute_query(
        query,
        {"selected_month": month_key}
    )

    return result.iloc[0].to_dict()


# ==========================================================
# 2. EXPECTED EXPORT COUNT
# ==========================================================

@st.cache_data(ttl=300, show_spinner=False)
def load_export_count(month_key):

    query = text("""
        SELECT COUNT(DISTINCT "Account No.") AS account_count
        FROM warburg_mom."Monthly Disbursement"
        WHERE "Month" = CAST(:selected_month AS date)
          AND "Account No." IS NOT NULL
    """)

    result = execute_query(
        query,
        {"selected_month": month_key}
    )

    return int(result.iloc[0]["account_count"])


# ==========================================================
# 3. PREVIEW - MAXIMUM 5,000 UNIQUE ACCOUNTS
# ==========================================================

@st.cache_data(ttl=300, show_spinner=False)
def load_monthly_preview(month_key):

    query = text("""
        SELECT *
        FROM (
            SELECT DISTINCT ON ("Account No.") *
            FROM warburg_mom."Monthly Disbursement"
            WHERE "Month" = CAST(:selected_month AS date)
              AND "Account No." IS NOT NULL
            ORDER BY "Account No."
        ) AS unique_accounts
        LIMIT 5000
    """)

    return execute_query(
        query,
        {"selected_month": month_key}
    )


# ==========================================================
# 4. TEMPORARY FILE
# ==========================================================

def create_temp_file(suffix):

    file = tempfile.NamedTemporaryFile(
        prefix="monthly_disbursement_",
        suffix=suffix,
        delete=False
    )

    file_path = file.name
    file.close()

    return file_path


def remove_export(path_key, ready_key, count_key):

    old_path = st.session_state.pop(path_key, None)

    st.session_state.pop(ready_key, None)
    st.session_state.pop(count_key, None)

    if old_path and os.path.exists(old_path):
        try:
            os.remove(old_path)
        except OSError:
            pass


# ==========================================================
# 5. CSV EXPORT - DIRECT POSTGRESQL COPY
# No full pandas DataFrame
# ==========================================================

def export_csv(month_key, file_path):

    # month_key is generated internally from the selected date.
    copy_query = f"""
        COPY (
            SELECT DISTINCT ON ("Account No.") *
            FROM warburg_mom."Monthly Disbursement"
            WHERE "Month" = DATE '{month_key}'
              AND "Account No." IS NOT NULL
            ORDER BY "Account No."
        )
        TO STDOUT WITH (FORMAT CSV, HEADER TRUE, ENCODING 'UTF8')
    """

    raw_conn = None
    cursor = None

    try:
        raw_conn = engine.raw_connection()
        cursor = raw_conn.cursor()

        with open(file_path, "wb") as output_file:
            cursor.copy_expert(
                copy_query,
                output_file
            )

    finally:
        if cursor is not None:
            cursor.close()

        if raw_conn is not None:
            raw_conn.close()

    # Return data row count, excluding the CSV header.
    with open(file_path, "rb") as input_file:
        line_count = sum(1 for _ in input_file)

    return max(line_count - 1, 0)


# ==========================================================
# 6. EXCEL EXPORT - BATCH FETCH + WRITE-ONLY WORKBOOK
# ==========================================================

def export_excel(month_key, file_path):

    from openpyxl import Workbook

    query = text("""
        SELECT DISTINCT ON ("Account No.") *
        FROM warburg_mom."Monthly Disbursement"
        WHERE "Month" = CAST(:selected_month AS date)
          AND "Account No." IS NOT NULL
        ORDER BY "Account No."
    """)

    workbook = Workbook(write_only=True)

    worksheet = workbook.create_sheet("Disbursement")
    worksheet_rows = 0
    sheet_number = 1
    exported_rows = 0

    connection = None
    result = None

    try:
        connection = engine.connect().execution_options(
            stream_results=True,
            yield_per=BATCH_SIZE
        )

        result = connection.execute(
            query,
            {"selected_month": month_key}
        )

        headers = list(result.keys())
        worksheet.append(headers)

        while True:

            batch = result.fetchmany(BATCH_SIZE)

            if not batch:
                break

            for row in batch:

                if worksheet_rows >= EXCEL_MAX_DATA_ROWS:

                    sheet_number += 1

                    worksheet = workbook.create_sheet(
                        f"Disb_{sheet_number}"
                    )

                    worksheet.append(headers)
                    worksheet_rows = 0

                worksheet.append(list(row))

                worksheet_rows += 1
                exported_rows += 1

    finally:
        if result is not None:
            result.close()

        if connection is not None:
            connection.close()

    try:
        workbook.save(file_path)
    finally:
        workbook.close()

    return exported_rows


# ==========================================================
# 7. MAIN REPORT
# ==========================================================

def Monthly_Disbursement(selected_month):

    st.title("📊 Monthly Disbursement")

    selected_date = (
        pd.to_datetime(selected_month)
        + pd.offsets.MonthEnd(0)
    ).date()

    month_key = selected_date.isoformat()
    month_label = selected_date.strftime("%b_%Y")

    st.caption(
        f"Selected Month: {selected_date.strftime('%b-%Y')}"
    )

    # ------------------------------------------------------
    # KPI
    # ------------------------------------------------------

    try:
        with st.spinner("Calculating monthly KPIs..."):
            kpis = load_monthly_kpis(month_key)

    except Exception as exc:
        st.error("KPI loading failed.")
        st.exception(exc)
        return

    loan_count = int(kpis["loan_count"] or 0)
    total_disbursed = float(kpis["total_disbursed"] or 0)
    ats = float(kpis["ats"] or 0)

    col1, col2, col3 = st.columns(3)

    col1.metric("Loan Disb", f"{loan_count:,}")

    col2.metric(
        "Loan Amt. Disb",
        f"₹{total_disbursed / 10_000_000:,.2f} Cr"
    )

    col3.metric("ATS", f"₹{ats:,.2f}")

    st.divider()

    # ------------------------------------------------------
    # PREVIEW
    # ------------------------------------------------------

    st.subheader("Monthly Disbursement Details")

    try:
        with st.spinner("Loading preview..."):
            preview_df = load_monthly_preview(month_key)

    except Exception as exc:
        st.error("Preview loading failed.")
        st.exception(exc)
        return

    if preview_df.empty:
        st.warning("No records found for the selected month.")
        return

    st.caption(
        f"Preview rows: {len(preview_df):,} | "
        f"Columns: {len(preview_df.columns):,}"
    )

    st.dataframe(
        preview_df,
        use_container_width=True,
        height=450,
        hide_index=True
    )

    st.info(
        "Preview and exports contain one row per unique, non-null "
        "Account No. Exported rows should match the Loan Disb KPI."
    )

    st.divider()

    # ------------------------------------------------------
    # EXPORT SECTION
    # ------------------------------------------------------

    st.subheader("Download Complete Data")

    st.caption(
        f"Expected unique account rows: {loan_count:,}"
    )

    csv_path_key = f"{EXPORT_VERSION}_csv_path_{month_key}"
    csv_ready_key = f"{EXPORT_VERSION}_csv_ready_{month_key}"
    csv_count_key = f"{EXPORT_VERSION}_csv_count_{month_key}"

    excel_path_key = f"{EXPORT_VERSION}_excel_path_{month_key}"
    excel_ready_key = f"{EXPORT_VERSION}_excel_ready_{month_key}"
    excel_count_key = f"{EXPORT_VERSION}_excel_count_{month_key}"

    # ------------------------------------------------------
    # PREPARE CSV
    # ------------------------------------------------------

    if st.button(
        "Prepare Full CSV",
        key=f"{EXPORT_VERSION}_prepare_csv_{month_key}",
        use_container_width=True
    ):

        remove_export(
            csv_path_key,
            csv_ready_key,
            csv_count_key
        )

        csv_path = create_temp_file(".csv")

        try:
            with st.spinner(
                "Exporting unique accounts directly from PostgreSQL..."
            ):
                actual_count = export_csv(
                    month_key,
                    csv_path
                )

            st.session_state[csv_path_key] = csv_path
            st.session_state[csv_count_key] = actual_count
            st.session_state[csv_ready_key] = True

            if actual_count == loan_count:
                st.success(
                    f"CSV ready: {actual_count:,} data rows. "
                    "Count matches the KPI."
                )
            else:
                st.warning(
                    f"CSV contains {actual_count:,} rows, "
                    f"but KPI shows {loan_count:,}. "
                    "Please verify the source data."
                )

        except Exception as exc:

            if os.path.exists(csv_path):
                os.remove(csv_path)

            st.error("CSV export failed.")
            st.exception(exc)

    # ------------------------------------------------------
    # DOWNLOAD CSV
    # ------------------------------------------------------

    csv_path = st.session_state.get(csv_path_key)

    if (
        st.session_state.get(csv_ready_key)
        and csv_path
        and os.path.exists(csv_path)
    ):

        with open(csv_path, "rb") as file:
            csv_data = file.read()

        st.download_button(
            "⬇️ Download Full CSV",
            data=csv_data,
            file_name=f"Monthly_Disbursement_{month_label}.csv",
            mime="text/csv",
            key=f"{EXPORT_VERSION}_download_csv_{month_key}",
            use_container_width=True
        )

    st.divider()

    # ------------------------------------------------------
    # PREPARE EXCEL
    # ------------------------------------------------------

    if st.button(
        "Prepare Full Excel",
        key=f"{EXPORT_VERSION}_prepare_excel_{month_key}",
        use_container_width=True
    ):

        remove_export(
            excel_path_key,
            excel_ready_key,
            excel_count_key
        )

        excel_path = create_temp_file(".xlsx")

        try:
            with st.spinner(
                "Creating Excel in batches. Please wait..."
            ):
                actual_count = export_excel(
                    month_key,
                    excel_path
                )

            st.session_state[excel_path_key] = excel_path
            st.session_state[excel_count_key] = actual_count
            st.session_state[excel_ready_key] = True

            if actual_count == loan_count:
                st.success(
                    f"Excel ready: {actual_count:,} data rows. "
                    "Count matches the KPI."
                )
            else:
                st.warning(
                    f"Excel contains {actual_count:,} rows, "
                    f"but KPI shows {loan_count:,}. "
                    "Please verify the source data."
                )

        except Exception as exc:

            if os.path.exists(excel_path):
                os.remove(excel_path)

            st.error("Excel export failed.")
            st.exception(exc)

    # ------------------------------------------------------
    # DOWNLOAD EXCEL
    # ------------------------------------------------------

    excel_path = st.session_state.get(excel_path_key)

    if (
        st.session_state.get(excel_ready_key)
        and excel_path
        and os.path.exists(excel_path)
    ):

        with open(excel_path, "rb") as file:
            excel_data = file.read()

        st.download_button(
            "⬇️ Download Full Excel",
            data=excel_data,
            file_name=f"Monthly_Disbursement_{month_label}.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            key=f"{EXPORT_VERSION}_download_excel_{month_key}",
            use_container_width=True
        )
