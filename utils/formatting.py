from io import BytesIO

import pandas as pd
import streamlit as st

from config.db import engine


@st.cache_data(ttl=1800)
def get_available_months():
    """Fetch distinct months from the branch analysis view."""
    query = """
    SELECT DISTINCT "Month"
    FROM warburg_mom.branch_wise_analysis
    ORDER BY "Month" DESC
    """
    months_df = pd.read_sql(query, engine)
    return months_df["Month"].tolist()


@st.cache_data(ttl=1800)
def load_branch_view_data(selected_month):
    """Load branch analysis data for the selected month."""
    query = f"""
    SELECT
        "Branch With Code",
        "Branch Category",
        "Total Active Loans",
        "Total Active Clinet",
        "POS",
        "Final Exposure",
        "PAR GT0 & Write_Off",
        "Cumu. Loan Disb"
    FROM warburg_mom.branch_wise_analysis
    WHERE "Month" = '{selected_month}'
    ORDER BY "Branch With Code"
    """
    return pd.read_sql(query, engine)


def format_indian(value):
    """Format numeric values in the Indian numbering system."""
    if pd.isna(value):
        return "—"

    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return value

    if value == 0:
        return "0"

    sign = "-" if value < 0 else ""
    absolute_value = abs(int(value))
    s = str(absolute_value)

    if len(s) <= 3:
        return sign + s

    last_three = s[-3:]
    remaining = s[:-3]
    groups = []

    while len(remaining) > 2:
        groups.append(remaining[-2:])
        remaining = remaining[:-2]

    if remaining:
        groups.append(remaining)

    groups.reverse()
    return sign + ",".join(groups) + "," + last_three


def format_currency(value):
    """Format a value as Indian currency with a rupee prefix."""
    return f"₹{format_indian(value)}"


def format_percentage(value):
    """Format a ratio as a percentage."""
    if pd.isna(value):
        return "—"
    return f"{value * 100:.2f}%"


def get_excel_bytes(df):
    """Create an Excel download buffer for the provided DataFrame."""
    buffer = BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    buffer.seek(0)
    return buffer
