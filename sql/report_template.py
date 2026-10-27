import streamlit as st
from datetime import datetime


def _format_month(selected_month):
    try:
        date_value = datetime.strptime(str(selected_month), "%Y-%m-%d")
        return date_value.strftime("%b-%y")
    except Exception:
        return str(selected_month)


def report_header(title, selected_month):
    """
    Common header for all reports
    """

    col1, col2 = st.columns([4, 1])

    with col1:
        st.title(title)

    with col2:
        st.markdown(
            f"<div style='text-align:center;'>"
            f"<div style='font-size:0.95rem; color:#64748b; letter-spacing:0.04em;'>Reporting Period</div>"
            f"<div style='font-size:2.2rem; font-weight:800; color:#0f172a; margin-top:0.15rem;'>{_format_month(selected_month)}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.divider()