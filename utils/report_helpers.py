import datetime
import pandas as pd
from config.db import engine


# =====================================================
# Get Available Months from Materialized View
# =====================================================
def get_available_months(view_name):
    """
    Returns available months from the given materialized view.
    """

    query = f"""
        SELECT DISTINCT "Month"
        FROM warburg_mom."{view_name}"
        ORDER BY "Month" DESC
    """

    df = pd.read_sql(query, engine)

    return df["Month"].tolist()


# =====================================================
# Load Data
# =====================================================
def _format_month_for_query(selected_month):
    if isinstance(selected_month, (datetime.date, datetime.datetime)):
        return selected_month.strftime("%Y-%m-%d")

    try:
        parsed = pd.to_datetime(selected_month, errors="coerce")
        if not pd.isna(parsed):
            return parsed.strftime("%Y-%m-%d")
    except Exception:
        pass

    return str(selected_month)


def get_data(view_name, selected_month=None):
    """
    Load data from any materialized view.
    """

    query = f"""
        SELECT *
        FROM warburg_mom."{view_name}"
    """

    if selected_month:
        formatted_month = _format_month_for_query(selected_month)
        query += f"""
            WHERE "Month" = '{formatted_month}'
        """

    return pd.read_sql(query, engine)


# =====================================================
# Indian Number Formatting
# Example:
# 1741996 -> 17,41,996
# =====================================================
def format_indian(number):

    if pd.isna(number):
        return "0"

    try:

        number = int(round(float(number)))

        negative = number < 0

        number = abs(number)

        s = str(number)

        if len(s) <= 3:
            result = s

        else:

            last3 = s[-3:]
            rest = s[:-3]

            parts = []

            while len(rest) > 2:
                parts.insert(0, rest[-2:])
                rest = rest[:-2]

            if rest:
                parts.insert(0, rest)

            result = ",".join(parts) + "," + last3

        return "-" + result if negative else result

    except Exception:
        return str(number)


# =====================================================
# Format Currency
# Example:
# ₹ 17,41,996
# =====================================================
def format_currency(number):

    if pd.isna(number):
        return "₹ 0"

    return f"₹ {format_indian(number)}"


# =====================================================
# Format Crore
# Example:
# 6466.47 Cr
# =====================================================
def format_crore(number):

    if pd.isna(number):
        return "0.00 Cr"

    try:

        crore = float(number) / 10000000

        return f"{crore:,.2f} Cr"

    except Exception:
        return "0.00 Cr"


# =====================================================
# Format Lakh
# Example:
# 12.45 Lakh
# =====================================================
def format_lakh(number):

    if pd.isna(number):
        return "0.00 Lakh"

    try:

        lakh = float(number) / 100000

        return f"{lakh:,.2f} Lakh"

    except Exception:
        return "0.00 Lakh"


# =====================================================
# Format Percentage
# Example:
# 0.9875 -> 98.75%
# =====================================================
def format_percent(value):

    if pd.isna(value):
        return "0.00%"

    try:

        return f"{float(value)*100:.2f}%"

    except Exception:
        return "0.00%"


# =====================================================
# Format Decimal
# =====================================================
def format_decimal(value, digits=2):

    if pd.isna(value):
        return "0"

    try:

        return f"{float(value):,.{digits}f}"

    except Exception:
        return str(value)