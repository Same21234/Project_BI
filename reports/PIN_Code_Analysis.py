from pathlib import Path
from io import BytesIO
import re
import json
import difflib
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import plotly.express as px
import plotly.graph_objects as go


def render_report(selected_month=None):
    """Render the PIN Code Analysis dashboard."""
    BASE = Path(__file__).resolve().parents[1]
    CSV_PATH = BASE / "Input_excel_file" / "PIN Code Analysis_CSV.csv"

    # GeoJSON files may be stored in Input_excel_file/assets/states,
    # Input_excel_file/assets, or the older Project_BI/assets/states path.
    STATE_DIR_CANDIDATES = [
        BASE / "Input_excel_file" / "assets",
        BASE / "assets" / "states",
        BASE / "assets",
    ]
    STATE_DIR = next(
        (
            folder
            for folder in STATE_DIR_CANDIDATES
            if folder.exists() and any(folder.rglob("*.geojson"))
        ),
        STATE_DIR_CANDIDATES[0],
    )

    MASTER_CANDIDATES = [
        BASE / "Input_excel_file" / "Fusion District and State.xlsx",
        BASE / "Input_excel_file" / "assets" / "Fusion District and State.xlsx",
        BASE / "Fusion District and State.xlsx",
    ]
    MASTER_PATH = next((p for p in MASTER_CANDIDATES if p.exists()), None)

    st.markdown(
        """
    <style>
    .stApp { background: #F3F6FA; }
    .block-container { padding-top: 1rem; padding-bottom: 1.8rem; max-width: 100%; }
    header[data-testid="stHeader"] { background: transparent; }
    .risk-header {
        background: linear-gradient(110deg,#10243A,#214C73);
        color: white; padding: 17px 22px; border-radius: 12px; margin-bottom: 13px;
    }
    .risk-header h1 { color: white; font-size: 25px; margin: 0; }
    .risk-header p { color: #D9E6F2; font-size: 13px; margin: 6px 0 0 0; }
    div[data-testid="stMetric"] {
        background: white; border: 1px solid #DCE4ED; border-radius: 9px;
        padding: 7px 10px; min-height: 74px;
    }
    div[data-testid="stMetricLabel"] { font-size: 11px; }
    div[data-testid="stMetricValue"] { font-size: 19px; }
    div[data-testid="stSidebar"] { background: #EDF1F6; }
    div[data-testid="stSidebar"] .block-container { padding-top: 1rem; }
    div[data-testid="stMultiSelect"] [data-baseweb="tag"] {
        background: #DCE8F5; color: #173B60; font-size: 11px;
        padding: 1px 4px;
    }
    div[data-testid="stMultiSelect"] [data-baseweb="select"] > div {
        min-height: 40px;
    }
    div[data-testid="stCheckbox"] label p { font-size: 12px; }
    .small-note { font-size: 12px; color: #526174; }
    </style>
    """,
        unsafe_allow_html=True,
    )

    # ----------------------------- HELPERS -----------------------------
    def norm(value):
        return re.sub(r"[^a-z0-9]", "", str(value).lower())

    def find_col(frame, candidates):
        lookup = {norm(col): col for col in frame.columns}
        for candidate in candidates:
            if norm(candidate) in lookup:
                return lookup[norm(candidate)]
        return None

    def to_num(series):
        cleaned = (
            series.astype("string")
            .str.strip()
            .str.replace(",", "", regex=False)
            .str.replace("₹", "", regex=False)
            .str.replace("%", "", regex=False)
            .str.replace(r"^\((.*)\)$", r"-\1", regex=True)
        )
        return pd.to_numeric(cleaned, errors="coerce")

    def to_percent(series):
        original = series.astype("string")
        explicit_percent = original.str.contains("%", regex=False, na=False).any()
        values = to_num(series)
        # Only convert decimal ratios (e.g. 0.012) to percent when values
        # are not explicitly labelled with % and the series looks like a ratio.
        if not explicit_percent and values.notna().any():
            q95 = values.abs().quantile(0.95)
            if pd.notna(q95) and q95 <= 1:
                values = values * 100
        return values

    def indian_number(value, decimals=0):
        """Indian digit grouping: 1912948 -> 19,12,948."""
        if pd.isna(value):
            return "—"
        number = float(value)
        sign = "-" if number < 0 else ""
        number = abs(number)
        if decimals:
            whole, frac = f"{number:.{decimals}f}".split(".")
        else:
            whole, frac = f"{int(round(number))}", None

        if len(whole) > 3:
            last3 = whole[-3:]
            rest = whole[:-3]
            chunks = []
            while len(rest) > 2:
                chunks.insert(0, rest[-2:])
                rest = rest[:-2]
            if rest:
                chunks.insert(0, rest)
            whole = ",".join(chunks + [last3])

        return sign + whole + (("." + frac) if frac is not None else "")

    def indian_cr(value):
        return "—" if pd.isna(value) else f"₹{indian_number(value, 2)} Cr"

    def pct_text(value):
        return "—" if pd.isna(value) else f"{value:.2f}%"

    def state_key(value):
        key = norm(value)
        aliases = {
            "orissa": "odisha",
            "uttaranchal": "uttarakhand",
            "nctofdelhi": "delhi",
            "nationalcapitalterritoryofdelhi": "delhi",
            "pondicherry": "puducherry",
            "dnhanddd": "dadranagarhavelianddamananddiu",
            "dadranagarhavelianddamananddiu": "dadranagarhavelianddamananddiu",
            "dadranagarhavelianddaman": "dadranagarhavelianddamananddiu",
        }
        return aliases.get(key, key)

    def district_match_key(district_name, state_name=None):
        """Normalize district labels; remove a parenthetical state suffix when it matches the state."""
        text = str(district_name or "").strip()
        state_norm = state_key(state_name) if state_name is not None else ""
        # Examples: "Pratapgarh (Rajasthan)" and "Pratapgarh" are the same district
        # when the feature/master row belongs to Rajasthan.
        match = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", text)
        if match and state_norm and state_key(match.group(2)) == state_norm:
            text = match.group(1).strip()
        return norm(text)

    # Read the Fusion district master if available. District matching is state-scoped,
    # exact first, then fuzzy only when the best match is strong and unambiguous.
    FUSION_DISTRICTS_BY_STATE = {}
    FUSION_DISTRICT_MATCH_AUDIT = []

    if MASTER_PATH is not None:
        try:
            _master = pd.read_excel(MASTER_PATH)
            _master.columns = [str(c).strip() for c in _master.columns]
            _master_district_col = find_col(
                _master, ["Districts", "District", "Branch District"]
            )
            _master_state_col = find_col(
                _master, ["State", "Branch State", "State Name"]
            )
            if _master_district_col and _master_state_col:
                _master = _master.dropna(
                    subset=[_master_district_col, _master_state_col]
                )
                for _, _row in _master.iterrows():
                    _state = str(_row[_master_state_col]).strip()
                    _district = str(_row[_master_district_col]).strip()
                    if _state and _district:
                        FUSION_DISTRICTS_BY_STATE.setdefault(state_key(_state), {})
                        FUSION_DISTRICTS_BY_STATE[state_key(_state)][
                            district_match_key(_district, _state)
                        ] = _district
        except Exception as _master_exc:
            st.warning(f"Could not read Fusion district master: {_master_exc}")

    def canonical_district(state_name, district_name):
        """Return the Fusion master spelling for a confident state-scoped district match."""
        if district_name is None or pd.isna(district_name):
            return ""
        original = str(district_name).strip()
        if not original:
            return original
        candidates = FUSION_DISTRICTS_BY_STATE.get(state_key(state_name), {})
        key = district_match_key(original, state_name)
        if key in candidates:
            return candidates[key]
        if not candidates:
            return original

        # Match against normalized district names within the same state only.
        scored = sorted(
            [
                (
                    difflib.SequenceMatcher(None, key, candidate_key).ratio(),
                    candidate_name,
                )
                for candidate_key, candidate_name in candidates.items()
            ],
            reverse=True,
        )
        if not scored:
            return original
        best_score, best_name = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        if best_score >= 0.88 and (best_score - second_score) >= 0.05:
            return best_name
        return original

    def negative_flag_mask(series):
        s = series.astype("string").str.strip().str.lower()
        negative = s.str.contains("negative", na=False) & ~s.str.contains(
            r"no\s*negative|non\s*negative|not\s*negative",
            regex=True,
            na=False,
        )
        return negative | s.isin(["yes", "true", "1", "y"])

    def weighted_rate(frame, rate_col, weight_col):
        if not rate_col:
            return float("nan")
        rates = frame[rate_col]
        if weight_col:
            weights = frame[weight_col]
            valid = rates.notna() & weights.notna() & (weights >= 0)
            if valid.any() and weights.loc[valid].sum() > 0:
                return float(
                    (rates.loc[valid] * weights.loc[valid]).sum()
                    / weights.loc[valid].sum()
                )
        return float(rates.mean()) if rates.notna().any() else float("nan")

    def aggregate_portfolio(frame, group_cols, C):
        grouped = frame.groupby(group_cols, dropna=False)
        out = grouped.agg(
            # The source report defines PIN Count as the number of input
            # records.  ``size`` deliberately includes a valid record whose
            # PIN field is blank, matching the Excel source total.
            PIN_Count=(C["pin"], "size"),
            Disbursement=(C["disb"], lambda x: x.sum(min_count=1)),
        ).reset_index()

        if C["pos"]:
            pos = grouped[C["pos"]].sum(min_count=1).reset_index(name="POS")
            out = out.merge(pos, on=group_cols, how="left")
        else:
            out["POS"] = float("nan")

        for key, amount_key, name in [
            ("par0", "par0_amt", "PAR0"),
            ("par90", "par90_amt", "PAR90"),
        ]:
            rate_col = C[key]
            amount_col = C.get(amount_key)

            # The Excel control totals use the supplied PAR percentage field,
            # weighted by Disb Amt.  This differs slightly from recalculating
            # the rate from the separately supplied PAR amount fields.
            if rate_col and C["disb"]:
                work = frame[group_cols].copy()
                work["_rate"] = frame[rate_col]
                work["_weight"] = frame[C["disb"]]
                valid = (
                    work["_rate"].notna()
                    & work["_weight"].notna()
                    & (work["_weight"] >= 0)
                )
                work["_num"] = work["_rate"].where(valid) * work["_weight"].where(valid)
                work["_den"] = work["_weight"].where(valid)
                rates = (
                    work.groupby(group_cols, dropna=False)
                    .agg(_num=("_num", "sum"), _den=("_den", "sum"))
                    .reset_index()
                )
                rates[name] = rates["_num"] / rates["_den"].where(rates["_den"] > 0)
                out = out.merge(rates[group_cols + [name]], on=group_cols, how="left")
                continue

            # Fallback for source files that do not supply a PAR percentage.
            if amount_col and C["disb"]:
                work = frame[group_cols].copy()
                work["_num"] = frame[amount_col]
                work["_den"] = frame[C["disb"]]
                rates = (
                    work.groupby(group_cols, dropna=False)
                    .agg(_num=("_num", "sum"), _den=("_den", "sum"))
                    .reset_index()
                )
                rates[name] = (
                    rates["_num"] / rates["_den"].where(rates["_den"] > 0)
                ) * 100
                out = out.merge(rates[group_cols + [name]], on=group_cols, how="left")
                continue

            out[name] = float("nan")
        return out

    def add_negative_counts(
        aggregate, negative_frame, group_cols, C, key_name="Map_Key"
    ):
        if negative_frame.empty:
            aggregate["Negative_PIN_Count"] = 0
        else:
            negative = (
                negative_frame.groupby(group_cols, dropna=False)
                .size()
                .reset_index(name="Negative_PIN_Count")
            )
            aggregate = aggregate.merge(negative, on=group_cols, how="left")
            aggregate["Negative_PIN_Count"] = (
                aggregate["Negative_PIN_Count"].fillna(0).astype(int)
            )

        aggregate["Non_Negative_PIN_Count"] = (
            aggregate["PIN_Count"] - aggregate["Negative_PIN_Count"]
        ).clip(lower=0)
        return aggregate

    # ----------------------------- LOAD CSV -----------------------------
    @st.cache_data(show_spinner="Loading PIN Code CSV...")
    def load_csv(path, modified_time, file_size):
        last_error = None
        for encoding in ("utf-8-sig", "cp1252", "latin1"):
            try:
                return (
                    pd.read_csv(
                        path,
                        encoding=encoding,
                        encoding_errors="strict",
                        low_memory=False,
                    ),
                    encoding,
                )
            except UnicodeDecodeError as exc:
                last_error = exc
        raise ValueError(f"CSV encoding error: {last_error}")

    if not CSV_PATH.exists():
        st.error(
            f"CSV not found at:\n{CSV_PATH}\n\n"
            "Keep the CSV inside Input_excel_file next to app.py."
        )
        st.stop()

    try:
        df, encoding_used = load_csv(
            str(CSV_PATH), CSV_PATH.stat().st_mtime, CSV_PATH.stat().st_size
        )
    except Exception as exc:
        st.error(f"Could not read CSV: {exc}")
        st.stop()

    df.columns = [str(c).strip().replace("\ufeff", "") for c in df.columns]
    df = df.dropna(how="all").copy()

    # Actual headers from your screenshot are included here.
    C = {
        "month": find_col(df, ["Month", "Disbursement Month", "Disb Month"]),
        "pin": find_col(df, ["Fision PIN Code", "Fusion PIN Code", "PIN Code"]),
        "state": find_col(df, ["Branch State", "State Name", "State"]),
        "district": find_col(df, ["Branch District", "District Name", "District"]),
        "branch": find_col(df, ["Branch Name", "Branch With Code", "Branch"]),
        "category": find_col(df, ["Branch Category", "Category"]),
        "range": find_col(df, ["RANGE-2", "Range", "Customer Range"]),
        "disb": find_col(df, ["Disb Amt.", "Disb Amt", "Disbursement"]),
        "pos": find_col(df, ["POS (Cr)", "POS", "Portfolio Outstanding"]),
        "par0_amt": find_col(df, ["PAR 0 +W/F", "PAR 0 + W/F", "PAR 0 W/F"]),
        "par90_amt": find_col(df, ["PAR 90 +W/F", "PAR 90 + W/F", "PAR 90 W/F"]),
        "par0": find_col(df, ["PAR0% DISB"]),
        "par90": find_col(df, ["PAR90% DISB"]),
        "loans": find_col(df, ["Loan Count", "Loan Accounts"]),
        "negative": find_col(
            df, ["PIN Negative Flag", "Negative Flag", "PIN Negative"]
        ),
    }

    # Monthly disbursement columns, e.g. Sep'26 Disb, Aug'26 Disb.
    # The month/year token is used to match the selected Month slicer to the correct source column.
    MONTH_DISB_COLS = []
    MONTH_RANK = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }

    def month_key(value):
        text_value = str(value).strip().lower()
        match = re.search(
            r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[^0-9]*(\d{2,4})",
            text_value,
        )
        if not match:
            parsed = pd.to_datetime(text_value.replace("'", " "), errors="coerce")
            if pd.isna(parsed):
                return None
            return f"{parsed.strftime('%b').lower()}{parsed.year % 100:02d}"
        year_text = match.group(2)
        year = int(year_text)
        if len(year_text) == 2:
            year += 2000
        return f"{match.group(1)}{year % 100:02d}"

    for col in df.columns:
        col_text = str(col).strip()
        if re.search(r"(?i)disb", col_text) and month_key(col_text):
            MONTH_DISB_COLS.append(col)

    def monthly_disb_col(month_label):
        key = month_key(month_label)
        if not key:
            return None
        for column in MONTH_DISB_COLS:
            if month_key(column) == key:
                return column
        return None

    for col in MONTH_DISB_COLS:
        df[col] = to_num(df[col])

    required = ["pin", "state", "district", "disb", "par0", "par90"]
    missing = [key for key in required if C[key] is None]
    if missing:
        st.error("Required columns not found: " + ", ".join(missing))
        st.write("Check the exact CSV header names.")
        st.stop()

    for key in ["disb", "pos", "loans", "par0_amt", "par90_amt"]:
        if C[key]:
            df[C[key]] = to_num(df[C[key]])
    for key in ["par0", "par90"]:
        df[C[key]] = to_percent(df[C[key]])

    for key in ["state", "district", "branch", "category", "range", "negative"]:
        if C[key]:
            df[C[key]] = df[C[key]].astype("string").str.strip()

    df[C["pin"]] = (
        df[C["pin"]]
        .astype("string")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .replace({"": pd.NA, "nan": pd.NA, "NaN": pd.NA, "None": pd.NA, "<NA>": pd.NA})
    )
    df = df[df[C["state"]].notna() & df[C["state"]].ne("")].copy()

    # Canonicalize each unique state/district pair once to keep this fast on large CSVs.
    if C["district"]:
        _unique_pairs = df[[C["state"], C["district"]]].drop_duplicates()
        _district_pair_map = {
            (
                str(row[C["state"]]).strip(),
                str(row[C["district"]]).strip(),
            ): canonical_district(row[C["state"]], row[C["district"]])
            for _, row in _unique_pairs.iterrows()
        }
        df["_Map_District"] = [
            _district_pair_map.get(
                (str(state).strip(), str(district).strip()),
                canonical_district(state, district),
            )
            for state, district in zip(df[C["state"]], df[C["district"]])
        ]
    else:
        df["_Map_District"] = ""

    if df.empty:
        st.error("No usable records found in the CSV.")
        st.stop()

    # ----------------------------- HEADER -----------------------------
    st.markdown(
        """
    <div class="risk-header">
      <h1>📍 PIN Code Portfolio Performance &amp; Risk</h1>
      <p>Fusion Finance Limited | Credit Risk Management | Month-wise Analysis</p>
    </div>
    """,
        unsafe_allow_html=True,
    )
    st.caption(
        f"Source: {CSV_PATH.name} | Total usable CSV rows: {indian_number(len(df))} | Encoding: {encoding_used}"
        + (
            f" | District master: {MASTER_PATH.name}"
            if MASTER_PATH
            else " | District master: not found (exact name matching only)"
        )
    )

    # ----------------------------- MONTH SELECTION -----------------------------
    # Initialize comparison values before any UI references them.
    comparison_month = None
    comparison_frame = df.iloc[0:0].copy()

    # Filter all KPIs and map metrics to the selected Month value.
    if C["month"]:
        month_values = (
            df[C["month"]]
            .astype("string")
            .str.strip()
            .replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
            .dropna()
            .unique()
            .tolist()
        )
        if not month_values:
            st.error("Month column is present, but no usable month values were found.")
            st.stop()

        def month_sort_key(value):
            parsed = pd.to_datetime(str(value).replace("'", " "), errors="coerce")
            return (0, parsed) if pd.notna(parsed) else (1, str(value).lower())

        month_values = sorted(month_values, key=month_sort_key, reverse=True)
        selected_month = st.selectbox(
            "📅 Select Month",
            options=month_values,
            index=0,
            key="pin_code_selected_month",
        )
        f = df[df[C["month"]].astype("string").str.strip() == selected_month].copy()
        st.caption(f"Showing data for selected month: {selected_month}")

        if comparison_month:
            st.markdown(
                f"<div style='margin-top:8px;margin-bottom:4px;font-size:18px;"
                f"font-weight:900;color:#173b60;'>KPI Summary: "
                f"<span style='color:#0f766e;'>{selected_month}</span> vs "
                f"<span style='color:#64748b;'>{comparison_month}</span></div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<div style='margin-top:8px;margin-bottom:4px;font-size:18px;"
                f"font-weight:900;color:#173b60;'>KPI Summary: {selected_month}</div>",
                unsafe_allow_html=True,
            )
    else:
        st.warning("Month column was not detected. Showing all available records.")
        f = df.copy()

    # Identify the immediately previous calendar month for the comparison tooltip.
    if C["month"]:
        selected_dt = pd.to_datetime(
            str(selected_month).replace("'", " "), errors="coerce"
        )
        if pd.notna(selected_dt):
            previous_dt = selected_dt - pd.DateOffset(months=1)
            month_series = df[C["month"]].astype("string").str.strip()
            parsed_months = pd.to_datetime(
                month_series.str.replace("'", " ", regex=False), errors="coerce"
            )
            previous_mask = parsed_months.dt.year.eq(
                previous_dt.year
            ) & parsed_months.dt.month.eq(previous_dt.month)
            comparison_frame = df[previous_mask].copy()
            if not comparison_frame.empty:
                comparison_month = str(comparison_frame[C["month"]].iloc[0]).strip()

    if f.empty:
        st.warning("No records available for the selected month.")
        st.stop()

    negative_rows = (
        f[negative_flag_mask(f[C["negative"]])].copy()
        if C["negative"]
        else f.iloc[0:0].copy()
    )

    # ----------------------------- KPI -----------------------------
    st.subheader("Executive Portfolio Summary")
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    loan_total = f[C["loans"]].sum(min_count=1) if C["loans"] else float("nan")

    # Total records is the source row count for the selected month.
    # Unique PIN Codes is intentionally not displayed as a KPI.
    k1.metric("Total Records", indian_number(len(f)))
    k2.metric("Loan Count", "—" if pd.isna(loan_total) else indian_number(loan_total))
    k3.metric("Total Disb", indian_cr(f[C["disb"]].sum(min_count=1)))
    # POS (Cr) is already in crore units; sum numeric source values without dividing again.
    pos_total_cr = f[C["pos"]].sum(min_count=1) if C["pos"] else float("nan")
    k4.metric("Total POS", indian_cr(pos_total_cr) if C["pos"] else "—")
    k5.metric("PAR 0% Disb", pct_text(weighted_rate(f, C["par0"], C["disb"])))
    k6.metric("PAR 90% Disb", pct_text(weighted_rate(f, C["par90"], C["disb"])))

    # ----------------------------- GEOJSON LOAD -----------------------------
    @st.cache_data(show_spinner="Loading India district boundaries...")
    def load_boundaries(folder, signature):
        import geopandas as gpd

        features = []
        label_rows = []
        errors = []
        district_candidates = [
            "district",
            "districtname",
            "distname",
            "dtname",
            "districtnam",
            "district_n",
            "name2",
            "name_2",
        ]
        state_candidates = ["st_nm", "state", "statename", "state_name", "stname"]

        for path in sorted(Path(folder).rglob("*.geojson")):
            try:
                geo = gpd.read_file(path)
                if geo.empty:
                    continue
                column_lookup = {
                    norm(col): col for col in geo.columns if col != geo.geometry.name
                }
                district_col = next(
                    (
                        column_lookup[name]
                        for name in district_candidates
                        if name in column_lookup
                    ),
                    None,
                )
                if not district_col:
                    errors.append(f"{path.name}: district name field not detected")
                    continue

                file_state = path.stem.replace("-", " ").replace("_", " ").strip()
                state_col = next(
                    (
                        column_lookup[name]
                        for name in state_candidates
                        if name in column_lookup
                    ),
                    None,
                )
                if state_col and pd.notna(geo.iloc[0][state_col]):
                    file_state = str(geo.iloc[0][state_col]).strip()
                skey = state_key(file_state)

                try:
                    projected = geo.to_crs("EPSG:3857")
                    point_geometries = projected.geometry.representative_point().to_crs(
                        "EPSG:4326"
                    )
                except Exception:
                    point_geometries = geo.geometry.representative_point()

                for idx, (_, row) in enumerate(geo.iterrows()):
                    geom = row.geometry
                    district_name = str(row[district_col]).strip()
                    if (
                        geom is None
                        or geom.is_empty
                        or not district_name
                        or district_name.lower() == "nan"
                    ):
                        continue
                    canonical_name = canonical_district(file_state, district_name)
                    map_key = skey + "|" + norm(canonical_name)
                    features.append(
                        {
                            "type": "Feature",
                            "properties": {
                                "map_key": map_key,
                                "State": file_state,
                                "District": canonical_name,
                                "Fusion_District": canonical_name,
                                "Original_District": district_name,
                            },
                            "geometry": geom.__geo_interface__,
                        }
                    )
                    point = point_geometries.iloc[idx]
                    label_rows.append(
                        {
                            "Map_Key": map_key,
                            "State": file_state,
                            "District": district_name,
                            "lon": float(point.x),
                            "lat": float(point.y),
                        }
                    )
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")

        return (
            {"type": "FeatureCollection", "features": features},
            pd.DataFrame(label_rows),
            errors,
        )

    state_files = sorted(STATE_DIR.rglob("*.geojson")) if STATE_DIR.exists() else []
    geo_signature = tuple(
        (p.name, p.stat().st_mtime, p.stat().st_size) for p in state_files
    )
    geojson, label_points, geo_errors = None, pd.DataFrame(), []

    if state_files:
        try:
            geojson, label_points, geo_errors = load_boundaries(
                str(STATE_DIR), geo_signature
            )
        except Exception as exc:
            st.error(f"Map boundary error: {exc}")

    # ----------------------------- AGGREGATION -----------------------------
    district_data = aggregate_portfolio(f, [C["state"], "_Map_District"], C).rename(
        columns={C["state"]: "State", "_Map_District": "District"}
    )
    district_data["State_Key"] = district_data["State"].map(state_key)
    district_data["District_Key"] = district_data["District"].map(norm)
    district_data["Map_Key"] = (
        district_data["State_Key"] + "|" + district_data["District_Key"]
    )

    # Build selected-month vs previous-month comparisons using the same calculations.
    # These values are added to each map feature for the hover comparison table.
    def build_comparison(frame, prefix, group_cols):
        if frame.empty:
            return pd.DataFrame(columns=["Map_Key"])
        temp = aggregate_portfolio(frame, group_cols, C).rename(
            columns={C["state"]: "State", "_Map_District": "District"}
        )
        if "District" not in temp.columns:
            temp["District"] = "All districts"
        temp["State_Key"] = temp["State"].map(state_key)
        temp["District_Key"] = temp["District"].map(norm)
        temp["Map_Key"] = temp["State_Key"] + "|" + temp["District_Key"]

        neg = (
            frame[negative_flag_mask(frame[C["negative"]])]
            if C["negative"]
            else frame.iloc[0:0]
        )
        if not neg.empty:
            neg_agg = (
                neg.groupby(group_cols, dropna=False)
                .size()
                .reset_index(name="Negative_PIN_Count")
            )
            neg_agg = neg_agg.rename(
                columns={C["state"]: "State", "_Map_District": "District"}
            )
            if "District" not in neg_agg.columns:
                neg_agg["District"] = "All districts"
            neg_agg["State_Key"] = neg_agg["State"].map(state_key)
            neg_agg["District_Key"] = neg_agg["District"].map(norm)
            neg_agg["Map_Key"] = neg_agg["State_Key"] + "|" + neg_agg["District_Key"]
            temp = temp.merge(
                neg_agg[["Map_Key", "Negative_PIN_Count"]], on="Map_Key", how="left"
            )
        else:
            temp["Negative_PIN_Count"] = 0

        temp["Negative_PIN_Count"] = temp["Negative_PIN_Count"].fillna(0).astype(int)
        temp["Non_Negative_PIN_Count"] = (
            temp["PIN_Count"] - temp["Negative_PIN_Count"]
        ).clip(lower=0)
        rename_map = {
            "PIN_Count": f"{prefix}_PIN_Count",
            "Negative_PIN_Count": f"{prefix}_Negative_PIN_Count",
            "Non_Negative_PIN_Count": f"{prefix}_Non_Negative_PIN_Count",
            "Loan_Count": f"{prefix}_Loan_Count",
            "Disbursement": f"{prefix}_Disbursement",
            "POS": f"{prefix}_POS",
            "PAR0": f"{prefix}_PAR0",
            "PAR90": f"{prefix}_PAR90",
        }
        if C["loans"]:
            temp["Loan_Count"] = (
                frame.groupby(group_cols, dropna=False)[C["loans"]]
                .sum(min_count=1)
                .values
            )
        else:
            temp["Loan_Count"] = float("nan")
        temp = temp.rename(columns=rename_map)
        keep = ["Map_Key"] + [v for k, v in rename_map.items() if v in temp.columns]
        for disb_col in MONTH_DISB_COLS:
            temp_name = f"{prefix}_{norm(disb_col)}"
            # Monthly disbursement values are summed using the same state/district grouping.
            monthly = (
                frame.groupby(group_cols, dropna=False)[disb_col]
                .sum(min_count=1)
                .reset_index(name=temp_name)
            )
            monthly = monthly.rename(
                columns={C["state"]: "State", "_Map_District": "District"}
            )
            if "District" not in monthly.columns:
                monthly["District"] = "All districts"
            monthly["Map_Key"] = (
                monthly["State"].map(state_key) + "|" + monthly["District"].map(norm)
            )
            temp = temp.merge(monthly[["Map_Key", temp_name]], on="Map_Key", how="left")
            keep.append(temp_name)

        # Selected-month monthly disbursement, matched to the actual source header.
        month_label = selected_month if prefix == "Current" else comparison_month
        month_column = monthly_disb_col(month_label) if month_label else None
        monthly_value_name = f"{prefix}_Monthly_Disbursement"
        if month_column and month_column in frame.columns:
            monthly_value = (
                frame.groupby(group_cols, dropna=False)[month_column]
                .sum(min_count=1)
                .reset_index(name=monthly_value_name)
            )
            monthly_value = monthly_value.rename(
                columns={C["state"]: "State", "_Map_District": "District"}
            )
            if "District" not in monthly_value.columns:
                monthly_value["District"] = "All districts"
            monthly_value["Map_Key"] = (
                monthly_value["State"].map(state_key)
                + "|"
                + monthly_value["District"].map(norm)
            )
            temp = temp.merge(
                monthly_value[["Map_Key", monthly_value_name]], on="Map_Key", how="left"
            )
        else:
            temp[monthly_value_name] = float("nan")
        keep.append(monthly_value_name)
        return temp[keep].drop_duplicates("Map_Key")

    district_compare_current = build_comparison(
        f, "Current", [C["state"], "_Map_District"]
    )
    district_compare_previous = build_comparison(
        comparison_frame, "Previous", [C["state"], "_Map_District"]
    )
    if not district_compare_current.empty:
        district_data = district_data.merge(
            district_compare_current, on="Map_Key", how="left"
        )
    if not district_compare_previous.empty:
        district_data = district_data.merge(
            district_compare_previous, on="Map_Key", how="left"
        )

    negative_district = (
        negative_rows.groupby([C["state"], "_Map_District"], dropna=False)
        .size()
        .reset_index(name="Negative_PIN_Count")
        .rename(columns={C["state"]: "State", "_Map_District": "District"})
    )
    negative_district["Map_Key"] = (
        negative_district["State"].map(state_key)
        + "|"
        + negative_district["District"].map(norm)
    )
    district_data = district_data.merge(
        negative_district[["Map_Key", "Negative_PIN_Count"]], on="Map_Key", how="left"
    )
    district_data["Negative_PIN_Count"] = (
        district_data["Negative_PIN_Count"].fillna(0).astype(int)
    )
    district_data["Non_Negative_PIN_Count"] = (
        district_data["PIN_Count"] - district_data["Negative_PIN_Count"]
    ).clip(lower=0)

    # ----------------------------- STATE / DISTRICT DRILL DOWN -----------------------------
    st.subheader("India Credit Risk Map")
    st.caption(
        "Hover over any district to view its PIN count, negative and non-negative PIN count, PAR 90%, PAR 0%, disbursement and POS. "
        "Red indicates PAR 90% Disb ≥ 4%, not the PIN Negative Flag."
    )

    # Fixed PAR90 bands:
    # <2% green; 2% to <4% yellow; >=4% red; missing grey.
    def add_risk_band(frame):
        frame = frame.copy()
        frame["Risk Band"] = pd.cut(
            frame["PAR90"],
            bins=[-float("inf"), 2, 4, float("inf")],
            labels=["Lower risk (<2%)", "Watch (2% to <4%)", "High risk (≥4%)"],
            right=False,
        ).astype("string")
        # True missing values remain grey; actual 0.00% falls in green band.
        frame["Risk Band"] = frame["Risk Band"].fillna("No PAR90 data")
        return frame

    risk_colors = {
        "Lower risk (<2%)": "#B7E4C7",
        "Watch (2% to <4%)": "#FFD966",
        "High risk (≥4%)": "#C62828",
        "No PAR90 data": "#B9C2CC",
    }

    state_data = aggregate_portfolio(f, [C["state"]], C).rename(
        columns={C["state"]: "State"}
    )
    negative_state = (
        negative_rows.groupby(C["state"])
        .size()
        .reset_index(name="Negative_PIN_Count")
        .rename(columns={C["state"]: "State"})
    )
    state_data = state_data.merge(negative_state, on="State", how="left")
    state_data["Negative_PIN_Count"] = (
        state_data["Negative_PIN_Count"].fillna(0).astype(int)
    )
    state_data["Non_Negative_PIN_Count"] = (
        state_data["PIN_Count"] - state_data["Negative_PIN_Count"]
    ).clip(lower=0)
    state_data["State_Key"] = state_data["State"].map(state_key)

    if geojson and geojson.get("features"):
        # Prepare the same portfolio metrics for each district boundary feature.
        # Leaflet switches from state polygons to district polygons automatically
        # at a zoom threshold, so the tooltip reflects the currently visible level.
        district_lookup = {row["Map_Key"]: row for _, row in district_data.iterrows()}
        district_features = []
        for feature in geojson["features"]:
            props = feature.get("properties", {})
            key = props.get("map_key")
            row = district_lookup.get(key)

            # Keep every district boundary, even if no Fusion PIN exists in the CSV.
            # Missing-data districts are displayed in grey with an explicit tooltip.
            if row is None:
                state_name = str(props.get("State", "Unknown State"))
                district_name = str(props.get("District", "Unknown District"))
                enriched = dict(props)
                enriched.update(
                    {
                        "Level": "District",
                        "State": state_name,
                        "District": district_name,
                        "Fusion_District": str(
                            props.get("Fusion_District", district_name)
                        ),
                        "PIN_Count": 0,
                        "Negative_PIN_Count": 0,
                        "Non_Negative_PIN_Count": 0,
                        "PAR90": None,
                        "PAR0": None,
                        "Disbursement": None,
                        "POS": None,
                        "Fusion_PIN_Status": "No Fusion PIN Found in this District",
                        "Risk_Band": "No Fusion PIN Found",
                    }
                )
                if comparison_month:
                    enriched["Comparison_Month"] = comparison_month
                    enriched["Selected_Month"] = str(selected_month)
            else:
                enriched = dict(props)
                enriched.update(
                    {
                        "Level": "District",
                        "State": str(row["State"]),
                        "District": str(row["District"]),
                        "Fusion_District": str(
                            props.get("Fusion_District", row["District"])
                        ),
                        "PIN_Count": (
                            int(row["PIN_Count"]) if pd.notna(row["PIN_Count"]) else 0
                        ),
                        "Negative_PIN_Count": (
                            int(row["Negative_PIN_Count"])
                            if pd.notna(row["Negative_PIN_Count"])
                            else 0
                        ),
                        "Non_Negative_PIN_Count": (
                            int(row["Non_Negative_PIN_Count"])
                            if pd.notna(row["Non_Negative_PIN_Count"])
                            else 0
                        ),
                        "PAR90": None if pd.isna(row["PAR90"]) else float(row["PAR90"]),
                        "PAR0": None if pd.isna(row["PAR0"]) else float(row["PAR0"]),
                        "Disbursement": (
                            None
                            if pd.isna(row["Disbursement"])
                            else float(row["Disbursement"])
                        ),
                        "POS": None if pd.isna(row["POS"]) else float(row["POS"]),
                    }
                )
                # Pass selected-vs-previous month metrics to the tooltip.
                for metric_col in row.index:
                    if metric_col.startswith(("Current_", "Previous_")):
                        value = row[metric_col]
                        enriched[metric_col] = None if pd.isna(value) else float(value)
                enriched["Selected_Month"] = (
                    str(selected_month) if C["month"] else "All months"
                )
                enriched["Comparison_Month"] = (
                    comparison_month or "Previous month unavailable"
                )
                enriched["Fusion_PIN_Status"] = (
                    "Fusion PIN Found"
                    if enriched["PIN_Count"] > 0
                    else "No Fusion PIN Found in this District"
                )
                enriched["Risk_Band"] = (
                    "No Fusion PIN Found"
                    if enriched["PIN_Count"] == 0
                    else (
                        "No PAR90 data"
                        if pd.isna(row["PAR90"])
                        else (
                            "Lower risk (<2%)"
                            if row["PAR90"] < 2
                            else (
                                "Watch (2% to <4%)"
                                if row["PAR90"] < 4
                                else "High risk (≥4%)"
                            )
                        )
                    )
                )
            feature_copy = {
                "type": "Feature",
                "geometry": feature.get("geometry"),
                "properties": enriched,
            }
            district_features.append(feature_copy)

        # Dissolve district boundaries into state polygons with invalid-geometry repair.
        from shapely.geometry import shape
        from shapely.ops import unary_union

        try:
            from shapely import make_valid
        except ImportError:
            make_valid = None

        state_features = []
        state_lookup = {
            state_key(row["State"]): row for _, row in state_data.iterrows()
        }

        state_compare_current = build_comparison(f, "Current", [C["state"]])
        state_compare_previous = build_comparison(
            comparison_frame, "Previous", [C["state"]]
        )
        state_compare_lookup = {}
        for compare_frame in [state_compare_current, state_compare_previous]:
            if not compare_frame.empty:
                for _, compare_row in compare_frame.iterrows():
                    state_compare_lookup.setdefault(compare_row["Map_Key"], {}).update(
                        {
                            col: compare_row[col]
                            for col in compare_frame.columns
                            if col != "Map_Key"
                        }
                    )

        states_in_geo = {}
        for feature in district_features:
            props = feature["properties"]
            states_in_geo.setdefault(
                state_key(props["State"]),
                {
                    "name": props["State"],
                    "geometries": [],
                },
            )["geometries"].append(feature["geometry"])

        for s_key, item in states_in_geo.items():
            state_row = state_lookup.get(s_key)
            valid_geometries = []
            for raw in item["geometries"]:
                try:
                    geom = shape(raw)
                    if geom.is_empty:
                        continue
                    if not geom.is_valid:
                        geom = make_valid(geom) if make_valid else geom.buffer(0)
                    if not geom.is_empty:
                        valid_geometries.append(geom)
                except Exception:
                    continue
            if not valid_geometries:
                continue
            try:
                union_geom = unary_union(valid_geometries)
            except Exception:
                repaired = [
                    (make_valid(g) if make_valid else g.buffer(0))
                    for g in valid_geometries
                ]
                union_geom = unary_union(repaired)
            if union_geom.is_empty:
                continue

            if state_row is None:
                state_name = str(item["name"])
                props = {
                    "Level": "State",
                    "State": state_name,
                    "District": "All districts",
                    "PIN_Count": 0,
                    "Negative_PIN_Count": 0,
                    "Non_Negative_PIN_Count": 0,
                    "PAR90": None,
                    "PAR0": None,
                    "Disbursement": None,
                    "POS": None,
                    "Fusion_PIN_Status": "No Fusion PIN Found",
                    "Risk_Band": "No Fusion PIN Found",
                }
            else:
                row = state_row
                props = {
                    "Level": "State",
                    "State": str(row["State"]),
                    "District": "All districts",
                    "PIN_Count": (
                        int(row["PIN_Count"]) if pd.notna(row["PIN_Count"]) else 0
                    ),
                    "Negative_PIN_Count": (
                        int(row["Negative_PIN_Count"])
                        if pd.notna(row["Negative_PIN_Count"])
                        else 0
                    ),
                    "Non_Negative_PIN_Count": (
                        int(row["Non_Negative_PIN_Count"])
                        if pd.notna(row["Non_Negative_PIN_Count"])
                        else 0
                    ),
                    "PAR90": None if pd.isna(row["PAR90"]) else float(row["PAR90"]),
                    "PAR0": None if pd.isna(row["PAR0"]) else float(row["PAR0"]),
                    "Disbursement": (
                        None
                        if pd.isna(row["Disbursement"])
                        else float(row["Disbursement"])
                    ),
                    "POS": None if pd.isna(row["POS"]) else float(row["POS"]),
                }
                props["Fusion_PIN_Status"] = (
                    "Fusion PIN Found"
                    if props["PIN_Count"] > 0
                    else "No Fusion PIN Found"
                )
                par90 = row["PAR90"]
                props["Risk_Band"] = (
                    "No Fusion PIN Found"
                    if props["PIN_Count"] == 0
                    else (
                        "No PAR90 data"
                        if pd.isna(par90)
                        else (
                            "Lower risk (<2%)"
                            if par90 < 2
                            else "Watch (2% to <4%)" if par90 < 4 else "High risk (≥4%)"
                        )
                    )
                )
            state_map_key = state_key(props["State"]) + "|" + norm("All districts")
            # State-level comparisons use the state key, independent of district.
            state_compare_key = state_key(props["State"]) + "|" + norm("")
            for compare_key in [state_compare_key, state_map_key]:
                if compare_key in state_compare_lookup:
                    for metric_name, metric_value in state_compare_lookup[
                        compare_key
                    ].items():
                        props[metric_name] = (
                            None if pd.isna(metric_value) else float(metric_value)
                        )
                    break
            props["Selected_Month"] = (
                str(selected_month) if C["month"] else "All months"
            )
            props["Comparison_Month"] = comparison_month or "Previous month unavailable"
            state_features.append(
                {
                    "type": "Feature",
                    "geometry": union_geom.__geo_interface__,
                    "properties": props,
                }
            )

        # JSON-safe conversion for NaN and numpy scalar types.
        district_geojson_json = json.dumps(
            {"type": "FeatureCollection", "features": district_features},
            ensure_ascii=False,
            default=str,
            allow_nan=False,
        )
        state_geojson_json = json.dumps(
            {"type": "FeatureCollection", "features": state_features},
            ensure_ascii=False,
            default=str,
            allow_nan=False,
        )

        # The map changes detail level automatically:
        # zoom < 5.2 = state boundaries + state tooltip; zoom >= 5.2 = districts.
        # This is a normal 2D Leaflet map, not a 3D or 4K map.
        map_html = r"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
    <style>
    html, body { margin:0; padding:0; width:100%; height:100%; font-family:Arial, sans-serif; }
    #map { width:100%; height:980px; background:#eef3f7; }
    .leaflet-tooltip.risk-tip {
      background:#fff; border:1px solid #163a5b; border-radius:4px;
      box-shadow:0 3px 12px rgba(0,0,0,.22); color:#172b4d;
      padding:16px 18px; width:620px; min-width:620px; max-width:calc(100vw - 24px);
      white-space:normal; max-height:none; height:auto; overflow:visible; box-sizing:border-box;
    }
    /* Compact month selector and stronger KPI presentation */
    div[data-testid="stSelectbox"] { max-width:680px; }
    div[data-testid="stSelectbox"] label {
        font-size: 15px !important;
        font-weight: 800 !important;
        color: #173b60 !important;
    }
    div[data-testid="stSelectbox"] div[data-baseweb="select"] {
        min-height: 34px !important;
        font-size: 14px !important;
    }
    div[data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #d4dfeb;
        border-radius: 9px;
        padding: 12px 14px;
    }
    div[data-testid="stMetricLabel"] p {
        font-size: 14px !important;
        font-weight: 800 !important;
        color: #173b60 !important;
    }
    div[data-testid="stMetricValue"] {
        font-size: 25px !important;
        font-weight: 900 !important;
        color: #102f50 !important;
    }

    .tip-title { font-size:28px; font-weight:900; margin-bottom:12px; color:#102b46; line-height:1.2; overflow-wrap:anywhere; }
    .tip-row { font-size:18px; line-height:1.35; }
    .tip-table { width:100%; table-layout:fixed; border-collapse:separate; border-spacing:0; margin:8px 0 14px; font-size:15px; border:1px solid #cbd8e5; border-radius:6px; overflow:hidden; }
    .tip-table th, .tip-table td {
      border:0; border-right:1px solid #d5dce3; border-bottom:1px solid #d5dce3; padding:9px 10px; text-align:right;
      vertical-align:middle; line-height:1.25; overflow-wrap:normal; word-break:normal; font-weight:700;
    }
    .tip-table th:last-child, .tip-table td:last-child { border-right:0; }
    .tip-table tbody tr:last-child td { border-bottom:0; }
    .tip-table tbody tr:nth-child(even) td:not(.change-good):not(.change-bad):not(.change-neutral):not(.remark-good):not(.remark-bad):not(.remark-neutral) { background:#f8fafc; }
    @media (max-width: 700px) {
      .risk-tip { min-width: min(620px, 92vw) !important; max-width: 92vw !important; }
      .tip-table th, .tip-table td { padding: 8px 9px; }
    }
    /* Fixed, balanced widths: Areas gets the largest share; numeric columns stay aligned. */
    .comparison-table { width:100%; table-layout:fixed; }
    .comparison-table th:nth-child(1), .comparison-table td:nth-child(1) { width:31%; text-align:left; }
    .comparison-table th:nth-child(2), .comparison-table td:nth-child(2) { width:16%; }
    .comparison-table th:nth-child(3), .comparison-table td:nth-child(3) { width:17.5%; }
    .comparison-table th:nth-child(4), .comparison-table td:nth-child(4) { width:17.5%; }
    .comparison-table th:nth-child(5), .comparison-table td:nth-child(5) { width:18%; text-align:center; }
    .comparison-table td:first-child { overflow-wrap:anywhere; word-break:normal; }
    .comparison-table td:nth-child(2),
    .comparison-table td:nth-child(3),
    .comparison-table td:nth-child(4) { white-space:nowrap; font-variant-numeric:tabular-nums; }
    .comparison-table td:nth-child(5) { white-space:normal; overflow-wrap:anywhere; }
    .tip-table th { background:#eaf0f6; color:#173b60; font-weight:900; font-size:15px; text-align:center; }
    .tip-table th:first-child { text-align:left; }
    .tip-table .change-good, .tip-table .remark-good { color:#166534; background:#dcfce7; font-weight:800; }
    .tip-table .change-bad, .tip-table .remark-bad { color:#991b1b; background:#fee2e2; font-weight:800; }
    .tip-table .change-neutral, .tip-table .remark-neutral { color:#475569; background:#f1f5f9; font-weight:800; }
    .monthly-disb-table { width:100%; table-layout:fixed; }
    .monthly-disb-table th:first-child, .monthly-disb-table td:first-child { width:38%; text-align:left; white-space:nowrap; }
    .monthly-disb-table th:nth-child(2), .monthly-disb-table td:nth-child(2) { width:62%; white-space:nowrap; }
    .monthly-disb-table td:nth-child(2) { font-variant-numeric:tabular-nums; }
    .tip-status { margin:12px 0 14px; padding:22px 24px; border-radius:6px; background:#EEF1F4;
      color:#374151; font-size:18px; font-weight:900; border:1px solid #D5DCE3; }
    .tip-negative-alert { margin:10px 0 12px; padding:11px 13px; border-radius:6px;
      background:#F3E8FF; color:#6B21A8; border:2px solid #7C3AED;
      font-size:18px; font-weight:900; line-height:1.4; }
    .map-label-icon { background:transparent; border:0; }
    .state-map-label, .district-map-label {
      background:rgba(255,255,255,.90); border:1px solid rgba(43,65,83,.55);
      border-radius:4px; box-shadow:0 1px 4px rgba(0,0,0,.18); color:#152b40;
      padding:3px 5px; font-weight:800; white-space:normal; text-align:center;
      pointer-events:none; transform:translate(-50%,-50%);
    }
    .state-map-label { font-size:17px; max-width:190px; line-height:1.25; padding:4px 7px; }
    .district-map-label { font-size:15px; max-width:260px; line-height:1.35; padding:4px 7px; }
    .tip-row b { font-weight:700; }
    .legend {
     position:absolute; z-index:1000; bottom:22px; right:18px; background:#fff;
     padding:12px 14px; border:1px solid #ccd5df; border-radius:8px;
     box-shadow:0 2px 8px #0002; font-size:13px; line-height:1.8;
    }
    .legend strong { display:block; margin-bottom:3px; font-size:14px; }
    .swatch { display:inline-block; width:13px; height:13px; border:1px solid #6b7280;
     margin-right:6px; vertical-align:-2px; }
    .level-tag {
     position:absolute; z-index:1000; top:12px; left:55px; background:#fff;
     padding:8px 12px; border-radius:7px; border:1px solid #d4dce5;
     box-shadow:0 2px 7px #0002; font-size:13px; font-weight:700; color:#173b60;
    }
    #backButton { position:absolute; z-index:1001; top:54px; left:55px; padding:8px 12px;
     border:1px solid #cbd5e1; border-radius:7px; background:#fff; color:#173b60;
     font-weight:700; cursor:pointer; box-shadow:0 2px 7px #0002; }
    #backButton:hover { background:#edf4fb; }
    </style>
    </head>
    <body>
    <div id="map"></div>
    <div class="level-tag" id="levelTag">State-level view</div>
    <button id="backButton" type="button" style="display:none" onclick="showAllStates()">← All States</button>
    <div class="legend">
      <strong>PAR 90% Disb Risk</strong>
      <div><span class="swatch" style="background:#B7E4C7"></span>Below 2% — lower risk</div>
      <div><span class="swatch" style="background:#FFD966"></span>2% to below 4% — watch</div>
      <div><span class="swatch" style="background:#C62828"></span>4% or above — high risk</div>
      <div><span class="swatch" style="background:#B9C2CC"></span>Missing — unavailable</div>
      <div><span class="swatch" style="background:#fff;border:3px solid #7C3AED;width:13px;height:13px"></span>At least 1 Negative PIN</div>
    </div>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
    const districtData = __DISTRICT_GEOJSON__;
    const stateData = __STATE_GEOJSON__;
    const map = L.map('map', {preferCanvas:true, zoomControl:true, scrollWheelZoom:true})
      .setView([22.8, 79.0], 4.2);

    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
      maxZoom: 19
    }).addTo(map);

    function bandColor(props) {
      const band = props.Risk_Band;
      if (band === 'Lower risk (<2%)') return '#B7E4C7';
      if (band === 'Watch (2% to <4%)') return '#FFD966';
      if (band === 'High risk (≥4%)') return '#C62828';
      return '#B9C2CC';
    }
    function numberIN(value, decimals=0) {
      if (value === null || value === undefined || value === '' || Number.isNaN(Number(value))) return 'Not available';
      return Number(value).toLocaleString('en-IN', {minimumFractionDigits:decimals, maximumFractionDigits:decimals});
    }
    function percent(value) {
      return value === null || value === undefined ? 'Not available' : numberIN(value, 2) + '%';
    }
    function amount(value) {
      return value === null || value === undefined ? 'Not available' : '₹' + numberIN(value, 2) + ' Cr';
    }
    function safeText(value) {
      return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/\"/g, '&quot;').replace(/'/g, '&#39;');
    }
    function tooltipHTML(p) {
      const jsonName = String(p.Original_District || p.District || '').trim();
      const fusionName = String(p.Fusion_District || p.District || '').trim();
      const namesDiffer = p.Level === 'District' && keyText(jsonName) !== keyText(fusionName);
      // When spellings differ, show both names in the title and in a dedicated row.
      const title = p.Level === 'State' ? safeText(p.State) :
        safeText(namesDiffer ? (fusionName + ' / ' + jsonName) : (fusionName || jsonName));
      const subtitle = p.Level === 'State' ? 'State-level portfolio' : ('State: ' + safeText(p.State));
      const nameLine = namesDiffer
        ? '<div class="tip-row"><b>District names (Fusion / GeoJSON):</b> ' +
          safeText(fusionName) + ' / ' + safeText(jsonName) + '</div>'
        : '';
      const noFusionData = Number(p.PIN_Count || 0) === 0 || p.Fusion_PIN_Status === 'No Fusion PIN Found';
      const statusText = p.Level === 'State'
        ? 'No Fusion PIN Found'
        : 'No Fusion PIN Found in this District';
      const statusHTML = noFusionData
        ? '<div class="tip-status">' + statusText + '</div>'
        : '<div class="tip-status">Fusion PIN Found</div>';
      const currentMonth = p.Selected_Month || 'Selected month';
      const previousMonth = p.Comparison_Month || 'Previous month';
      const fmtVal = v => (v === null || v === undefined || Number.isNaN(Number(v))) ? '—' : numberIN(v);
      const fmtCr = v => (v === null || v === undefined || Number.isNaN(Number(v))) ? '—' : amount(v).replace(/\\sCr$/, '\\u00A0Cr');
      const fmtPct = v => (v === null || v === undefined || Number.isNaN(Number(v))) ? '—' : percent(v);
      const changePct = (current, previous) => {
        const c = Number(current), p0 = Number(previous);
        if (current === null || current === undefined || previous === null || previous === undefined ||
            !Number.isFinite(c) || !Number.isFinite(p0)) return null;
        if (p0 === 0) return c === 0 ? 0 : null;
        return ((c - p0) / Math.abs(p0)) * 100;
      };
      const changeText = v => v === null ? '—' : (v > 0 ? '+' : '') + v.toFixed(2) + '%';
      const remarkText = v => v === null ? '—' : (Math.abs(v) < 0.005 ? '•' : (v > 0 ? '▲' : '▼'));
      const comparisonRows = [
        {label:'Total PIN Count', key:'PIN_Count', format:fmtVal},
        {label:'Neg. PIN Count', key:'Negative_PIN_Count', format:fmtVal},
        {label:'No Neg. PIN Count', key:'Non_Negative_PIN_Count', format:fmtVal},
        {label:'Disb. (Cr.)', key:'Monthly_Disbursement', format:fmtCr},
        {label:'Cumu. Disb. (Cr.)', key:'Disbursement', format:fmtCr},
        {label:'PAR 0 Disb % +WO', key:'PAR0', format:fmtPct},
        {label:'PAR 90 Disb % +WO', key:'PAR90', format:fmtPct}
      ];
      const changeClass = (item, delta) => {
        if (delta === null || Math.abs(delta) < 0.005) return 'neutral';
        // Higher PAR and more negative PINs are adverse; higher non-negative PINs/disbursement are favourable.
        const adverseWhenUp = ['Negative_PIN_Count', 'PAR0', 'PAR90'].includes(item.key);
        const favourable = adverseWhenUp ? delta < 0 : delta > 0;
        return favourable ? 'good' : 'bad';
      };
      let comparisonTable = '<div class="tip-row"><b>Month-on-Month Comparison</b></div>' +
        '<table class="tip-table comparison-table"><colgroup>' +
        '<col style="width:31%"><col style="width:16%"><col style="width:17.5%"><col style="width:17.5%"><col style="width:18%">' +
        '</colgroup><thead><tr><th>Areas</th><th>Changes%</th><th>' +
        safeText(currentMonth) + '</th><th>' + safeText(previousMonth) +
        '</th><th>Remark</th></tr></thead><tbody>';
      comparisonRows.forEach(item => {
        const current = p['Current_' + item.key];
        const previous = p['Previous_' + item.key];
        const delta = changePct(current, previous);
        const status = changeClass(item, delta);
        const remarkClass = status === 'good' ? 'remark-good' : status === 'bad' ? 'remark-bad' : 'remark-neutral';
        const changeCellClass = status === 'good' ? 'change-good' : status === 'bad' ? 'change-bad' : 'change-neutral';
        comparisonTable += '<tr><td>' + safeText(item.label) + '</td><td class="' + changeCellClass + '">' + changeText(delta) +
          '</td><td>' + item.format(current) + '</td><td>' + item.format(previous) +
          '</td><td class="' + remarkClass + '">' + safeText(remarkText(delta)) + '</td></tr>';
      });
      comparisonTable += '</tbody></table>';

      const monthRank = {jan:1, feb:2, mar:3, apr:4, may:5, jun:6, jul:7, aug:8, sep:9, oct:10, nov:11, dec:12};
      const disbKeys = Object.keys(p).filter(k => k.startsWith('Current_') && /disb$/.test(k) && !['Current_Disbursement'].includes(k));
      disbKeys.sort((a, b) => {
        const la = a.replace(/^Current_/, '').toLowerCase();
        const lb = b.replace(/^Current_/, '').toLowerCase();
        const ma = la.match(/(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec).*?(\d{2,4})/);
        const mb = lb.match(/(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec).*?(\d{2,4})/);
        if (!ma || !mb) return 0;
        const ya = Number(ma[2].length === 2 ? '20' + ma[2] : ma[2]);
        const yb = Number(mb[2].length === 2 ? '20' + mb[2] : mb[2]);
        return (yb * 12 + monthRank[mb[1]]) - (ya * 12 + monthRank[ma[1]]);
      });
      let monthlyDisbHTML = '<div class="tip-row"><b>Recent Monthly Disbursement</b></div><table class="tip-table monthly-disb-table"><thead><tr><th>Month</th><th>Disbursement</th></tr></thead><tbody>';
      let shownDisb = 0;
      disbKeys.slice(0, 3).forEach(k => {
        const rawLabel = k.replace(/^Current_/, '').replace(/disb$/i, '').trim();
        const monthMatch = rawLabel.match(/(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[^0-9]*(\d{2,4})/i);
        let label = rawLabel;
        if (monthMatch) {
          const monthNames = {jan:'Jan',feb:'Feb',mar:'Mar',apr:'Apr',may:'May',jun:'Jun',jul:'Jul',aug:'Aug',sep:'Sep',oct:'Oct',nov:'Nov',dec:'Dec'};
          const year = monthMatch[2].length === 2 ? monthMatch[2] : monthMatch[2].slice(-2);
          label = monthNames[monthMatch[1].toLowerCase()] + '-' + year;
        }
        monthlyDisbHTML += '<tr><td>' + safeText(label) + '</td><td>' + fmtCr(p[k]) + '</td></tr>';
        shownDisb += 1;
      });
      if (!shownDisb) monthlyDisbHTML += '<tr><td colspan="2">Monthly Disb columns not detected</td></tr>';
      monthlyDisbHTML += '</tbody></table>';

      return '<div class="tip-title">' + title + '</div>' +
        '<div class="tip-row"><b>' + subtitle + '</b></div>' +
        nameLine + statusHTML +
        '<div class="tip-row">Current PIN Count: <b>' + numberIN(p.PIN_Count) + '</b></div>' +
        (Number(p.Negative_PIN_Count || 0) > 0
          ? '<div class="tip-negative-alert">⚠ Negative PIN Alert: At least 1 Negative PIN Code</div>'
          : '') +
        comparisonTable + monthlyDisbHTML +
        '<div class="tip-row">Risk Band: <b>' + safeText(p.Risk_Band) + '</b></div>';
    }
    function styleFeature(feature) {
      const p = feature.properties || {};
      const hasNegativePin = Number(p.Negative_PIN_Count || 0) > 0;
      // Preserve the PAR90 fill colour, but mark every state/district with any
      // negative PIN using a prominent purple outline.
      return {
        fillColor: bandColor(p),
        weight: hasNegativePin ? (p.Level === 'State' ? 4.2 : 3.2) : (p.Level === 'State' ? 1.8 : 1.0),
        opacity: 1,
        color: hasNegativePin ? '#7C3AED' : (p.Level === 'State' ? '#496173' : '#536878'),
        dashArray: hasNegativePin ? '5 3' : null,
        fillOpacity: 0.86
      };
    }
    let selectedStateName = null;
    let districtLayer = null;
    let activeLayer = null;

    function keyText(value) {
      return String(value ?? '').toLowerCase().replace(/[^a-z0-9]/g, '');
    }
    function stateKey(value) {
      const key = keyText(value);
      const aliases = {
        'orissa':'odisha', 'uttaranchal':'uttarakhand',
        'nctofdelhi':'delhi', 'nationalcapitalterritoryofdelhi':'delhi',
        'pondicherry':'puducherry'
      };
      return aliases[key] || key;
    }
    function removeActiveLayer() {
      if (activeLayer && map.hasLayer(activeLayer)) map.removeLayer(activeLayer);
      activeLayer = null;
    }
    function districtMapLabel(p) {
      const jsonName = String(p.Original_District || p.District || '').trim();
      const fusionName = String(p.Fusion_District || p.District || '').trim();
      // Same spelling: show one name. Different spelling: show both names on the map.
      if (keyText(jsonName) === keyText(fusionName)) return jsonName || fusionName;
      if (!jsonName) return fusionName;
      if (!fusionName) return jsonName;
      return jsonName + ' / ' + fusionName;
    }
    function onEachFeature(feature, layer) {
      // Keep the data tooltip on the polygon. Map labels are separate marker layers
      // so permanent labels do not overwrite this hover tooltip.
      layer.bindTooltip(tooltipHTML(feature.properties), {
        className:'risk-tip', sticky:true, direction:'top', offset:[0,-10], opacity:1
      });
      layer.on({
        mouseover: function(e) {
          const l = e.target;
          l.setStyle({weight:2.4, color:'#142d43', fillOpacity:0.96});
          if (!L.Browser.ie && !L.Browser.opera && !L.Browser.edge) l.bringToFront();
        },
        mouseout: function(e) {
          if (activeLayer) activeLayer.resetStyle(e.target);
        },
        click: function(e) {
          const props = feature.properties || {};
          if (props.Level === 'State') {
            // Stay in this state until the user presses "All States".
            // This guarantees no other state's districts can appear.
            selectedStateName = props.State;
            showSelectedState(selectedStateName, e.target);
          }
        }
      });
    }

    const stateLayer = L.geoJSON(stateData, {style:styleFeature, onEachFeature:onEachFeature});
    let stateLabelsLayer = L.layerGroup();
    let districtLabelsLayer = L.layerGroup();

    function labelMarker(latlng, text, className) {
      return L.marker(latlng, {
        interactive:false, keyboard:false, zIndexOffset:1000,
        icon:L.divIcon({className:'map-label-icon', html:'<div class="' + className + '">' + text + '</div>', iconSize:null})
      });
    }
    function makeStateLabels() {
      const labels = L.layerGroup();
      stateLayer.eachLayer(function(layer) {
        const p = layer.feature && layer.feature.properties ? layer.feature.properties : {};
        if (!p.State) return;
        const center = layer.getBounds().getCenter();
        labels.addLayer(labelMarker(center, String(p.State), 'state-map-label'));
      });
      return labels;
    }
    function makeDistrictLabels(layerGroup) {
      const labels = L.layerGroup();
      layerGroup.eachLayer(function(layer) {
        const p = layer.feature && layer.feature.properties ? layer.feature.properties : {};
        if (!p.District) return;
        const center = layer.getBounds().getCenter();
        labels.addLayer(labelMarker(center, districtMapLabel(p), 'district-map-label'));
      });
      return labels;
    }
    stateLabelsLayer = makeStateLabels();

    function buildDistrictLayer(stateName) {
      const wantedKey = stateKey(stateName);
      const filteredFeatures = districtData.features.filter(f => {
        const props = f.properties || {};
        return stateKey(props.State) === wantedKey;
      });
      if (districtLayer && map.hasLayer(districtLayer)) map.removeLayer(districtLayer);
      districtLayer = L.geoJSON({type:'FeatureCollection', features:filteredFeatures}, {
        style:styleFeature, onEachFeature:onEachFeature
      });
      return districtLayer;
    }

    function showSelectedState(stateName, clickedLayer=null) {
      selectedStateName = stateName;
      const filtered = buildDistrictLayer(stateName);
      removeActiveLayer();
      if (map.hasLayer(stateLabelsLayer)) map.removeLayer(stateLabelsLayer);
      if (map.hasLayer(districtLabelsLayer)) map.removeLayer(districtLabelsLayer);
      activeLayer = filtered;
      activeLayer.addTo(map);
      districtLabelsLayer = makeDistrictLabels(filtered);
      districtLabelsLayer.addTo(map);
      document.getElementById('levelTag').textContent = 'Districts of ' + stateName;
      document.getElementById('backButton').style.display = 'block';

      // Zoom to the selected state's district boundaries, if available.
      if (filtered.getLayers().length > 0) {
        map.fitBounds(filtered.getBounds(), {padding:[24,24], maxZoom:7});
      } else if (clickedLayer) {
        map.fitBounds(clickedLayer.getBounds(), {padding:[24,24], maxZoom:7});
        console.warn('No district boundary matched state:', stateName,
          'Available district states:', [...new Set(districtData.features.map(f => f.properties.State))]);
      }
    }

    function showAllStates() {
      selectedStateName = null;
      if (districtLayer && map.hasLayer(districtLayer)) map.removeLayer(districtLayer);
      if (map.hasLayer(districtLabelsLayer)) map.removeLayer(districtLabelsLayer);
      removeActiveLayer();
      activeLayer = stateLayer;
      activeLayer.addTo(map);
      stateLabelsLayer.addTo(map);
      document.getElementById('levelTag').textContent = 'State-level view · click a state to drill down';
      document.getElementById('backButton').style.display = 'none';
      map.setView([22.8, 79.0], 4.2);
    }

    // Initial view always displays state polygons. A state click switches to only
    // that state's district polygons; zooming in/out never adds other states.
    activeLayer = stateLayer;
    activeLayer.addTo(map);
    stateLabelsLayer.addTo(map);
    </script>
    </body>
    </html>
    """
        map_html = map_html.replace("__DISTRICT_GEOJSON__", district_geojson_json)
        map_html = map_html.replace("__STATE_GEOJSON__", state_geojson_json)
        components.html(map_html, height=1000, scrolling=False)

        st.markdown(
            "**Map behaviour:** hover for tooltips. Click a state to show only that state's districts. "
            "Use the **All States** button to return to the India state map. Red means PAR 90% Disb ≥ 4%, "
            "not that the PIN Negative Flag is present."
        )
    else:
        st.error(
            "No valid district GeoJSON boundaries were loaded. "
            f"GeoJSON search folder: {STATE_DIR}. "
            "The folder must contain district-level .geojson files with a district-name field "
            "(for example district, districtname, distname, dtname, or name_2)."
        )
        if geo_errors:
            with st.expander("GeoJSON file diagnostics"):
                for geo_error in geo_errors:
                    st.write(f"- {geo_error}")
        elif not state_files:
            st.info(
                "No .geojson files were found in the searched folder or its subfolders."
            )

    # ----------------------------- RANKING MATRICES -----------------------------
    # Keep the portfolio rank tables below the map so users can first inspect
    # the geography and then compare the same metrics in a sortable format.
    def build_rank_matrix(frame, group_cols, group_labels):
        work = frame.dropna(subset=group_cols).copy()
        for group_col in group_cols:
            work = work[work[group_col].astype("string").str.strip().ne("")]

        if work.empty:
            return pd.DataFrame(columns=group_labels)

        matrix = aggregate_portfolio(work, group_cols, C)
        matrix = add_negative_counts(matrix, negative_rows, group_cols, C)

        if C["loans"]:
            loans = (
                work.groupby(group_cols, dropna=False)[C["loans"]]
                .sum(min_count=1)
                .reset_index(name="Total Loan Count")
            )
            matrix = matrix.merge(loans, on=group_cols, how="left")
        else:
            matrix["Total Loan Count"] = float("nan")

        latest_column = monthly_disb_col(selected_month) if C["month"] else None
        if latest_column and latest_column in work.columns:
            latest_disb = (
                work.groupby(group_cols, dropna=False)[latest_column]
                .sum(min_count=1)
                .reset_index(name="Latest Disb (Cr.)")
            )
            matrix = matrix.merge(latest_disb, on=group_cols, how="left")
        else:
            matrix["Latest Disb (Cr.)"] = float("nan")

        matrix = matrix.rename(
            columns={
                **dict(zip(group_cols, group_labels)),
                "Negative_PIN_Count": "Neg. PIN Count",
                "Non_Negative_PIN_Count": "No Neg. PIN Count",
                "Disbursement": "Total Disb (Cr.)",
                "PAR0": "PAR 0 Disb %",
                "PAR90": "PAR 90 Disb %",
                "POS": "POS (Cr.)",
            }
        )
        metric_columns = [
            "Neg. PIN Count",
            "No Neg. PIN Count",
            "Total Disb (Cr.)",
            "PAR 0 Disb %",
            "PAR 90 Disb %",
            "Latest Disb (Cr.)",
            "POS (Cr.)",
            "Total Loan Count",
        ]
        return (
            matrix[group_labels + metric_columns]
            .sort_values("Total Disb (Cr.)", ascending=False, na_position="last")
            .reset_index(drop=True)
        )

    def matrix_xlsx_bytes(matrix, sheet_name):
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            matrix.to_excel(writer, sheet_name=sheet_name, index=False)
            sheet = writer.sheets[sheet_name]
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            for cell in sheet[1]:
                cell.font = cell.font.copy(bold=True)
            for column_cells in sheet.columns:
                width = max(len(str(cell.value or "")) for cell in column_cells) + 2
                sheet.column_dimensions[column_cells[0].column_letter].width = min(
                    width, 28
                )
        return output.getvalue()

    def show_rank_matrix(title, matrix, sheet_name, download_name, key):
        with st.container(border=True):
            with st.container(
                horizontal=True, vertical_alignment="center", gap="small"
            ):
                st.subheader(title)
                st.download_button(
                    "Download Excel",
                    data=matrix_xlsx_bytes(matrix, sheet_name),
                    file_name=download_name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=key,
                    icon=":material/download:",
                )

            if matrix.empty:
                st.info("No records are available for this view.")
                return

            row_limit = st.slider(
                "Rows to show",
                min_value=5,
                max_value=max(5, len(matrix)),
                value=min(25, len(matrix)),
                key=f"{key}_top_n",
            )
            shown = matrix.head(row_limit)
            st.caption("Sorted high to low by Total Disb (Cr.).")
            st.dataframe(
                shown,
                hide_index=True,
                width="stretch",
                column_config={
                    "Neg. PIN Count": st.column_config.NumberColumn(format="%d"),
                    "No Neg. PIN Count": st.column_config.NumberColumn(format="%d"),
                    "Total Disb (Cr.)": st.column_config.NumberColumn(
                        format="₹%.2f Cr"
                    ),
                    "PAR 0 Disb %": st.column_config.NumberColumn(format="%.2f%%"),
                    "PAR 90 Disb %": st.column_config.NumberColumn(format="%.2f%%"),
                    "Latest Disb (Cr.)": st.column_config.NumberColumn(
                        format="₹%.2f Cr"
                    ),
                    "POS (Cr.)": st.column_config.NumberColumn(format="₹%.2f Cr"),
                    "Total Loan Count": st.column_config.NumberColumn(format="%d"),
                },
            )

    st.subheader("Portfolio ranking matrices")
    st.caption("Numeric figures are ranked high to low by Total Disb (Cr.).")

    state_matrix = build_rank_matrix(f, [C["state"]], ["State"])
    show_rank_matrix(
        "State-wise portfolio ranking",
        state_matrix,
        "State-wise ranking",
        "state_wise_portfolio_ranking.xlsx",
        "download_state_portfolio_ranking",
    )

    detail_view = st.segmented_control(
        "Detail view",
        options=["District-wise", "Branch-wise"],
        default="District-wise",
        key="pin_ranking_detail_view",
    )
    if detail_view == "Branch-wise" and C["branch"]:
        detail_matrix = build_rank_matrix(
            f, [C["state"], C["district"], C["branch"]], ["State", "District", "Branch"]
        )
        detail_title, detail_sheet, detail_file = (
            "Branch-wise portfolio ranking",
            "Branch-wise ranking",
            "branch_wise_portfolio_ranking.xlsx",
        )
    else:
        detail_matrix = build_rank_matrix(
            f, [C["state"], C["district"]], ["State", "District"]
        )
        detail_title, detail_sheet, detail_file = (
            "District-wise portfolio ranking",
            "District-wise ranking",
            "district_wise_portfolio_ranking.xlsx",
        )
        if detail_view == "Branch-wise":
            st.warning(
                "Branch column was not detected, so district-wise ranking is shown."
            )

    show_rank_matrix(
        detail_title,
        detail_matrix,
        detail_sheet,
        detail_file,
        "download_detail_portfolio_ranking",
    )
