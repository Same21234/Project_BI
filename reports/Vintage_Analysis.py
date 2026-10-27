"""Power BI aligned vintage matrix sourced from the Vintage MOB materialized view."""

import pandas as pd
import streamlit as st
from sqlalchemy import text

from config.db import engine


SOURCE = 'warburg_mom."Vintage_MOB_2slicer"'
MAX_MOB = 23


def _set_vintage_months_selected(month_options, selected):
    """Select or clear every month before rendering the month checkboxes."""
    st.session_state["vintage_disbursement_months"] = (
        list(month_options) if selected else []
    )
    for month in month_options:
        st.session_state[f"vintage_month_{month}"] = selected


def _sync_vintage_month_selection(month_options, month):
    """Keep the selection list and Select all checkbox in sync."""
    key = "vintage_disbursement_months"
    selected = set(st.session_state.get(key, []))
    month_key = f"vintage_month_{month}"
    if st.session_state[month_key]:
        selected.add(month)
    else:
        selected.discard(month)
    st.session_state[key] = [value for value in month_options if value in selected]


@st.cache_data(ttl=900, show_spinner=False)
def _load_filter_dimensions():
    """Load only the month/state/category values exposed by the MV."""
    query = text(f"""
        SELECT DISTINCT
               mmm_yy,
               to_date('01-' || mmm_yy, 'DD-Mon-YY')::date AS cohort_month,
               branch_state,
               branch_category
        FROM {SOURCE}
        ORDER BY cohort_month, branch_state, branch_category
    """)
    with engine.connect() as connection:
        return pd.read_sql_query(query, connection)


@st.cache_data(ttl=900, show_spinner=False)
def _load_vintage_data(state=None, branch_category=None, disb_months=()):
    """Return the filtered cohort x MOB matrix inputs, aggregated in PostgreSQL."""
    conditions = []
    params = {"max_mob": MAX_MOB}
    if state is not None:
        conditions.append("branch_state = :state")
        params["state"] = state
    if branch_category is not None:
        conditions.append("branch_category = :branch_category")
        params["branch_category"] = branch_category
    if disb_months:
        conditions.append("mmm_yy = ANY(CAST(:disb_months AS text[]))")
        params["disb_months"] = list(disb_months)
    where_sql = " AND ".join(conditions) if conditions else "TRUE"

    query = text(f"""
        WITH filtered AS (
            SELECT mmm_yy,
                   to_date('01-' || mmm_yy, 'DD-Mon-YY')::date AS cohort_month,
                   branch_state,
                   branch_category,
                   snapshot_date,
                   amt_disb_cr,
                   par_0_wf_amt_cr,
                   par_snapshot_disb_cr
            FROM {SOURCE}
            WHERE {where_sql}
        ),
        disb_by_slice AS (
            SELECT mmm_yy, cohort_month, branch_state, branch_category,
                   MAX(amt_disb_cr) AS disb_amount_cr
            FROM filtered
            GROUP BY mmm_yy, cohort_month, branch_state, branch_category
        ),
        cohort_disb AS (
            SELECT mmm_yy, cohort_month,
                   SUM(disb_amount_cr) AS disb_amount_cr
            FROM disb_by_slice
            GROUP BY mmm_yy, cohort_month
        ),
        cohort_months AS (
            SELECT DISTINCT mmm_yy, cohort_month
            FROM filtered
        ),
        performance AS (
            SELECT mmm_yy, snapshot_date,
                   SUM(par_0_wf_amt_cr) AS par_amount_cr,
                   SUM(par_snapshot_disb_cr) AS par_snapshot_disb_cr
            FROM filtered
            GROUP BY mmm_yy, snapshot_date
        ),
        mob_headers AS (
            SELECT generate_series(1, :max_mob)::integer AS mob
        ),
        target_grid AS (
            SELECT c.mmm_yy, c.cohort_month, h.mob,
                   (date_trunc(
                       'month', c.cohort_month + h.mob * INTERVAL '1 month'
                    ) + INTERVAL '1 month' - INTERVAL '1 day')::date
                    AS target_snapshot_date
            FROM cohort_months c CROSS JOIN mob_headers h
        )
        SELECT g.mmm_yy,
               g.cohort_month,
               g.mob,
               g.target_snapshot_date,
               d.disb_amount_cr,
               p.par_amount_cr,
               p.par_snapshot_disb_cr,
               CASE
                   WHEN p.snapshot_date IS NULL
                     OR p.par_snapshot_disb_cr IS NULL
                     OR p.par_snapshot_disb_cr = 0
                   THEN NULL
                   ELSE p.par_amount_cr / p.par_snapshot_disb_cr
               END AS par_pct,
               CASE
                   WHEN p.snapshot_date IS NULL
                     OR d.disb_amount_cr IS NULL
                     OR d.disb_amount_cr = 0
                   THEN NULL
                   ELSE p.par_amount_cr / d.disb_amount_cr
               END AS color_ratio
        FROM target_grid g
        JOIN cohort_disb d USING (mmm_yy, cohort_month)
        LEFT JOIN performance p
          ON p.mmm_yy = g.mmm_yy
         AND p.snapshot_date = g.target_snapshot_date
        ORDER BY g.cohort_month, g.mob
    """)
    with engine.connect() as connection:
        return pd.read_sql_query(query, connection, params=params)


@st.cache_data(ttl=30, show_spinner=False)
def _load_vintage_qob_data(state=None, branch_category=None):
    """Return quarterly cohorts and QOB PAR using the DAX matrix logic."""
    conditions = []
    params = {}
    if state is not None:
        conditions.append('branch_state = :state')
        params['state'] = state
    if branch_category is not None:
        conditions.append('branch_category = :branch_category')
        params['branch_category'] = branch_category
    where_sql = ' AND '.join(conditions) if conditions else 'TRUE'

    query = text(f"""
        WITH scoped AS (
            SELECT mmm_yy,
                   to_date('01-' || mmm_yy, 'DD-Mon-YY')::date AS cohort_month,
                   branch_state,
                   branch_category,
                   snapshot_date,
                   amt_disb_cr,
                   par_0_wf_amt_cr,
                   par_snapshot_disb_cr
            FROM {SOURCE}
            WHERE {where_sql}
        ), quarter_cohorts AS (
            SELECT DISTINCT
                   date_trunc(
                       'quarter', to_date('01-' || mmm_yy, 'DD-Mon-YY')
                   )::date + INTERVAL '3 months' - INTERVAL '1 day'
                       AS quarter_end
            FROM {SOURCE}
            WHERE mmm_yy IS NOT NULL
        ), disbursement_by_slice AS (
            SELECT mmm_yy,
                   cohort_month,
                   branch_state,
                   branch_category,
                   MAX(amt_disb_cr) AS disb_amount_cr
            FROM scoped
            GROUP BY mmm_yy, cohort_month, branch_state, branch_category
        ), par_by_slice AS (
            SELECT mmm_yy,
                   cohort_month,
                   snapshot_date,
                   branch_state,
                   branch_category,
                   SUM(par_0_wf_amt_cr) AS par_amount_cr,
                   SUM(par_snapshot_disb_cr) AS par_snapshot_disb_cr
            FROM scoped
            WHERE snapshot_date IS NOT NULL
            GROUP BY mmm_yy, cohort_month, snapshot_date,
                     branch_state, branch_category
        ), quarter_disbursement AS (
            SELECT date_trunc('quarter', cohort_month)::date
                       + INTERVAL '3 months' - INTERVAL '1 day' AS quarter_end,
                   SUM(disb_amount_cr) AS disb_amount_cr
            FROM disbursement_by_slice
            GROUP BY quarter_end
        ), quarter_performance AS (
            SELECT date_trunc('quarter', cohort_month)::date
                       + INTERVAL '3 months' - INTERVAL '1 day' AS quarter_end,
                   snapshot_date,
                   SUM(par_amount_cr) AS par_amount_cr,
                   SUM(par_snapshot_disb_cr) AS par_snapshot_disb_cr
            FROM par_by_slice
            GROUP BY quarter_end, snapshot_date
        ), latest_snapshot AS (
            SELECT MAX(snapshot_date) AS snapshot_date FROM scoped
        ), first_quarter AS (
            SELECT MIN(quarter_end) AS quarter_end
            FROM quarter_cohorts
        ), qob_headers AS (
            SELECT generate_series(
                1,
                GREATEST(
                    1,
                    (
                        (EXTRACT(YEAR FROM ls.snapshot_date)
                            - EXTRACT(YEAR FROM fq.quarter_end)) * 4
                        + EXTRACT(QUARTER FROM ls.snapshot_date)
                        - EXTRACT(QUARTER FROM fq.quarter_end)
                    )::integer
                )
            )::integer AS qob
            FROM latest_snapshot ls
            CROSS JOIN first_quarter fq
        ), target_grid AS (
            SELECT q.quarter_end,
                   h.qob,
                   (date_trunc(
                       'month', q.quarter_end + h.qob * INTERVAL '3 months'
                   ) + INTERVAL '1 month' - INTERVAL '1 day')::date
                       AS standard_target_snapshot,
                   ls.snapshot_date AS latest_snapshot_date,
                   (date_trunc('quarter', ls.snapshot_date)::date
                       + INTERVAL '3 months' - INTERVAL '1 day')::date
                       AS latest_snapshot_quarter_end
            FROM quarter_cohorts q
            CROSS JOIN qob_headers h
            CROSS JOIN latest_snapshot ls
        ), targets AS (
            SELECT quarter_end,
                   qob,
                   CASE
                       WHEN standard_target_snapshot = latest_snapshot_quarter_end
                       THEN latest_snapshot_date
                       ELSE standard_target_snapshot
                   END AS target_snapshot_date
            FROM target_grid
        )
        SELECT t.quarter_end,
               t.qob,
               d.disb_amount_cr,
               CASE
                   WHEN p.par_snapshot_disb_cr IS NULL
                     OR p.par_snapshot_disb_cr = 0
                   THEN NULL
                   ELSE p.par_amount_cr / p.par_snapshot_disb_cr
               END AS par_pct
        FROM targets t
        LEFT JOIN quarter_disbursement d USING (quarter_end)
        LEFT JOIN quarter_performance p
          ON p.quarter_end = t.quarter_end
         AND p.snapshot_date = t.target_snapshot_date
        ORDER BY t.quarter_end, t.qob
    """)
    with engine.connect() as connection:
        return pd.read_sql_query(query, connection, params=params)


def _par_color_style(value):
    """Use Power BI's PARAmount / DisbAmount thresholds for cell colors."""
    if pd.isna(value):
        return "background-color: #FFFFFF; color: #FFFFFF;"
    if value > 0.07:
        return "background-color: #FF0000; color: #000000;"
    if value > 0.05:
        return "background-color: #D9B3FF; color: #000000;"
    if value >= 0.025:
        return "background-color: #FCE4D6; color: #000000;"
    return "background-color: #92D050; color: #000000;"


def _qob_color_style(value):
    """Use the QOB DAX thresholds for quarter performance cell colors."""
    if pd.isna(value):
        return "background-color: #FFFFFF; color: #FFFFFF;"
    if value < 0.025:
        return "background-color: #92D050; color: #000000;"
    if value < 0.05:
        return "background-color: #FCE4D6; color: #000000;"
    if value <= 0.07:
        return "background-color: #D9B3FF; color: #000000;"
    return "background-color: #FF0000; color: #000000;"


@st.fragment(run_every="60s")
def _render_vintage_qob(state, category):
    with st.spinner("Loading Vintage QOB snapshot aggregates..."):
        qob_df = _load_vintage_qob_data(
            state=None if state == "All" else state,
            branch_category=None if category == "All" else category,
        )
    if qob_df.empty:
        st.info("No quarterly QOB rows match the selected filters.")
        return

    qob_df["disb_quarter"] = pd.to_datetime(qob_df["quarter_end"]).dt.strftime(
        "%b-%y"
    )
    quarter_order = (
        qob_df[["quarter_end", "disb_quarter"]]
        .drop_duplicates()
        .sort_values("quarter_end")["disb_quarter"]
        .tolist()
    )
    available_qobs = sorted(
        qob_df.loc[qob_df["par_pct"].notna(), "qob"].astype(int).unique().tolist()
    )
    qob_matrix = qob_df.pivot(
        index="disb_quarter", columns="qob", values="par_pct"
    ).reindex(index=quarter_order, columns=available_qobs)
    qob_disb_amount = (
        qob_df[["disb_quarter", "disb_amount_cr"]]
        .drop_duplicates("disb_quarter")
        .set_index("disb_quarter")["disb_amount_cr"]
    )
    qob_matrix.insert(
        0, "Amt Disb (Cr)", qob_disb_amount.reindex(qob_matrix.index)
    )
    qob_matrix.index.name = "Disb Quarter"
    qob_matrix.columns = ["Amt Disb (Cr)", *[f"{qob} QOB" for qob in available_qobs]]
    for column in qob_matrix.columns:
        qob_matrix[column] = pd.to_numeric(qob_matrix[column], errors="coerce")
    qob_color_matrix = qob_matrix.drop(columns=["Amt Disb (Cr)"])

    qob_colors = pd.DataFrame(
        "", index=qob_matrix.index, columns=qob_matrix.columns
    )
    for qob in available_qobs:
        qob_column = f"{qob} QOB"
        qob_colors[qob_column] = qob_matrix[qob_column].map(_qob_color_style)
    qob_formatters = {
        "Amt Disb (Cr)": lambda value: "" if pd.isna(value) else f"{value:,.2f}",
        **{
            f"{qob} QOB": lambda value: "" if pd.isna(value) else f"{value:.2%}"
            for qob in available_qobs
        },
    }

    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.subheader("Vintage QOB Performance (Quarterly Base)")
        st.download_button(
            "Download QOB.xlsx",
            data=lambda: _build_xlsx_bytes(
                qob_matrix,
                qob_color_matrix,
                "QOB",
                "Disb Quarter",
                "qob",
            ),
            file_name="QOB.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            icon=":material/download:",
            width="content",
        )
    _render_vintage_matrix(qob_matrix, qob_colors, qob_formatters)


def _render_vintage_matrix(matrix, styles, formatters, max_height=None):
    """Render a styled, scrollable matrix with aligned cohort and amount columns."""
    row_label = matrix.index.name or "Cohort"
    display_matrix = matrix.copy()
    display_matrix.insert(0, row_label, matrix.index.astype(str))
    display_matrix = display_matrix.reset_index(drop=True)

    display_styles = pd.DataFrame(
        "", index=display_matrix.index, columns=display_matrix.columns
    )
    for column in styles.columns:
        display_styles[column] = styles[column].reset_index(drop=True)

    table_styles = [
        {
            "selector": "table",
            "props": [
                ("border-collapse", "collapse"),
                ("border-spacing", "0"),
                ("min-width", "100%"),
                ("width", "max-content"),
            ],
        },
        {
            "selector": "thead th",
            "props": [
                ("font-size", "15px"),
                ("font-weight", "700"),
                ("color", "#293548"),
                ("padding", "7px 10px"),
                ("text-align", "center"),
            ],
        },
        {
            "selector": "tbody td",
            "props": [("padding", "5px 10px"), ("line-height", "18px")],
        },
    ]
    table_html = (
        display_matrix.style
        .format(formatters, na_rep="", escape="html")
        .apply(lambda _data: display_styles, axis=None)
        .hide(axis="index")
        .set_table_styles(table_styles)
        .to_html()
    )
    height_css = (
        f"max-height: {int(max_height)}px; overflow-y: auto;"
        if max_height is not None
        else "overflow-y: visible;"
    )
    st.html(f"""
        <style>
        .vintage-matrix-scroll {{
            width: 100%;
            overflow-x: auto;
            {height_css}
            border: 1px solid #000000;
            background: #FFFFFF;
        }}
        .vintage-matrix-scroll table {{
            font-family: inherit;
            white-space: nowrap;
            border: 1px solid #000000 !important;
            border-collapse: collapse !important;
            border-spacing: 0 !important;
        }}
        .vintage-matrix-scroll th,
        .vintage-matrix-scroll td {{
            border: 1px solid #000000 !important;
        }}
        .vintage-matrix-scroll thead th {{
            position: sticky;
            top: 0;
            z-index: 2;
            background: #EEF1F6 !important;
            line-height: 20px;
        }}
        .vintage-matrix-scroll tbody td:first-child {{
            position: sticky;
            left: 0;
            z-index: 1;
            background: #F7F8FA !important;
            font-size: 15px !important;
            font-weight: 700 !important;
            color: #293548 !important;
            text-align: center !important;
        }}
        .vintage-matrix-scroll thead th:first-child {{
            left: 0;
            z-index: 3;
        }}
        .vintage-matrix-scroll td {{
            font-size: 13px;
            white-space: nowrap;
            text-align: center;
        }}
        .vintage-matrix-scroll tbody td:nth-child(2) {{
            text-align: right !important;
        }}
        </style>
        <div class="vintage-matrix-scroll">{table_html}</div>
    """)


def _render_slicer_label(label):
    st.markdown(
        f"<div style='font-size: 16px; font-weight: 700; margin-bottom: 6px;'>{label}</div>",
        unsafe_allow_html=True,
    )


def _par_fill_color(value):
    """Return the MOB fill color for an Excel export."""
    if pd.isna(value):
        return "FFFFFF"
    if value > 0.07:
        return "FF0000"
    if value > 0.05:
        return "D9B3FF"
    if value >= 0.025:
        return "FCE4D6"
    return "92D050"


def _qob_fill_color(value):
    """Return the QOB DAX fill color for an Excel export."""
    if pd.isna(value):
        return "FFFFFF"
    if value < 0.025:
        return "92D050"
    if value < 0.05:
        return "FCE4D6"
    if value <= 0.07:
        return "D9B3FF"
    return "FF0000"


@st.cache_data(ttl=900, show_spinner=False, max_entries=8)
def _build_xlsx_bytes(matrix, color_matrix, sheet_name, index_label, color_mode):
    """Build a styled Excel workbook for one vintage matrix."""
    from io import BytesIO

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet_name
    worksheet.append([index_label, *matrix.columns.tolist()])

    for cell in worksheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="17365D")
        cell.alignment = Alignment(horizontal="center")

    fill_color = _qob_fill_color if color_mode == "qob" else _par_fill_color
    for row_number, (row_label, row) in enumerate(matrix.iterrows(), start=2):
        worksheet.cell(row=row_number, column=1, value=str(row_label))
        for column_number, column in enumerate(matrix.columns, start=2):
            value = row[column]
            cell = worksheet.cell(
                row=row_number,
                column=column_number,
                value=None if pd.isna(value) else float(value),
            )
            if column == "Amt Disb (Cr)":
                cell.number_format = "#,##0.00"
            else:
                cell.number_format = "0.00%"
                ratio = color_matrix.at[row_label, column]
                cell.fill = PatternFill("solid", fgColor=fill_color(ratio))

    worksheet.freeze_panes = "C2"
    worksheet.auto_filter.ref = worksheet.dimensions
    worksheet.column_dimensions["A"].width = 16
    worksheet.column_dimensions["B"].width = 18
    for column_number in range(3, worksheet.max_column + 1):
        worksheet.column_dimensions[get_column_letter(column_number)].width = 12

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def render_report(selected_month=None):
    st.markdown(
        "<h1 style='text-align: center;'>Vintage Analysis</h1>",
        unsafe_allow_html=True,
    )
    st.html("""
        <style>
        .st-key-vintage_category_cat_a button {
            background: #92D050 !important;
            border-color: #92D050 !important;
            color: #1F2937 !important;
        }
        .st-key-vintage_category_cat_b button {
            background: #FFD966 !important;
            border-color: #FFD966 !important;
            color: #1F2937 !important;
        }
        .st-key-vintage_category_cat_c button {
            background: #F4B183 !important;
            border-color: #F4B183 !important;
            color: #1F2937 !important;
        }
        .st-key-vintage_category_cat_d button {
            background: #F4CCCC !important;
            border-color: #F4CCCC !important;
            color: #1F2937 !important;
        }
        .st-key-vintage_category_cat_a button,
        .st-key-vintage_category_cat_a button *,
        .st-key-vintage_category_cat_b button,
        .st-key-vintage_category_cat_b button *,
        .st-key-vintage_category_cat_c button,
        .st-key-vintage_category_cat_c button *,
        .st-key-vintage_category_cat_d button,
        .st-key-vintage_category_cat_d button * {
            font-size: 22px !important;
            font-weight: 800 !important;
            line-height: 1.2 !important;
        }
        .st-key-vintage_category_cat_a button,
        .st-key-vintage_category_cat_b button,
        .st-key-vintage_category_cat_c button,
        .st-key-vintage_category_cat_d button {
            min-height: 54px !important;
        }
        </style>
    """)
    try:
        dimensions = _load_filter_dimensions()
        if dimensions.empty:
            st.info("No vintage data is available.")
            return

        month_rows = dimensions[["mmm_yy", "cohort_month"]].drop_duplicates()
        month_rows = month_rows.sort_values("cohort_month")
        month_labels = dict(zip(month_rows["mmm_yy"], month_rows["mmm_yy"]))
        month_options = month_rows["mmm_yy"].tolist()
        states = sorted(dimensions["branch_state"].dropna().unique().tolist())
        categories = sorted(dimensions["branch_category"].dropna().unique().tolist())

        filters = st.columns([1.3, 1, 1.4], vertical_alignment="bottom")
        with filters[0]:
            month_state_key = "vintage_disbursement_months"
            if month_state_key not in st.session_state:
                st.session_state[month_state_key] = month_options.copy()
            else:
                # Keep persisted selections valid when the available cohorts change.
                st.session_state[month_state_key] = [
                    month for month in st.session_state[month_state_key]
                    if month in month_options
                ]
            for month in month_options:
                month_key = f"vintage_month_{month}"
                if month_key not in st.session_state:
                    st.session_state[month_key] = month in st.session_state[month_state_key]

            _render_slicer_label(
                f"Disbursement Month ({len(st.session_state[month_state_key])} selected)"
            )
            with st.popover("Select months", width="stretch"):
                selection_actions = st.columns(2)
                selection_actions[0].button(
                    "Select all",
                    key="vintage_month_select_all_button",
                    on_click=_set_vintage_months_selected,
                    args=(month_options, True),
                    width="stretch",
                )
                selection_actions[1].button(
                    "Unselect all",
                    key="vintage_month_unselect_all_button",
                    on_click=_set_vintage_months_selected,
                    args=(month_options, False),
                    width="stretch",
                )

                for month in month_options:
                    month_key = f"vintage_month_{month}"
                    st.checkbox(
                        month_labels[month],
                        key=month_key,
                        on_change=_sync_vintage_month_selection,
                        args=(month_options, month),
                    )

            selected_months = st.session_state[month_state_key]
        with filters[1]:
            _render_slicer_label("State")
            state = st.selectbox(
                "State", ["All", *states], label_visibility="collapsed"
            )
        with filters[2]:
            _render_slicer_label("Branch Category")
            category_state_key = "vintage_branch_category"
            if st.session_state.get(category_state_key) not in ["All", *categories]:
                st.session_state[category_state_key] = "All"
            category = st.session_state[category_state_key]
            category_buttons = st.columns(len(categories) + 1)
            if category_buttons[0].button(
                "All",
                key="vintage_category_all",
                type="primary" if category == "All" else "secondary",
                width="stretch",
            ):
                st.session_state[category_state_key] = "All"
                category = "All"
            for button, category_option in zip(category_buttons[1:], categories):
                category_slug = category_option.lower().replace(" ", "_")
                display_label = category_option.replace(" ", "-")
                selected = category == category_option
                if button.button(
                    display_label,
                    key=f"vintage_category_{category_slug}",
                    type="primary" if selected else "secondary",
                    icon=":material/check:" if selected else None,
                    width="stretch",
                ):
                    st.session_state[category_state_key] = category_option
                    category = category_option

        if not selected_months:
            st.info("Select at least one disbursement month.")
            _render_vintage_qob(state, category)
            return

        with st.spinner("Loading Vintage MOB snapshot aggregates..."):
            df = _load_vintage_data(
                state=None if state == "All" else state,
                branch_category=None if category == "All" else category,
                disb_months=tuple(selected_months),
            )
        if df.empty:
            st.warning("No rows match the selected filters.")
            _render_vintage_qob(state, category)
            return

        month_order = month_rows.loc[
            month_rows["mmm_yy"].isin(selected_months), "mmm_yy"
        ].tolist()
        amount_by_month = (
            df[["mmm_yy", "disb_amount_cr"]]
            .drop_duplicates("mmm_yy")
            .set_index("mmm_yy")["disb_amount_cr"]
        )
        matrix = df.pivot(index="mmm_yy", columns="mob", values="par_pct")
        matrix = matrix.reindex(index=month_order, columns=range(1, MAX_MOB + 1))
        color_matrix = df.pivot(index="mmm_yy", columns="mob", values="color_ratio")
        color_matrix = color_matrix.reindex(
            index=month_order, columns=range(1, MAX_MOB + 1)
        )

        matrix.insert(0, "Amt Disb (Cr)", amount_by_month.reindex(matrix.index))
        matrix.index.name = "Disb Month"
        matrix.columns = ["Amt Disb (Cr)"] + [f"{mob} MOB" for mob in range(1, MAX_MOB + 1)]
        color_matrix.columns = [f"{mob} MOB" for mob in range(1, MAX_MOB + 1)]

        style_grid = pd.DataFrame("", index=matrix.index, columns=matrix.columns)
        for mob_column in color_matrix.columns:
            style_grid[mob_column] = color_matrix[mob_column].map(_par_color_style)

        formatters = {
            "Amt Disb (Cr)": lambda value: "" if pd.isna(value) else f"{value:,.2f}",
            **{
                f"{mob} MOB": lambda value: "" if pd.isna(value) else f"{value:.2%}"
                for mob in range(1, MAX_MOB + 1)
            },
        }

        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.subheader("Vintage MOB Performance (Monthly Base)")
            st.download_button(
                "Download MOB.xlsx",
                data=lambda: _build_xlsx_bytes(
                    matrix,
                    color_matrix,
                    "MOB",
                    "Disb Month",
                    "mob",
                ),
                file_name="MOB.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                icon=":material/download:",
                width="content",
            )
        # Twelve monthly cohorts (Sep-24 through Aug-25) remain visible;
        # later cohorts can be reached by scrolling within this first matrix.
        _render_vintage_matrix(
            matrix, style_grid, formatters, max_height=370
        )
        _render_vintage_qob(state, category)

    except Exception as exc:
        st.error(f"Unable to load Vintage Analysis: {exc}")
