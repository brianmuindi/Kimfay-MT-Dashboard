# mt_unvisited_report_dashboard_v4.py
# Executive-safe Streamlit dashboard (Unvisited Outlets + Off-Route + Leave + Status Updates)
# - Auth (streamlit-authenticator; version-safe)
# - Light-mode UI + readable hover buttons
# - Friendly errors (no raw traceback)
# - Save uploads once to ./data_uploads and reuse on refresh/restart
# - Filters apply across ALL tabs (date/region/supervisor/rep/key accounts where possible)
# - Rep views ALWAYS include Supervisor + Region
# - Download exports include ALL modules (filtered + full)

from __future__ import annotations

import io
import inspect
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
import streamlit as st
import numpy as np

# ----------------------------
# STANDARD MASTER LISTS
# ----------------------------
STANDARD_SUPERVISORS = [
    "Stephen Otieno",
    "Lucy Wangui",
    "Lilian Kimanthi",
    "Zipporah Wangari",
    "Diana Akinyi",
    "Pauline Mugodo",
    "Caroline Gakii",
    "Collins Ochieng",
]

STANDARD_REGIONS = [
    "Nairobi",
    "Mountain",
    "Lake",
    "Coast",
    "Rift Valley",
]

STANDARD_KEY_ACCOUNTS = [
    "Naivas",
    "Quickmart",
    "Chandarana",
    "Magunas",
    "Carrefour",
]


# ----------------------------
# STANDARDIZATION HELPERS
# ----------------------------
def standardize_supervisor(name):
    if pd.isna(name):
        return "UNKNOWN / UNMAPPED"

    name = str(name).strip()
    name = name.split("@")[0]
    name = " ".join(name.split())

    for sup in STANDARD_SUPERVISORS:
        if name.lower() in sup.lower() or sup.lower() in name.lower():
            return sup

    return "UNKNOWN / UNMAPPED"


def standardize_region(region):
    if pd.isna(region):
        return "UNKNOWN / UNMAPPED"

    region = str(region).upper().strip()

    mapping = {
        "MT": "Mountain",
        "MOUNTAI": "Mountain",
        "MOUNTAINS": "Mountain",
        "NAIROBI EAST": "Nairobi",
        "NAIROBI WEST": "Nairobi",
    }

    if region in mapping:
        return mapping[region]

    for r in STANDARD_REGIONS:
        if r.upper() == region:
            return r

    return "UNKNOWN / UNMAPPED"


def detect_key_account(customer) -> str:
    """Return standardized key account name if CUSTOMER contains one; else empty string."""
    if pd.isna(customer):
        return ""
    c = str(customer).upper()

    if "NAIVAS" in c:
        return "Naivas"
    if "CHANDARANA" in c:
        return "Chandarana"
    if "MAGUNAS" in c:
        return "Magunas"
    if "CARREFOUR" in c:
        return "Carrefour"
    if "QUICKMART" in c or "QUICKMATT" in c:
        return "Quickmart"

    return ""


def remove_test_reps(series: pd.Series) -> pd.Series:
    """Remove reps with MERCH TEST or ORDER in their name (test/system accounts)."""
    s = series.astype("string")
    mask = (
        s.str.upper().str.contains("MERCH TEST", na=False)
        | s.str.upper().str.contains("ORDER", na=False)
    )
    s[mask] = pd.NA
    return s



# ----------------------------
# CONFIG

# ----------------------------
APP_TITLE = "📊 Unvisited Outlets — Executive Dashboard"

UNVISITED_DEFAULT = "unvisited_outlets_1770194316603.xlsx"
MERCH_DEFAULT = "Field Merchandisers.xlsx"

KEY_CUSTOMERS = ["CHANDARANA", "CARREFOUR", "NAIVAS", "QUICKMART", "MAGUNAS"]


# Benchmarks / thresholds (can be overridden in sidebar)
DEFAULT_MAX_UNVISITED_PER_REP = 2
DEFAULT_MAX_UNVISITED_PER_SUPERVISOR = 10
DEFAULT_MAX_KEY_ACCOUNT_UNVISITED = 10

DATA_DIR = Path("data_uploads")
DATA_DIR.mkdir(exist_ok=True)

SAVED_UNVISITED_NAME = "unvisited_outlets.xlsx"
SAVED_MERCH_NAME = "field_merchandisers.xlsx"

# Extra modules
SAVED_OFFROUTE_NAME = "off_route_requests.xlsx"
SAVED_LEAVE_NAME = "leave_management.csv"
SAVED_STATUS_CSV_NAME = "status_update.csv"
SAVED_STATUS_XLSX_NAME = "status_update.xlsx"

st.set_page_config(
    page_title="Unvisited Outlets Executive Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ----------------------------
# UI (LIGHT THEME + BUTTON HOVER READABILITY)
# ----------------------------
def inject_light_theme_css() -> None:
    st.markdown(
        """
        <style>
          .stApp { background: #f6f7fb; }
          .block-container { padding-top: 1.2rem; padding-bottom: 2rem; }

          /* soften widgets */
          div[data-testid="stMetric"] {
            background: white;
            border: 1px solid rgba(0,0,0,0.06);
            border-radius: 16px;
            padding: 14px 16px;
            box-shadow: 0 8px 22px rgba(0,0,0,0.05);
          }

          /* buttons with readable hover text */
          .stButton>button {
            border-radius: 12px !important;
            border: 1px solid rgba(0,0,0,0.12) !important;
            background: white !important;
            color: #1f2937 !important;
            font-weight: 600 !important;
          }
          .stButton>button:hover {
            background: #111827 !important;
            color: #ffffff !important;
            border-color: #111827 !important;
          }

          /* expander */
          div[data-testid="stExpander"] {
            border: 1px solid rgba(0,0,0,0.08);
            border-radius: 14px;
            background: white;
          }

          /* sidebar */
          section[data-testid="stSidebar"] { background: #fbfbfd; }
          section[data-testid="stSidebar"] .stMarkdown { color: #111827; }

          /* tables */
          .stDataFrame { background: white; border-radius: 12px; }

          /* hide Streamlit footer */
          footer {visibility: hidden;}
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_light_theme_css()


# ----------------------------
# FRIENDLY ERROR HANDLER
# ----------------------------
def friendly_stop(title: str, details: str, hint: Optional[str] = None) -> None:
    st.error(title)
    st.markdown(details)
    if hint:
        st.info(hint)
    st.stop()


# ----------------------------
# FILE HELPERS
# ----------------------------
def save_uploaded_file(uploaded, save_as_name: str) -> Path:
    out_path = DATA_DIR / save_as_name
    out_path.write_bytes(uploaded.getvalue())
    return out_path


def read_excel_safely(path: Path, friendly_name: str) -> pd.DataFrame:
    try:
        return pd.read_excel(path)
    except FileNotFoundError:
        friendly_stop(
            f"📁 {friendly_name} not found",
            f"Could not find **{path.name}** in the app folder or saved uploads.",
            "Upload the file using the sidebar.",
        )
    except Exception:
        friendly_stop(
            f"⚠️ Unable to read {friendly_name}",
            "The file may be corrupted or not a valid Excel format.",
            "Try re-saving it as .xlsx, or export to CSV and upload again.",
        )


def read_csv_safely(path: Path, friendly_name: str) -> pd.DataFrame:
    try:
        # Try default comma; if columns look wrong, auto-detect delimiter
        df = pd.read_csv(path)
        if df.shape[1] <= 1:
            df = pd.read_csv(path, sep=None, engine='python')
        return df
    except FileNotFoundError:
        friendly_stop(
            f"📁 {friendly_name} not found",
            f"Could not find **{path.name}** in saved uploads.",
            "Upload the file using the sidebar.",
        )
    except Exception:
        friendly_stop(
            f"⚠️ Unable to read {friendly_name}",
            "The file may be corrupted or not a valid CSV format.",
            "Try exporting again as CSV and re-upload.",
        )


@st.cache_data(show_spinner=False)
def cached_read_excel(path_str: str, friendly_name: str) -> pd.DataFrame:
    return read_excel_safely(Path(path_str), friendly_name)


@st.cache_data(show_spinner=False)
def cached_read_csv(path_str: str, friendly_name: str) -> pd.DataFrame:
    return read_csv_safely(Path(path_str), friendly_name)


# ----------------------------
# DATA CLEANING
# ----------------------------
def standardize_cols(df: pd.DataFrame) -> pd.DataFrame:
    df2 = df.copy()
    df2.columns = [str(c).strip().upper() for c in df2.columns]
    return df2


def normalize_region(series: pd.Series) -> pd.Series:
    s = series.astype("string").str.strip().str.upper()
    # common variants
    s = s.replace(
        {
            "MT": "MOUNTAIN",
            "MOUNTAINS": "MOUNTAIN",
            "NAIROBI EAST": "NAIROBI",
            "NAIROBI WEST": "NAIROBI",
        }
    )
    return s


def norm_name(series: pd.Series) -> pd.Series:
    s = series.astype("string").str.strip().str.lower()
    s = s.str.replace(r"\s+", " ", regex=True)
    return s


def clean_supervisor(series: pd.Series) -> pd.Series:
    s = series.astype("string").fillna("").str.strip()
    s = s.str.replace(r"\s+", " ", regex=True)
    # normalize email-y variants
    s = s.str.replace("@.*$", "", regex=True).str.strip()
    return s


def build_merch_mapping(merch_df: pd.DataFrame) -> pd.DataFrame:
    """Build minimal mapping FULL NAME -> SUPERVISOR/REGION with normalized key."""
    m = standardize_cols(merch_df)

    # Try to infer name column
    name_col = None
    for cand in ["FULL NAME", "NAME", "MERCHANDISER", "SERVICED BY", "DSR"]:
        if cand in m.columns:
            name_col = cand
            break
    if not name_col:
        friendly_stop(
            "Missing columns in Merch file",
            "Could not find a name column like **FULL NAME / NAME / MERCHANDISER**.",
            "Open the merch file and ensure it has a staff name column.",
        )

    # Region + supervisor candidates
    region_col = "REGION" if "REGION" in m.columns else ("REGION NAME" if "REGION NAME" in m.columns else None)
    sup_col = None
    for cand in ["SUPERVISOR", "SUPERVISOR NAME", "TEAM LEADER", "TL"]:
        if cand in m.columns:
            sup_col = cand
            break

    out = pd.DataFrame(
        {
            "FULL_NAME": m[name_col].astype("string"),
            "FULL_NAME_NORM": norm_name(m[name_col]),
        }
    )
    if region_col:
        out["REGION"] = normalize_region(m[region_col])
    else:
        out["REGION"] = pd.NA

    if sup_col:
        out["SUPERVISOR"] = clean_supervisor(m[sup_col])
    else:
        out["SUPERVISOR"] = pd.NA

    out = out.dropna(subset=["FULL_NAME_NORM"]).drop_duplicates("FULL_NAME_NORM")
    return out


def enrich_with_merch(df_in: pd.DataFrame, name_col: str, merch_map: pd.DataFrame) -> pd.DataFrame:
    """Adds REGION + SUPERVISOR_CLEAN using the Reps (merch) mapping.

    Region mapping rule (requested):
    - Use the sales rep's REGION from the reps file to map outlets per region.
    - If the outlet file already has a valid region, we keep it; otherwise we fill from the rep region.
    """
    df = standardize_cols(df_in).copy()
    if name_col.upper() not in df.columns:
        df["REGION"] = df.get("REGION", pd.NA)
        df["SUPERVISOR_CLEAN"] = df.get("SUPERVISOR_CLEAN", pd.NA)
        return df

    col = name_col.upper()
    df[col] = remove_test_reps(df[col])
    df["_NAME_NORM"] = norm_name(df[col])
    mm = merch_map.rename(columns={"FULL_NAME_NORM": "_NAME_NORM"}).copy()

    df = df.merge(mm[["_NAME_NORM", "REGION", "SUPERVISOR"]], on="_NAME_NORM", how="left")

    # Supervisor standardization (force 8)
    if "SUPERVISOR" in df.columns:
        df["SUPERVISOR_CLEAN"] = df["SUPERVISOR"].apply(standardize_supervisor)
    else:
        df["SUPERVISOR_CLEAN"] = df.get("SUPERVISOR_CLEAN", pd.NA)

    # Region mapping using rep region as fallback
    outlet_region = df["REGION_x"] if "REGION_x" in df.columns else df.get("REGION", pd.NA)
    rep_region = df["REGION_y"] if "REGION_y" in df.columns else df.get("REGION", pd.NA)

    outlet_std = pd.Series(outlet_region).apply(standardize_region)
    rep_std = pd.Series(rep_region).apply(standardize_region)

    def is_valid_region(v) -> bool:
        return (not pd.isna(v)) and (str(v).strip() in STANDARD_REGIONS)

    df["REGION"] = [r if is_valid_region(r) else o for o, r in zip(outlet_std, rep_std)]
    df["REGION"] = df["REGION"].fillna("UNKNOWN / UNMAPPED")

    df = df.drop(columns=[c for c in ["REGION_x", "REGION_y"] if c in df.columns], errors="ignore")
    df = df.drop(columns=["_NAME_NORM"], errors="ignore")
    return df


def parse_date(df: pd.DataFrame, col: str) -> pd.DataFrame:
    c = col.upper()
    if c in df.columns:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


# ----------------------------
# KPI CARD
# ----------------------------
def kpi_card(title: str, value: str, note: str = "") -> None:
    st.metric(label=title, value=value, delta=note if note else None)



# ----------------------------
# CHART HELPERS (Streamlit native; no matplotlib dependency)
# ----------------------------
def plot_bar(df: pd.DataFrame, x: str, y: str, title: str) -> None:
    if df is None or df.empty or x not in df.columns or y not in df.columns:
        st.info("No data to plot for current filters.")
        return
    st.subheader(title)
    d = df[[x, y]].copy()
    d[x] = d[x].astype("string").fillna("UNKNOWN")
    d[y] = pd.to_numeric(d[y], errors="coerce").fillna(0)
    d = d.set_index(x)
    st.bar_chart(d[y])

def plot_line(df: pd.DataFrame, x: str, y: str, title: str) -> None:
    if df is None or df.empty or x not in df.columns or y not in df.columns:
        st.info("No data to plot for current filters.")
        return
    st.subheader(title)
    d = df[[x, y]].copy()
    d[y] = pd.to_numeric(d[y], errors="coerce").fillna(0)
    d = d.sort_values(by=x).set_index(x)
    st.line_chart(d[y])


# ----------------------------
# FILTER SUMMARY BANNER
# ----------------------------
def render_filter_banner(date_range, region_sel, supervisor_sel, rep_sel, show_key_only) -> None:
    parts = []
    if date_range:
        parts.append(f"Date: {date_range[0]} → {date_range[1]}")
    if region_sel:
        parts.append(f"Region: {', '.join(region_sel[:6])}{'…' if len(region_sel)>6 else ''}")
    if supervisor_sel:
        parts.append(f"Supervisor: {', '.join(supervisor_sel[:6])}{'…' if len(supervisor_sel)>6 else ''}")
    if rep_sel:
        parts.append(f"Rep: {', '.join(rep_sel[:6])}{'…' if len(rep_sel)>6 else ''}")
    if show_key_only:
        parts.append("Key accounts only")

    msg = " | ".join(parts) if parts else "No filters applied"
    html = (
        "<div style='padding:10px 12px;border-radius:14px;background:white;"
        "border:1px solid rgba(0,0,0,0.06);box-shadow:0 8px 22px rgba(0,0,0,0.05);"
        "margin-bottom:10px;'><b>Active filters:</b> "
        + msg +
        "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


# ----------------------------
# ROOT-CAUSE ENRICHMENT
# ----------------------------
def enrich_root_cause(unv: pd.DataFrame, leave: pd.DataFrame, offroute: pd.DataFrame, status: pd.DataFrame) -> pd.DataFrame:
    """
    Adds ROOT_CAUSE + CAUSE_DETAIL.
    Priority: Leave -> Off-route -> Status update -> Unexplained.
    Works only when unv has DATE and REP.
    """
    d = unv.copy()
    d["ROOT_CAUSE"] = "UNEXPLAINED"
    d["CAUSE_DETAIL"] = ""

    if "DATE" not in d.columns or d["DATE"].isna().all() or "REP" not in d.columns:
        return d

    d["_DAY"] = pd.to_datetime(d["DATE"], errors="coerce").dt.date

    # Leave overlap
    if not leave.empty and {"USER", "REQUEST START", "REQUEST END"}.issubset(set(leave.columns)):
        lv = leave.copy()
        lv["_USER"] = lv["USER"].astype("string")
        lv["_START"] = pd.to_datetime(lv["REQUEST START"], errors="coerce").dt.date
        lv["_END"] = pd.to_datetime(lv["REQUEST END"], errors="coerce").dt.date
        lv = lv.dropna(subset=["_USER", "_START", "_END"])
        for user, g in lv.groupby("_USER", dropna=False):
            mask_user = d["REP"].astype("string") == str(user)
            if not mask_user.any():
                continue
            for _, row in g.iterrows():
                mask = mask_user & (d["_DAY"] >= row["_START"]) & (d["_DAY"] <= row["_END"])
                d.loc[mask, "ROOT_CAUSE"] = "LEAVE"
                cat = str(row.get("CATEGORY", "")).strip()
                d.loc[mask, "CAUSE_DETAIL"] = ("Leave " + cat).strip()

    # Off-route overlap
    if not offroute.empty and "REP NAME" in offroute.columns:
        start_col = "APPROVED START" if "APPROVED START" in offroute.columns else ("REQUEST START" if "REQUEST START" in offroute.columns else None)
        end_col = "APPROVED END" if "APPROVED END" in offroute.columns else ("REQUEST END" if "REQUEST END" in offroute.columns else None)
        if start_col and end_col:
            orr = offroute.copy()
            orr["_REP"] = orr["REP NAME"].astype("string")
            orr["_START"] = pd.to_datetime(orr[start_col], errors="coerce").dt.date
            orr["_END"] = pd.to_datetime(orr[end_col], errors="coerce").dt.date
            orr = orr.dropna(subset=["_REP", "_START", "_END"])
            for rep, g in orr.groupby("_REP", dropna=False):
                mask_rep = d["REP"].astype("string") == str(rep)
                if not mask_rep.any():
                    continue
                for _, row in g.iterrows():
                    mask = mask_rep & (d["_DAY"] >= row["_START"]) & (d["_DAY"] <= row["_END"]) & (d["ROOT_CAUSE"] == "UNEXPLAINED")
                    d.loc[mask, "ROOT_CAUSE"] = "OFF-ROUTE"
                    stt = str(row.get("STATUS", "")).strip()
                    d.loc[mask, "CAUSE_DETAIL"] = ("Off-route " + stt).strip()

    # Status updates same day
    if not status.empty and {"REP NAME", "STATUS DATE"}.issubset(set(status.columns)):
        su = status.copy()
        su["_REP"] = su["REP NAME"].astype("string")
        su["_DAY"] = pd.to_datetime(su["STATUS DATE"], errors="coerce").dt.date
        su = su.dropna(subset=["_REP", "_DAY"])
        cat = su["CATEGORY"].astype("string") if "CATEGORY" in su.columns else pd.Series(["STATUS UPDATE"] * len(su))
        lookup = dict(zip(zip(su["_REP"].astype(str), su["_DAY"]), cat.astype(str)))

        mask_unexp = d["ROOT_CAUSE"] == "UNEXPLAINED"
        idxs = d.loc[mask_unexp].index.tolist()
        for i in idxs:
            r = str(d.at[i, "REP"])
            day = d.at[i, "_DAY"]
            c = lookup.get((r, day))
            if c:
                d.at[i, "ROOT_CAUSE"] = "STATUS UPDATE"
                d.at[i, "CAUSE_DETAIL"] = str(c)

    d = d.drop(columns=["_DAY"], errors="ignore")
    return d


# ----------------------------
# DATA QUALITY
# ----------------------------
def data_quality_summary(unv: pd.DataFrame) -> dict:
    out = {}
    out["Missing REGION"] = int(unv["REGION"].isna().sum()) if "REGION" in unv.columns else 0
    out["Missing SUPERVISOR"] = int(unv["SUPERVISOR_CLEAN"].isna().sum()) if "SUPERVISOR_CLEAN" in unv.columns else 0
    out["Missing REP"] = int(unv["REP"].isna().sum()) if "REP" in unv.columns else 0
    if "CUSTOMER" in unv.columns and "REGION" in unv.columns:
        out["Possible duplicate outlets (CUSTOMER+REGION)"] = int(unv.duplicated(subset=["CUSTOMER", "REGION"]).sum())
    else:
        out["Possible duplicate outlets (CUSTOMER+REGION)"] = 0
    return out



# ----------------------------
# AUTH (SIMPLE SINGLE LOGIN)
# ----------------------------
# This avoids streamlit-authenticator version issues and shows only ONE login form.
# For deployment: put these in .streamlit/secrets.toml:
#   admin_user = "admin"
#   admin_pass = "admin123"
ADMIN_USER = st.secrets.get("admin_user", "admin")
ADMIN_PASS = st.secrets.get("admin_pass", "admin123")

def require_login():
    if st.session_state.get("auth_ok") is True:
        return

    st.title("🔐 Login")
    with st.form("login_form"):
        u = st.text_input("Username", value="admin")
        p = st.text_input("Password", type="password")
        ok = st.form_submit_button("Login")

    if ok:
        if u.strip().lower() == str(ADMIN_USER).strip().lower() and p == str(ADMIN_PASS):
            st.session_state["auth_ok"] = True
            st.session_state["auth_user"] = u
            st.rerun()
        else:
            st.error("❌ Incorrect username or password.")
    st.stop()

require_login()

# ----------------------------
# SIDEBAR: UPLOADS + FILTERS
# ----------------------------
with st.sidebar:
    st.markdown(f"## {APP_TITLE}")

    st.markdown("### Data Sources (Saved once)")
    up_unvisited = st.file_uploader("Upload Unvisited Outlets (xlsx)", type=["xlsx"])
    up_merch = st.file_uploader("Upload Field Merchandisers (xlsx)", type=["xlsx"])

    st.markdown("### Extra Modules")
    up_offroute = st.file_uploader("Upload Off-Route Requests (xlsx)", type=["xlsx"])
    up_leave = st.file_uploader("Upload Leave Management (csv)", type=["csv"])
    up_status = st.file_uploader("Upload Status Update (csv preferred)", type=["csv", "xlsx"])

    if up_unvisited is not None:
        save_uploaded_file(up_unvisited, SAVED_UNVISITED_NAME)
        st.success("✅ Unvisited Outlets saved")

    if up_merch is not None:
        save_uploaded_file(up_merch, SAVED_MERCH_NAME)
        st.success("✅ Field Merchandisers saved")

    if up_offroute is not None:
        save_uploaded_file(up_offroute, SAVED_OFFROUTE_NAME)
        st.success("✅ Off-Route Requests saved")

    if up_leave is not None:
        save_uploaded_file(up_leave, SAVED_LEAVE_NAME)
        st.success("✅ Leave Management saved")

    if up_status is not None:
        if up_status.name.lower().endswith(".csv"):
            save_uploaded_file(up_status, SAVED_STATUS_CSV_NAME)
            st.success("✅ Status Update CSV saved")
        else:
            save_uploaded_file(up_status, SAVED_STATUS_XLSX_NAME)
            st.success("✅ Status Update XLSX saved (CSV is more reliable)")

    st.divider()

    clear = st.button("🧹 Clear saved uploads")
    if clear:
        for fname in [
            SAVED_UNVISITED_NAME,
            SAVED_MERCH_NAME,
            SAVED_OFFROUTE_NAME,
            SAVED_LEAVE_NAME,
            SAVED_STATUS_CSV_NAME,
            SAVED_STATUS_XLSX_NAME,
        ]:
            try:
                (DATA_DIR / fname).unlink(missing_ok=True)
            except Exception:
                pass
        st.success("Cleared saved uploads. Refresh the page.")
        st.stop()


# ----------------------------
# LOAD DATA (use saved if exists; else default file in app folder)
# ----------------------------
unvisited_path = (DATA_DIR / SAVED_UNVISITED_NAME) if (DATA_DIR / SAVED_UNVISITED_NAME).exists() else Path(UNVISITED_DEFAULT)
merch_path = (DATA_DIR / SAVED_MERCH_NAME) if (DATA_DIR / SAVED_MERCH_NAME).exists() else Path(MERCH_DEFAULT)

unvisited_raw = standardize_cols(cached_read_excel(str(unvisited_path), "Unvisited Outlets"))
merch_raw = standardize_cols(cached_read_excel(str(merch_path), "Field Merchandisers"))

merch_map = build_merch_mapping(merch_raw)

# Unvisited essentials (flexible)
# Try common column names; if missing, allow user to map columns from a dropdown.
def pick_col(df: pd.DataFrame, label: str, candidates: list[str], required: bool = True) -> Optional[str]:
    cols = df.columns.tolist()
    for c in candidates:
        if c in cols:
            return c
    if not required:
        return None

    st.warning(f"Missing expected column for **{label}**.")
    st.write("Please map it using the selector below:")
    choice = st.selectbox(
        f"Select column for {label}",
        options=["-- Select --"] + cols,
        index=0,
        key=f"map_{label}",
    )
    if choice == "-- Select --":
        return None
    return choice

st.markdown("### Data validation")
with st.expander("See uploaded Unvisited file columns", expanded=False):
    st.code(", ".join(unvisited_raw.columns))

rep_col = pick_col(unvisited_raw, "Rep / Serviced By", ["SERVICED BY", "DSR", "REP", "REP NAME", "SALES REP", "MERCHANDISER"], required=True)
cust_col = pick_col(unvisited_raw, "Customer / Outlet", ["CUSTOMER NAME", "OUTLET NAME", "CUSTOMER", "OUTLET", "ACCOUNT NAME", "STORE NAME"], required=True)
region_col = pick_col(unvisited_raw, "Region", ["REGION", "REGION NAME", "TERRITORY", "AREA", "ZONE"], required=False)
date_col = pick_col(unvisited_raw, "Date", ["DATE", "VISIT DATE", "CREATED DATE", "DAY", "REPORT DATE"], required=False)

if rep_col is None or cust_col is None:
    friendly_stop(
        "Missing columns in Unvisited Outlets file",
        "Please select the missing column mappings above (Rep and Customer/Outlet are required).",
        "After selecting, the dashboard will continue automatically.",
    )

unvisited = unvisited_raw.copy()
unvisited = unvisited.rename(columns={rep_col: "REP"})
if region_col:
    unvisited = unvisited.rename(columns={region_col: "REGION"})
else:
    unvisited["REGION"] = pd.NA

unvisited["REGION"] = unvisited["REGION"].apply(standardize_region)

# Parse date if exists
if date_col:
    unvisited = unvisited.rename(columns={date_col: "DATE"})
    unvisited["DATE"] = pd.to_datetime(unvisited["DATE"], errors="coerce")

# Add supervisor + normalized rep
unvisited = enrich_with_merch(unvisited, "REP", merch_map)
unvisited["REP"] = unvisited["REP"].astype("string")
unvisited["REP"] = remove_test_reps(unvisited["REP"])
unvisited = unvisited[unvisited["REP"].notna()].copy()
unvisited["CUSTOMER"] = unvisited[cust_col].astype("string")

# Key account flag
unvisited["KEY_ACCOUNT_NAME"] = unvisited["CUSTOMER"].apply(detect_key_account)

unvisited["IS_KEY_ACCOUNT"] = unvisited["KEY_ACCOUNT_NAME"].astype("string").str.strip() != ""

# ----------------------------
# LOAD EXTRA MODULES (optional)
# ----------------------------
offroute_df = pd.DataFrame()
leave_df = pd.DataFrame()
status_df = pd.DataFrame()

offroute_path = DATA_DIR / SAVED_OFFROUTE_NAME
leave_path = DATA_DIR / SAVED_LEAVE_NAME
status_csv_path = DATA_DIR / SAVED_STATUS_CSV_NAME
status_xlsx_path = DATA_DIR / SAVED_STATUS_XLSX_NAME

if offroute_path.exists():
    offroute_df = standardize_cols(cached_read_excel(str(offroute_path), "Off-Route Requests"))
    offroute_df = parse_date(offroute_df, "REQUEST START")
    offroute_df = parse_date(offroute_df, "REQUEST END")
    offroute_df = parse_date(offroute_df, "APPROVED START")
    offroute_df = parse_date(offroute_df, "APPROVED END")
    offroute_df = parse_date(offroute_df, "ENTRY TIME")
    offroute_df = enrich_with_merch(offroute_df, "REP NAME", merch_map)

if leave_path.exists():
    leave_df = standardize_cols(cached_read_csv(str(leave_path), "Leave Management"))
    leave_df = parse_date(leave_df, "REQUEST START")
    leave_df = parse_date(leave_df, "REQUEST END")
    leave_df = parse_date(leave_df, "ENTRY TIME")
    leave_df = enrich_with_merch(leave_df, "USER", merch_map)

if status_csv_path.exists():
    status_df = standardize_cols(cached_read_csv(str(status_csv_path), "Status Updates"))
elif status_xlsx_path.exists():
    try:
        # First try normal read
        status_df = standardize_cols(cached_read_excel(str(status_xlsx_path), "Status Updates (XLSX)"))
    except Exception:
        # Fallback: try reading all sheets and concatenating
        try:
            sheets = pd.read_excel(status_xlsx_path, sheet_name=None, engine='openpyxl')
            if isinstance(sheets, dict) and sheets:
                status_df = pd.concat(sheets.values(), ignore_index=True)
                status_df = standardize_cols(status_df)
            else:
                status_df = pd.DataFrame()
        except Exception:
            status_df = pd.DataFrame()

if not status_df.empty:
    status_df = parse_date(status_df, "STATUS DATE")
    status_df = parse_date(status_df, "APPROVAL DATE")
    # make REGION column consistent if provided as REGION NAME
    if "REGION NAME" in status_df.columns and "REGION" not in status_df.columns:
        status_df["REGION"] = normalize_region(status_df["REGION NAME"])
    status_df = enrich_with_merch(status_df, "REP NAME", merch_map)


# ----------------------------
# GLOBAL FILTERS (apply everywhere)
# ----------------------------
with st.sidebar:
    if st.button('🔄 Force reload (clear cache)'):
        st.cache_data.clear()
        st.rerun()

    st.markdown("### Global Filters")

    st.markdown("### Benchmarks")
    max_unvisited_rep = st.number_input("Max unvisited per rep (alert threshold)", min_value=1, value=DEFAULT_MAX_UNVISITED_PER_REP, step=1)
    max_unvisited_sup = st.number_input("Max unvisited per supervisor (alert threshold)", min_value=1, value=DEFAULT_MAX_UNVISITED_PER_SUPERVISOR, step=1)
    max_key_unvisited = st.number_input("Max key-account unvisited (alert threshold)", min_value=1, value=DEFAULT_MAX_KEY_ACCOUNT_UNVISITED, step=1)


    # Date range (uses unvisited DATE; if missing, defaults to none)
    min_date = None
    max_date = None
    if "DATE" in unvisited.columns and unvisited["DATE"].notna().any():
        min_date = unvisited["DATE"].min().date()
        max_date = unvisited["DATE"].max().date()

    date_range: Optional[Tuple] = None
    if min_date and max_date:
        date_range = st.date_input("Date range (Unvisited)", value=(min_date, max_date))
    else:
        st.caption("Date filter unavailable (no DATE column in unvisited file).")

    regions = sorted([r for r in unvisited["REGION"].dropna().unique().tolist() if str(r).strip() != ""])
    region_sel = st.multiselect("Region", options=regions, default=regions)

    sups = sorted([s for s in unvisited.get("SUPERVISOR_CLEAN", pd.Series(dtype="string")).dropna().unique().tolist() if str(s).strip() != ""])
    supervisor_sel = st.multiselect("Supervisor", options=sups, default=sups)

    reps = sorted([r for r in unvisited["REP"].dropna().unique().tolist() if str(r).strip() != ""])
    rep_sel = st.multiselect("Rep", options=reps, default=reps)

    show_key_only = st.checkbox("Key accounts only", value=False)


def apply_unvisited_filters(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()

    if region_sel and "REGION" in d.columns:
        d = d[d["REGION"].isin(region_sel)]

    if supervisor_sel and "SUPERVISOR_CLEAN" in d.columns:
        d = d[d["SUPERVISOR_CLEAN"].isin(supervisor_sel)]

    if rep_sel and "REP" in d.columns:
        d = d[d["REP"].isin(rep_sel)]

    if show_key_only and "IS_KEY_ACCOUNT" in d.columns:
        d = d[d["IS_KEY_ACCOUNT"] == True]  # noqa: E712

    if date_range and "DATE" in d.columns:
        try:
            start = pd.to_datetime(date_range[0])
            end = pd.to_datetime(date_range[1]) + pd.Timedelta(days=1)
            d = d[(d["DATE"] >= start) & (d["DATE"] < end)]
        except Exception:
            pass

    return d


def apply_common_filters(df: pd.DataFrame, date_col: Optional[str], rep_col: Optional[str]) -> pd.DataFrame:
    """Applies region/supervisor/rep and (optional) date range if df has those cols."""
    d = df.copy()

    if region_sel and "REGION" in d.columns:
        d = d[d["REGION"].isin(region_sel)]

    if supervisor_sel and "SUPERVISOR_CLEAN" in d.columns:
        d = d[d["SUPERVISOR_CLEAN"].isin(supervisor_sel)]

    if rep_col and rep_col in d.columns and rep_sel:
        d = d[d[rep_col].astype("string").isin(pd.Series(rep_sel, dtype="string"))]

    # date_range applies only to unvisited by default; but if date_col exists, also filter
    if date_range and date_col and date_col in d.columns:
        try:
            start = pd.to_datetime(date_range[0])
            end = pd.to_datetime(date_range[1]) + pd.Timedelta(days=1)
            d = d[(d[date_col] >= start) & (d[date_col] < end)]
        except Exception:
            pass

    return d


filtered_unvisited = apply_unvisited_filters(unvisited)

# Root-cause enrichment (only meaningful when DATE exists)
filtered_unvisited = enrich_root_cause(filtered_unvisited, leave_df, offroute_df, status_df)

# Alerts
alert_reps = (
    filtered_unvisited.groupby(["REP", "SUPERVISOR_CLEAN", "REGION"], dropna=False)
    .size()
    .reset_index(name="UNVISITED")
    .query("UNVISITED >= @max_unvisited_rep")
    .sort_values("UNVISITED", ascending=False)
)

alert_sup = (
    filtered_unvisited.groupby(["SUPERVISOR_CLEAN"], dropna=False)
    .size()
    .reset_index(name="UNVISITED")
    .query("UNVISITED >= @max_unvisited_sup")
    .sort_values("UNVISITED", ascending=False)
)

# ----------------------------
# DATA HEALTH (quick diagnostics)
# ----------------------------
with st.expander('✅ Data health & quick checks', expanded=False):
    st.write('If a section looks empty, check these counts + column names.')
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric('Unvisited rows (all)', f"{len(unvisited):,}")
        st.metric('Unvisited rows (filtered)', f"{len(filtered_unvisited):,}")
    with c2:
        st.metric('Unique reps', f"{unvisited['REP'].nunique():,}" if 'REP' in unvisited.columns else '—')
        st.metric('Unique customers', f"{unvisited['CUSTOMER'].nunique():,}" if 'CUSTOMER' in unvisited.columns else '—')
    with c3:
        st.metric('Regions (non-empty)', f"{unvisited['REGION'].dropna().nunique():,}" if 'REGION' in unvisited.columns else '—')
        st.metric('Supervisors (non-empty)', f"{unvisited['SUPERVISOR_CLEAN'].dropna().nunique():,}" if 'SUPERVISOR_CLEAN' in unvisited.columns else '—')
    with c4:
        st.metric('Off-route rows', f"{len(offroute_df):,}" if not offroute_df.empty else '0')
        st.metric('Leave rows', f"{len(leave_df):,}" if not leave_df.empty else '0')
        st.metric('Status rows', f"{len(status_df):,}" if not status_df.empty else '0')

    st.markdown('**Unvisited columns detected**')
    st.code(', '.join(unvisited_raw.columns[:200]))
    st.markdown('**Merch columns detected**')
    st.code(', '.join(merch_raw.columns[:200]))

    if 'SUPERVISOR_CLEAN' in unvisited.columns and unvisited['SUPERVISOR_CLEAN'].dropna().nunique() == 0:
        st.warning('Supervisor mapping looks empty. Your Merch file may be missing a Supervisor column, or names are not matching.')
        st.info('Fix: ensure Merch file has a supervisor column (e.g., SUPERVISOR / TEAM LEADER) and names match the rep names.')

    if status_df.empty and status_xlsx_path.exists() and not status_csv_path.exists():
        st.warning('Status update XLSX could not be read. Export it as CSV and upload the CSV for best results.')

    st.markdown('**Quick preview (Unvisited)**')
    st.dataframe(unvisited.head(20), use_container_width=True)


# ----------------------------
# HEADER
# ----------------------------
st.title(APP_TITLE)

render_filter_banner(date_range, region_sel, supervisor_sel, rep_sel, show_key_only)

# ----------------------------
# TABS
# ----------------------------
tab_overview, tab_supervisor, tab_supervisor_routes, tab_key, tab_region, tab_detail, tab_offroute, tab_leave, tab_status, tab_download = st.tabs(
    [
        "📌 Overview",
        "👥 Supervisors",
        "🧭 Supervisor Routes",
        "⭐ Key Accounts",
        "🗺️ Region & Reps",
        "📋 Detail",
        "🚗 Off-Route",
        "🌴 Leave",
        "✅ Status Updates",
        "⬇️ Download",
    ]
)


with tab_supervisor_routes:
    st.markdown("## 🧭 Supervisor Route Coverage")
    st.caption("Supervisors both manage teams and may also cover routes themselves.")

    sup_selected = st.selectbox(
        "Select Supervisor",
        options=["All"] + STANDARD_SUPERVISORS,
    )

    df = filtered_unvisited.copy()

    if sup_selected == "All":
        st.info("Select a supervisor to view their own routes vs team responsibility.")
    else:
        self_df = df[df["REP"].astype("string") == sup_selected]
        team_df = df[df["SUPERVISOR_CLEAN"].astype("string") == sup_selected]
        combined = pd.concat([self_df, team_df], ignore_index=True)

        st.markdown("### KPI")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Supervisor Own Routes (Unvisited)", f"{len(self_df):,}")
        with c2:
            st.metric("Team Routes (Unvisited)", f"{len(team_df):,}")
        with c3:
            st.metric("Total Responsibility", f"{len(combined):,}")
        with c4:
            if "IS_KEY_ACCOUNT" in combined.columns:
                st.metric("Key Account Unvisited", f"{int(combined['IS_KEY_ACCOUNT'].fillna(False).sum()):,}")
            else:
                st.metric("Key Account Unvisited", "—")

        st.markdown("### Root-cause breakdown")
        if "ROOT_CAUSE" in combined.columns:
            rc = combined["ROOT_CAUSE"].astype("string").fillna("UNKNOWN").value_counts().reset_index()
            rc.columns = ["ROOT_CAUSE", "COUNT"]
            st.dataframe(rc, use_container_width=True)
            plot_bar(rc, "ROOT_CAUSE", "COUNT", "Root cause breakdown")
        else:
            st.caption("Root-cause not available (ensure DATE exists and modules are uploaded).")

        st.markdown("### Drill-down")
        view_mode = st.radio("View", options=["Combined", "Supervisor Only", "Team Only"], horizontal=True)
        show_df = combined
        if view_mode == "Supervisor Only":
            show_df = self_df
        elif view_mode == "Team Only":
            show_df = team_df

        cols = [c for c in ["DATE","REGION","REP","SUPERVISOR_CLEAN","CUSTOMER","KEY_ACCOUNT_NAME","ROOT_CAUSE","CAUSE_DETAIL"] if c in show_df.columns]
        st.dataframe(show_df[cols].head(2000) if cols else show_df.head(2000), use_container_width=True)



# ----------------------------
# OVERVIEW (minimal charts; executive snapshot)
# ----------------------------
with tab_overview:
    st.markdown("### Quick overview")
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        kpi_card("Unvisited outlets", f"{len(filtered_unvisited):,}")
    with c2:
        kpi_card("Unique reps", f"{filtered_unvisited['REP'].nunique():,}")
    with c3:
        kpi_card("Regions covered", f"{filtered_unvisited['REGION'].nunique():,}")
    with c4:
        kpi_card("Key account unvisited", f"{filtered_unvisited['IS_KEY_ACCOUNT'].sum():,}")

    st.markdown("### Top 10 reps (most unvisited)")
    top_reps = (
        filtered_unvisited.groupby(["REP", "SUPERVISOR_CLEAN", "REGION"], dropna=False)
        .size()
        .reset_index(name="UNVISITED")
        .sort_values("UNVISITED", ascending=False)
        .head(10)
    )
    st.dataframe(top_reps, use_container_width=True)

    st.markdown("### Extra modules snapshot")
    e1, e2, e3 = st.columns(3)
    with e1:
        kpi_card("Off-route requests", f"{len(offroute_df):,}" if not offroute_df.empty else "—")
    with e2:
        kpi_card("Leave requests", f"{len(leave_df):,}" if not leave_df.empty else "—")
    with e3:
        kpi_card("Status updates", f"{len(status_df):,}" if not status_df.empty else "—")

    
    st.markdown("### Root-cause breakdown (why unvisited)")
    if "ROOT_CAUSE" in filtered_unvisited.columns:
        cause_counts = (
            filtered_unvisited["ROOT_CAUSE"]
            .astype("string")
            .fillna("UNKNOWN")
            .value_counts()
            .reset_index()
        )
        cause_counts.columns = ["ROOT_CAUSE", "COUNT"]
        cA, cB = st.columns([1, 1])
        with cA:
            st.dataframe(cause_counts, use_container_width=True)
        with cB:
            plot_bar(cause_counts, "ROOT_CAUSE", "COUNT", "Unvisited by root cause")

    st.markdown("### Risk alerts (threshold-based)")
    a1, a2 = st.columns(2)
    with a1:
        st.markdown("**Reps above threshold**")
        if alert_reps.empty:
            st.success("No reps above threshold under current filters.")
        else:
            st.dataframe(alert_reps.head(50), use_container_width=True)
    with a2:
        st.markdown("**Supervisors above threshold**")
        if alert_sup.empty:
            st.success("No supervisors above threshold under current filters.")
        else:
            st.dataframe(alert_sup.head(50), use_container_width=True)

    st.markdown("### Data quality")
    dq = data_quality_summary(filtered_unvisited)
    st.dataframe(pd.DataFrame(list(dq.items()), columns=["CHECK", "COUNT"]), use_container_width=True)

    st.caption("Use the tabs for details. Filters on the left apply everywhere.")


# ----------------------------
# SUPERVISORS
# ----------------------------
with tab_supervisor:
    st.markdown("### Unvisited by Supervisor")
    if "SUPERVISOR_CLEAN" not in filtered_unvisited.columns:
        st.info("Supervisor mapping not available in the uploaded Merch file.")
    else:
        sup_summary = (
            filtered_unvisited.groupby(["SUPERVISOR_CLEAN"], dropna=False)
            .size()
            .reset_index(name="UNVISITED")
            .sort_values("UNVISITED", ascending=False)
        )
        st.dataframe(sup_summary, use_container_width=True)


        st.markdown("### Drill-down (Supervisor → Rep → Outlets)")
        sel_sup = st.selectbox("Select a supervisor", options=["(All)"] + sup_summary["SUPERVISOR_CLEAN"].astype(str).tolist())
        dd = filtered_unvisited.copy()
        if sel_sup != "(All)":
            dd = dd[dd["SUPERVISOR_CLEAN"].astype("string") == sel_sup]

        rep_counts = (
            dd.groupby(["REP", "SUPERVISOR_CLEAN", "REGION"], dropna=False)
            .size()
            .reset_index(name="UNVISITED")
            .sort_values("UNVISITED", ascending=False)
        )
        sel_rep = st.selectbox("Select a rep", options=["(All)"] + rep_counts["REP"].astype(str).tolist())
        if sel_rep != "(All)":
            dd = dd[dd["REP"].astype("string") == sel_rep]

        cols = [c for c in ["DATE", "REGION", "REP", "SUPERVISOR_CLEAN", "CUSTOMER", "ROOT_CAUSE", "CAUSE_DETAIL"] if c in dd.columns]
        st.dataframe(dd[cols].head(1000), use_container_width=True)

        st.markdown("### Reps under selected filters (includes Supervisor + Region)")
        reps_table = (
            filtered_unvisited.groupby(["REP", "SUPERVISOR_CLEAN", "REGION"], dropna=False)
            .size()
            .reset_index(name="UNVISITED")
            .sort_values(["SUPERVISOR_CLEAN", "UNVISITED"], ascending=[True, False])
        )
        st.dataframe(reps_table, use_container_width=True)


# ----------------------------
# KEY ACCOUNTS
# ----------------------------
with tab_key:
    st.markdown("### Key accounts focus (exact counts)")
    key_df = filtered_unvisited[filtered_unvisited.get("IS_KEY_ACCOUNT", False) == True].copy()

    # Ensure REGION values match STANDARD_REGIONS (so pivot doesn't become all zeros)
    if "REGION" in key_df.columns:
        key_df["REGION"] = key_df["REGION"].apply(standardize_region)
        key_df["REGION"] = key_df["REGION"].fillna("UNKNOWN / UNMAPPED")
  # noqa: E712

    if key_df.empty:
        st.info("No key-account unvisited outlets under current filters.")
    else:
        st.markdown("#### Key account unvisited (overall)")
        if "KEY_ACCOUNT_NAME" in key_df.columns:
            ka_overall = (
                key_df[key_df["KEY_ACCOUNT_NAME"].astype("string").str.strip() != ""]
                .groupby("KEY_ACCOUNT_NAME", dropna=False)
                .size()
                .reindex(STANDARD_KEY_ACCOUNTS, fill_value=0)
                .reset_index(name="UNVISITED")
            )
            st.dataframe(ka_overall, use_container_width=True)
        else:
            st.caption("KEY_ACCOUNT_NAME column missing — check detect_key_account logic.")

        st.markdown("#### Key account unvisited by region (respects filters)")
        if "KEY_ACCOUNT_NAME" in key_df.columns and "REGION" in key_df.columns:
            ka_region = (
                key_df[key_df["KEY_ACCOUNT_NAME"].astype("string").str.strip() != ""]
                .groupby(["REGION", "KEY_ACCOUNT_NAME"], dropna=False)
                .size()
                .reset_index(name="UNVISITED")
            )

            # Complete grid so zeros appear
            grid = [(r, k) for r in STANDARD_REGIONS for k in STANDARD_KEY_ACCOUNTS]
            base = pd.DataFrame(grid, columns=["REGION", "KEY_ACCOUNT_NAME"])
            ka_region = base.merge(ka_region, on=["REGION", "KEY_ACCOUNT_NAME"], how="left").fillna({"UNVISITED": 0})
            ka_region["UNVISITED"] = pd.to_numeric(ka_region["UNVISITED"], errors="coerce").fillna(0).astype(int)

            pivot = ka_region.pivot_table(index="REGION", columns="KEY_ACCOUNT_NAME", values="UNVISITED", aggfunc="sum", fill_value=0)
            pivot = pivot.reindex(STANDARD_REGIONS).reindex(columns=STANDARD_KEY_ACCOUNTS)
            st.dataframe(pivot, use_container_width=True)

            # Show any key-account unvisited that landed in UNKNOWN / UNMAPPED
            unknown_rows = key_df[key_df.get('REGION','').astype('string') == 'UNKNOWN / UNMAPPED']
            if not unknown_rows.empty:
                st.markdown('**Unknown / Unmapped region (check rep mapping / names):**')
                unk = (unknown_rows.groupby('KEY_ACCOUNT_NAME', dropna=False).size().reindex(STANDARD_KEY_ACCOUNTS, fill_value=0).reset_index(name='UNVISITED'))
                st.dataframe(unk, use_container_width=True)


        st.markdown("#### Key account outlets (detail)")
        cols = [c for c in ["DATE", "REGION", "REP", "SUPERVISOR_CLEAN", "CUSTOMER", "KEY_ACCOUNT_NAME", "ROOT_CAUSE"] if c in key_df.columns]
        st.dataframe(key_df[cols + [c for c in key_df.columns if c not in cols]].head(2000), use_container_width=True)


# ----------------------------
# REGION & REPS
# ----------------------------


# ----------------------------
# REGION & REPS
# ----------------------------
with tab_region:
    st.markdown("### Region summary")
    region_summary = (
        filtered_unvisited.groupby(["REGION"], dropna=False)
        .size()
        .reset_index(name="UNVISITED")
        .sort_values("UNVISITED", ascending=False)
    )
    st.dataframe(region_summary, use_container_width=True)

    st.markdown("### Rep ranking (includes Supervisor + Region)")
    rep_rank = (
        filtered_unvisited.groupby(["REGION", "REP", "SUPERVISOR_CLEAN"], dropna=False)
        .size()
        .reset_index(name="UNVISITED")
        .sort_values(["REGION", "UNVISITED"], ascending=[True, False])
    )
    st.dataframe(rep_rank, use_container_width=True)


# ----------------------------
# DETAIL
# ----------------------------
with tab_detail:
    st.markdown("### Detailed unvisited outlets")
    cols_first = [c for c in ["DATE","REGION","REP","SUPERVISOR_CLEAN","CUSTOMER","ROOT_CAUSE","CAUSE_DETAIL"] if c in filtered_unvisited.columns]
    st.dataframe(
        filtered_unvisited[cols_first + [c for c in filtered_unvisited.columns if c not in cols_first]].head(2000),
        use_container_width=True,
    )


# ----------------------------
# OFF-ROUTE REQUESTS
# ----------------------------
with tab_offroute:
    st.markdown("## 🚗 Off-Route Requests")
    if offroute_df.empty:
        st.info("Upload **Off-Route Requests (xlsx)** in the sidebar to view this tab.")
    else:
        d = apply_common_filters(offroute_df, date_col="REQUEST START", rep_col="REP NAME")

        c1, c2, c3 = st.columns(3)
        with c1:
            kpi_card("Requests", f"{len(d):,}")
        with c2:
            kpi_card("Unique reps", f"{d['REP NAME'].nunique():,}" if "REP NAME" in d.columns else "—")
        with c3:
            kpi_card("Statuses", f"{d['STATUS'].nunique():,}" if "STATUS" in d.columns else "—")

        if "STATUS" in d.columns:
            st.markdown("### Status breakdown")
            st.dataframe(d["STATUS"].astype("string").value_counts().reset_index(name="COUNT"), use_container_width=True)

        st.markdown("### Detail")
        st.dataframe(d, use_container_width=True)


# ----------------------------
# LEAVE MANAGEMENT
# ----------------------------
with tab_leave:
    st.markdown("## 🌴 Leave Management")
    if leave_df.empty:
        st.info("Upload **Leave Management (csv)** in the sidebar to view this tab.")
    else:
        d = apply_common_filters(leave_df, date_col="REQUEST START", rep_col="USER")

        c1, c2, c3 = st.columns(3)
        with c1:
            kpi_card("Requests", f"{len(d):,}")
        with c2:
            kpi_card("Unique users", f"{d['USER'].nunique():,}" if "USER" in d.columns else "—")
        with c3:
            kpi_card("Statuses", f"{d['STATUS'].nunique():,}" if "STATUS" in d.columns else "—")

        if "CATEGORY" in d.columns:
            st.markdown("### Leave categories")
            st.dataframe(d["CATEGORY"].astype("string").value_counts().reset_index(name="COUNT"), use_container_width=True)

        st.markdown("### Detail")
        st.dataframe(d, use_container_width=True)


# ----------------------------
# STATUS UPDATES
# ----------------------------
with tab_status:
    st.markdown("## ✅ Status Updates")
    if status_df.empty:
        st.info("Upload **Status Update (CSV preferred)** in the sidebar to view this tab.")
        st.caption("If your XLSX fails to load, export it as CSV and re-upload.")
    else:
        d = apply_common_filters(status_df, date_col="STATUS DATE", rep_col="REP NAME")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            kpi_card("Updates", f"{len(d):,}")
        with c2:
            kpi_card("Unique reps", f"{d['REP NAME'].nunique():,}" if "REP NAME" in d.columns else "—")
        with c3:
            kpi_card("Categories", f"{d['CATEGORY'].nunique():,}" if "CATEGORY" in d.columns else "—")
        with c4:
            kpi_card("Approved", f"{d['APPROVED BY'].notna().sum():,}" if "APPROVED BY" in d.columns else "—")

        if "CATEGORY" in d.columns:
            st.markdown("### Category breakdown")
            st.dataframe(d["CATEGORY"].astype("string").value_counts().reset_index(name="COUNT"), use_container_width=True)

        if "APPROVED BY" in d.columns:
            st.markdown("### Approvals by manager")
            mgr = d["APPROVED BY"].astype("string").fillna("NOT APPROVED")
            st.dataframe(mgr.value_counts().reset_index(name="COUNT"), use_container_width=True)

        st.markdown("### Detail")
        st.dataframe(d, use_container_width=True)


# ----------------------------
# DOWNLOAD
# ----------------------------
with tab_download:
    st.markdown("### Download (Filtered)")
    st.caption("Exports respect your global filters where columns exist.")

    # Prepare filtered versions for export
    exp_unvisited = filtered_unvisited.copy()
    exp_offroute = apply_common_filters(offroute_df, "REQUEST START", "REP NAME") if not offroute_df.empty else pd.DataFrame()
    exp_leave = apply_common_filters(leave_df, "REQUEST START", "USER") if not leave_df.empty else pd.DataFrame()
    exp_status = apply_common_filters(status_df, "STATUS DATE", "REP NAME") if not status_df.empty else pd.DataFrame()

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        exp_unvisited.to_excel(writer, index=False, sheet_name="Unvisited (Filtered)")
        if not exp_offroute.empty:
            exp_offroute.to_excel(writer, index=False, sheet_name="Off-Route (Filtered)")
        if not exp_leave.empty:
            exp_leave.to_excel(writer, index=False, sheet_name="Leave (Filtered)")
        if not exp_status.empty:
            exp_status.to_excel(writer, index=False, sheet_name="Status (Filtered)")

        # include full raw too (for audit)
        unvisited.to_excel(writer, index=False, sheet_name="Unvisited (All)")
        if not offroute_df.empty:
            offroute_df.to_excel(writer, index=False, sheet_name="Off-Route (All)")
        if not leave_df.empty:
            leave_df.to_excel(writer, index=False, sheet_name="Leave (All)")
        if not status_df.empty:
            status_df.to_excel(writer, index=False, sheet_name="Status (All)")

    st.download_button(
        "⬇️ Download Excel",
        data=buffer.getvalue(),
        file_name="executive_dashboard_export.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.markdown("### Notes")
    st.write(
        "- If **Status Update XLSX** fails to load, export it as **CSV** and upload the CSV.\n"
        "- If your merch file uses different column names, ensure it contains staff name + region (and supervisor if possible)."
    )
    