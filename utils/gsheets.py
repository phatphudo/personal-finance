import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

TAB_CASH_COUNTS = "Cash Counts"
TAB_SETTINGS = "Settings"
TAB_WORK_HOURS = "Work Hours"
TAB_PAY_PERIODS = "Pay Periods"
TAB_STARTING_BALANCES = "Monthly Starting Balances"
TAB_CASH_IN = "Cash In"
TAB_CASH_OUT = "Cash Out"
TAB_DEBIT_IN = "Debit In"
TAB_DEBIT_OUT = "Debit Out"
TAB_CREDIT_TX = "Credit Transactions"
TAB_AVAILABILITY = "Availability"

@st.cache_resource(ttl=60)
def get_client() -> gspread.Client:
    """Authenticate and return a gspread client using credentials from Streamlit secrets."""
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES,
    )
    return gspread.authorize(creds)


def get_spreadsheet() -> gspread.Spreadsheet:
    client = get_client()
    return client.open_by_key(st.secrets["sheets"]["spreadsheet_id"])


# ── Read helpers ──────────────────────────────────────────────────────────────


def get_or_create_worksheet(tab_name: str) -> gspread.Worksheet:
    """Get a worksheet by name, creating it if it doesn't exist."""
    spreadsheet = get_spreadsheet()
    try:
        ws = spreadsheet.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=tab_name, rows=100, cols=20)
        # Add default headers for known tabs
        if tab_name == TAB_WORK_HOURS:
            ws.append_row(["Date", "Clock In", "Clock Out", "Status", "Work Hours", "Break", "Pay Period"])
        elif tab_name == TAB_PAY_PERIODS:
            ws.append_row(["Pay Period", "Current Rate", "Expected Rate"])
        elif tab_name == TAB_AVAILABILITY:
            ws.append_row(["Day", "Clock In", "Clock Out", "Break"])
        elif tab_name == TAB_STARTING_BALANCES:
            ws.append_row(["Month", "Account", "Starting Balance"])
        elif tab_name in (
            TAB_CASH_IN,
            TAB_DEBIT_IN,
            TAB_CASH_OUT,
            TAB_DEBIT_OUT,
            TAB_CREDIT_TX,
        ):
            ws.append_row(["Date", "Month", "Description", "Category", "Amount"])
    return ws


# All tabs we care about — fetched in a single batchGet call
_ALL_TABS = [
    TAB_CASH_COUNTS,
    TAB_SETTINGS,
    TAB_WORK_HOURS,
    TAB_PAY_PERIODS,
    TAB_STARTING_BALANCES,
    TAB_CASH_IN,
    TAB_CASH_OUT,
    TAB_DEBIT_IN,
    TAB_DEBIT_OUT,
    TAB_CREDIT_TX,
    TAB_AVAILABILITY,
]


@st.cache_data(ttl=60)
def _batch_read_all() -> dict[str, pd.DataFrame]:
    """
    Fetch every known tab in ONE batchGet API call.
    Returns a dict of tab_name → DataFrame (empty DF if tab doesn't exist).
    """
    spreadsheet = get_spreadsheet()

    # Collect all tabs that actually exist
    existing = {ws.title for ws in spreadsheet.worksheets()}
    tabs_to_fetch = [t for t in _ALL_TABS if t in existing]

    if not tabs_to_fetch:
        return {}

    # Single batched read — spreadsheet.client IS the HTTPClient in gspread v6+
    ranges = [f"'{t}'" for t in tabs_to_fetch]
    result = spreadsheet.client.values_batch_get(spreadsheet.id, ranges)
    out: dict[str, pd.DataFrame] = {}
    for vr in result.get("valueRanges", []):
        # Range looks like "'Cash In'!A1:Z999" — extract tab name
        raw_range = vr.get("range", "")
        tab_name = raw_range.split("!")[0].strip("'")
        rows = vr.get("values", [])
        if not rows:
            out[tab_name] = pd.DataFrame()
            continue
        headers = rows[0]
        data_rows = rows[1:]
        # Pad short rows to header width (missing trailing cells come back empty)
        padded = [r + [""] * (len(headers) - len(r)) for r in data_rows]
        df = pd.DataFrame(padded, columns=headers)
        # Row numbers relative to the sheet (header = row 1, data starts at 2)
        df["_SheetRow"] = range(2, 2 + len(df))
        out[tab_name] = df

    return out


def read_sheet(tab_name: str) -> pd.DataFrame:
    """Return the cached DataFrame for a single tab (no extra API call)."""
    data = _batch_read_all()
    df = data.get(tab_name, pd.DataFrame())
    return df


def invalidate_cache():
    """Clear the batch cache so the next read fetches fresh data."""
    _batch_read_all.clear()


# ── Re-export all domain helpers from the gsheets/ sub-package ────────────────
# This preserves backward compat: `from utils.gsheets import read_cash_in` etc.

from gsheets import (  # noqa: E402
    append_cash_in,
    append_cash_out,
    append_credit_tx,
    append_debit_in,
    append_debit_out,
    append_work_hours,
    get_period_rates,
    read_availability,
    read_cash_counts,
    read_cash_in,
    read_cash_out,
    read_credit_tx,
    read_debit_in,
    read_debit_out,
    read_pay_periods,
    read_settings,
    read_starting_balances,
    read_work_hours,
    update_cash_in_row,
    update_cash_out_row,
    update_credit_tx_row,
    update_debit_in_row,
    update_debit_out_row,
    update_work_hours_row,
    upsert_cash_count,
    upsert_pay_period_rates,
    upsert_starting_balance,
    write_availability,
    write_settings,
)

__all__ = [
    # core
    "get_client",
    "get_spreadsheet",
    "read_sheet",
    # delegated to gsheets/
    "read_settings",
    "write_settings",
    "read_availability",
    "write_availability",
    "read_work_hours",
    "append_work_hours",
    "update_work_hours_row",
    "read_pay_periods",
    "upsert_pay_period_rates",
    "get_period_rates",
    "read_starting_balances",
    "upsert_starting_balance",
    "read_cash_counts",
    "upsert_cash_count",
    "read_cash_in",
    "read_cash_out",
    "append_cash_in",
    "append_cash_out",
    "update_cash_in_row",
    "update_cash_out_row",
    "read_debit_in",
    "read_debit_out",
    "append_debit_in",
    "append_debit_out",
    "update_debit_in_row",
    "update_debit_out_row",
    "read_credit_tx",
    "append_credit_tx",
    "update_credit_tx_row",
]

