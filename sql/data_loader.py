import datetime
import pandas as pd
from config.db import engine


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


def get_data(view_name, month=None):
    """
    Load data from any materialized view.
    """

    query = f'SELECT * FROM warburg_mom."{view_name}"'

    if month:
        formatted_month = _format_month_for_query(month)
        query += f' WHERE "Month" = \'{formatted_month}\''

    return pd.read_sql(query, engine)