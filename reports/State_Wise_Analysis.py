
import pandas as pd
import streamlit as st
from sqlalchemy import text
from config.db import engine
from io import BytesIO

from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.utils import get_column_letter


# ============================================================
# CONFIGURATION
# ============================================================

SOURCE_TABLE = "warburg_mom.branch_wise_analysis"
NAVY = "#08265F"
WHITE = "#FFFFFF"

DIMENSIONS = [
    ("State Wise PAR", "branch_state", "State", "State_Wise_PAR"),
    ("District Wise PAR", "branch_district", "District", "District_Wise_PAR"),
    ("Branch Wise PAR", "branch_with_code", "Branch", "Branch_Wise_PAR"),
    ("Branch Category Wise PAR", "branch_category", "Category", "Branch_Category_Wise_PAR"),
    ("Branch Type Wise PAR", "branch_type", "Type", "Branch_Type_Wise_PAR"),
]


# ============================================================
# LOAD DATA
# ============================================================

def load_par_data():
    query = text("""
        SELECT
            "Month" AS snapshot_month,
            TRIM("Branch With Code"::text) AS branch_with_code,
            TRIM("Branch Type"::text) AS branch_type,
            TRIM("Branch District"::text) AS branch_district,
            TRIM("Branch State"::text) AS branch_state,
            TRIM("Branch Category"::text) AS branch_category,
            COALESCE("Cumulative Disb", 0) AS cumulative_disb,
            COALESCE("PAR GT0 & Write_Off", 0) AS par_gt0_writeoff
        FROM warburg_mom.branch_wise_analysis
        WHERE "Month" IS NOT NULL
    """)

    with engine.connect() as connection:
        df = pd.read_sql(query, connection)

    if df.empty:
        return df

    df["snapshot_month"] = pd.to_datetime(
        df["snapshot_month"], errors="coerce"
    )

    for column in ["cumulative_disb", "par_gt0_writeoff"]:
        df[column] = pd.to_numeric(
            df[column], errors="coerce"
        ).fillna(0)

    for column in [
        "branch_with_code",
        "branch_type",
        "branch_district",
        "branch_state",
        "branch_category",
    ]:
        df[column] = (
            df[column].astype("string").str.strip()
            .replace("", pd.NA)
        )

    df = df.dropna(subset=["snapshot_month"]).copy()
    df["month_label"] = df["snapshot_month"].dt.strftime("%b-%y")

    return df


# ============================================================
# BUILD MATRIX
# ============================================================

def build_matrix(df, dimension_column):
    # dimension_column now matches the actual aliased DataFrame columns.
    if dimension_column not in df.columns:
        raise ValueError(
            f"Column '{dimension_column}' is missing from loaded data. "
            f"Available columns: {list(df.columns)}"
        )

    usable = df.dropna(subset=[dimension_column]).copy()

    if usable.empty:
        return pd.DataFrame(), [], {}

    month_order = (
        usable[["snapshot_month", "month_label"]]
        .drop_duplicates()
        .sort_values("snapshot_month", ascending=False)
        ["month_label"]
        .tolist()
    )

    grouped = (
        usable.groupby(
            [dimension_column, "month_label"],
            as_index=False,
            dropna=False,
        )
        .agg(
            cumulative_disb=("cumulative_disb", "sum"),
            par_gt0_writeoff=("par_gt0_writeoff", "sum"),
        )
    )

    # PAR 0% Disb with Write-off:
    # PAR GT0 & Write-off / Cumulative Disb * 100
    grouped["par_pct"] = (
        grouped["par_gt0_writeoff"]
        .div(
            grouped["cumulative_disb"].where(
                grouped["cumulative_disb"] != 0
            )
        )
        * 100
    )

    matrix = grouped.pivot(
        index=dimension_column,
        columns="month_label",
        values="par_pct",
    ).reindex(columns=month_order)

    matrix.index = matrix.index.astype(str)
    matrix.index.name = "Name"
    matrix.columns.name = None

    total_values = {}

    for month in month_order:
        month_df = usable[usable["month_label"] == month]

        total_disb = month_df["cumulative_disb"].sum()
        total_par = month_df["par_gt0_writeoff"].sum()

        total_values[month] = (
            total_par / total_disb * 100
            if total_disb != 0
            else float("nan")
        )

    return matrix, month_order, total_values


# ============================================================
# ROW-WISE CONDITIONAL FORMATTING
# ============================================================

def interpolate_color(start_hex, end_hex, ratio):
    start = tuple(int(start_hex[i:i + 2], 16) for i in (1, 3, 5))
    end = tuple(int(end_hex[i:i + 2], 16) for i in (1, 3, 5))

    rgb = tuple(
        round(a + (b - a) * ratio)
        for a, b in zip(start, end)
    )

    return "#{:02X}{:02X}{:02X}".format(*rgb)


def row_color(value, minimum, maximum):
    if pd.isna(value):
        return "#FFFFFF"

    if maximum == minimum:
        return "#FFEB84"

    ratio = (value - minimum) / (maximum - minimum)

    if ratio <= 0.5:
        return interpolate_color("#63BE7B", "#FFEB84", ratio * 2)

    return interpolate_color("#FFEB84", "#F8696B", (ratio - 0.5) * 2)


def style_detail_row(row):
    values = pd.to_numeric(row, errors="coerce")
    valid = values.dropna()

    if valid.empty:
        return [""] * len(row)

    minimum, maximum = valid.min(), valid.max()
    styles = []

    for value in values:
        if pd.isna(value):
            styles.append("background-color: #FFFFFF; color: #000000;")
        else:
            bg = row_color(value, minimum, maximum)
            styles.append(
                f"background-color: {bg}; "
                "color: #000000; font-weight: bold;"
            )

    return styles


def style_headers(styler):
    return styler.set_table_styles([
        {
            "selector": "th",
            "props": [
                ("background-color", NAVY),
                ("color", WHITE),
                ("font-weight", "bold"),
                ("text-align", "center"),
                ("padding", "7px"),
                ("white-space", "nowrap"),
            ],
        },
        {
            "selector": "th.row_heading",
            "props": [
                ("background-color", NAVY),
                ("color", WHITE),
                ("font-weight", "bold"),
                ("text-align", "left"),
                ("min-width", "190px"),
                ("white-space", "nowrap"),
            ],
        },
        {
            "selector": "td",
            "props": [
                ("text-align", "right"),
                ("font-size", "13px"),
                ("padding", "7px"),
                ("white-space", "nowrap"),
            ],
        },
    ])


# ============================================================
# DISPLAY MATRIX
# ============================================================

def display_matrix(matrix, title, month_order, total_values, key):
    st.subheader(title)

    if matrix.empty:
        st.info(f"No data available for {title}.")
        return

    # Use Name as a normal column (not the dataframe index) in both tables.
    # This keeps the Total table and detail table columns aligned.
    sorted_matrix = matrix.sort_index(ascending=True)
    total_df = pd.DataFrame([{"Name": "Total", **total_values}])
    detail_df = sorted_matrix.reset_index()
    detail_df.columns = ["Name"] + month_order

    column_config = {
        "Name": st.column_config.TextColumn("Name", width="medium"),
        **{
            month: st.column_config.NumberColumn(
                month, width="small", format="%.2f%%"
            )
            for month in month_order
        },
    }

    total_style = (
        total_df.style
        .format({m: "{:.2f}%" for m in month_order}, na_rep="—")
        .set_properties(**{
            "background-color": NAVY,
            "color": WHITE,
            "font-weight": "bold",
            "text-align": "right",
            "font-size": "13px",
            "padding": "7px",
        })
        .set_properties(subset=["Name"], **{
            "text-align": "left",
            "min-width": "190px",
        })
    )
    total_style = style_headers(total_style)

    st.dataframe(
        total_style,
        use_container_width=True,
        hide_index=True,
        column_config=column_config,
        height=75,
        key=f"{key}_total",
    )

    detail_style = (
        detail_df.style
        .format({m: "{:.2f}%" for m in month_order}, na_rep="—")
        .apply(lambda row: [""] + style_detail_row(row[1:]), axis=1)
        .set_properties(subset=["Name"], **{
            "text-align": "left",
            "min-width": "190px",
            "font-weight": "bold",
        })
    )
    detail_style = style_headers(detail_style)

    st.dataframe(
        detail_style,
        use_container_width=True,
        hide_index=True,
        column_config=column_config,
        height=min(800, max(100, 38 + len(detail_df) * 34)),
        key=f"{key}_detail",
    )


# ============================================================
# EXCEL EXPORT - INDIVIDUAL FILE PER MATRIX
# ============================================================

def create_excel_for_dimension(df, dimension_column, sheet_name):
    """Create a formatted Excel workbook for one matrix."""
    output = BytesIO()
    matrix, month_order, total_values = build_matrix(df, dimension_column)

    if matrix.empty:
        return None

    # Match the dashboard: detail rows sorted alphabetically.
    matrix = matrix.sort_index(ascending=True)

    export_df = matrix.reset_index()
    export_df.columns = ["Name"] + month_order

    # Keep Total at the top, separate from detail rows.
    total_row = {"Name": "Total", **total_values}
    export_df = pd.concat(
        [pd.DataFrame([total_row]), export_df],
        ignore_index=True,
    )

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export_df.to_excel(writer, sheet_name=sheet_name, index=False)

        ws = writer.sheets[sheet_name]
        ws.freeze_panes = "B2"
        ws.auto_filter.ref = ws.dimensions
        ws.sheet_view.showGridLines = False

        navy_fill = PatternFill("solid", fgColor=NAVY.lstrip("#"))
        white_font = Font(bold=True, color="FFFFFF")
        black_font = Font(bold=True, color="000000")
        thin = Side(style="thin", color="D9E1F2")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        # Header row.
        for cell in ws[1]:
            cell.fill = navy_fill
            cell.font = white_font
            cell.alignment = Alignment(
                horizontal="center", vertical="center", wrap_text=True
            )
            cell.border = border

        ws.row_dimensions[1].height = 24
        ws.column_dimensions["A"].width = 30

        for col_idx in range(2, ws.max_column + 1):
            letter = get_column_letter(col_idx)
            ws.column_dimensions[letter].width = 14

            for row_idx in range(2, ws.max_row + 1):
                cell = ws.cell(row_idx, col_idx)
                cell.number_format = '0.00"%"'
                cell.alignment = Alignment(horizontal="right")
                cell.border = border

        # Total row formatting.
        for cell in ws[2]:
            cell.fill = navy_fill
            cell.font = white_font
            cell.border = border
        ws.row_dimensions[2].height = 22

        # Detail names and row-wise conditional formatting.
        for row_idx in range(3, ws.max_row + 1):
            ws.cell(row_idx, 1).font = black_font
            ws.cell(row_idx, 1).alignment = Alignment(horizontal="left")
            ws.cell(row_idx, 1).border = border

            if ws.max_column >= 2:
                # Each row gets its own green-yellow-red scale across months.
                ws.conditional_formatting.add(
                    f"B{row_idx}:{get_column_letter(ws.max_column)}{row_idx}",
                    ColorScaleRule(
                        start_type="min",
                        start_color="63BE7B",
                        mid_type="percentile",
                        mid_value=50,
                        mid_color="FFEB84",
                        end_type="max",
                        end_color="F8696B",
                    ),
                )

    output.seek(0)
    return output.getvalue()


def create_all_matrices_excel(df):
    """Create one formatted workbook with all five matrix sheets."""
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for title, dimension_column, sheet_name, file_stem in DIMENSIONS:
            matrix, month_order, total_values = build_matrix(df, dimension_column)
            if matrix.empty:
                continue

            matrix = matrix.sort_index(ascending=True)
            export_df = matrix.reset_index()
            export_df.columns = ["Name"] + month_order

            total_row = {"Name": "Total", **total_values}
            export_df = pd.concat(
                [pd.DataFrame([total_row]), export_df],
                ignore_index=True,
            )
            export_df.to_excel(writer, sheet_name=sheet_name, index=False)

            ws = writer.sheets[sheet_name]
            ws.freeze_panes = "B2"
            ws.auto_filter.ref = ws.dimensions
            ws.sheet_view.showGridLines = False

            navy_fill = PatternFill("solid", fgColor=NAVY.lstrip("#"))
            white_font = Font(bold=True, color="FFFFFF")
            black_font = Font(bold=True, color="000000")
            thin = Side(style="thin", color="D9E1F2")
            border = Border(left=thin, right=thin, top=thin, bottom=thin)

            for cell in ws[1]:
                cell.fill = navy_fill
                cell.font = white_font
                cell.alignment = Alignment(
                    horizontal="center", vertical="center", wrap_text=True
                )
                cell.border = border

            ws.row_dimensions[1].height = 24
            ws.column_dimensions["A"].width = 30

            for col_idx in range(2, ws.max_column + 1):
                letter = get_column_letter(col_idx)
                ws.column_dimensions[letter].width = 14
                for row_idx in range(2, ws.max_row + 1):
                    cell = ws.cell(row_idx, col_idx)
                    cell.number_format = '0.00"%"'
                    cell.alignment = Alignment(horizontal="right")
                    cell.border = border

            for cell in ws[2]:
                cell.fill = navy_fill
                cell.font = white_font
                cell.border = border
            ws.row_dimensions[2].height = 22

            for row_idx in range(3, ws.max_row + 1):
                ws.cell(row_idx, 1).font = black_font
                ws.cell(row_idx, 1).alignment = Alignment(horizontal="left")
                ws.cell(row_idx, 1).border = border
                if ws.max_column >= 2:
                    ws.conditional_formatting.add(
                        f"B{row_idx}:{get_column_letter(ws.max_column)}{row_idx}",
                        ColorScaleRule(
                            start_type="min",
                            start_color="63BE7B",
                            mid_type="percentile",
                            mid_value=50,
                            mid_color="FFEB84",
                            end_type="max",
                            end_color="F8696B",
                        ),
                    )

        if not writer.sheets:
            pd.DataFrame({"Message": ["No data available"]}).to_excel(
                writer, sheet_name="No Data", index=False
            )

    output.seek(0)
    return output.getvalue()


# ============================================================
# MAIN REPORT
# ============================================================

def render_report(selected_month=None):
    # No duplicate page title or source caption; section headings identify each matrix.
    try:
        df = load_par_data()
    except Exception as exc:
        st.error(f"Unable to load PAR analysis data: {exc}")
        st.info(
            "Expected source: warburg_mom.branch_wise_analysis. "
            "Verify its column names and SELECT permission."
        )
        return

    if df.empty:
        st.warning("No data found in warburg_mom.branch_wise_analysis.")
        return

    excel_mime = (
        "application/vnd.openxmlformats-officedocument."
        "spreadsheetml.sheet"
    )

    # Individual matrix display and download.
    for title, dimension_column, sheet_name, file_stem in DIMENSIONS:
        matrix, month_order, total_values = build_matrix(df, dimension_column)

        display_matrix(
            matrix,
            title,
            month_order,
            total_values,
            file_stem,
        )

        try:
            excel_data = create_excel_for_dimension(
                df, dimension_column, sheet_name
            )
            if excel_data is not None:
                st.download_button(
                    label=f"Download {title} Excel",
                    data=excel_data,
                    file_name=f"{file_stem}.xlsx",
                    mime=excel_mime,
                    key=f"{file_stem}_excel_download",
                )
        except Exception as exc:
            st.error(f"Unable to create Excel for {title}: {exc}")

    # One combined workbook containing all five matrices as separate sheets.
    try:
        all_excel_data = create_all_matrices_excel(df)
        st.download_button(
            label="Download All Matrices Excel",
            data=all_excel_data,
            file_name="All_Matrices_PAR.xlsx",
            mime=excel_mime,
            key="all_matrices_excel_download",
            type="primary",
        )
    except Exception as exc:
        st.error(f"Unable to create combined Excel file: {exc}")

