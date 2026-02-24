import glob
import os

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

TAB_SETTINGS = "Settings"
TAB_WORK_HOURS = "Work Hours"
TAB_TRANSACTIONS = "Transactions"
TAB_STARTING_BALANCES = "Monthly Starting Balances"
TAB_CASH_IN = "Cash In"
TAB_CASH_OUT = "Cash Out"
TAB_DEBIT_IN = "Debit In"
TAB_DEBIT_OUT = "Debit Out"

# Resolve the service account JSON from the .secret/ folder next to this project
_SECRET_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".secret")


def _find_service_account_file() -> str:
    """Return the path to the first JSON key file found in .secret/."""
    matches = glob.glob(os.path.join(_SECRET_DIR, "*.json"))
    if not matches:
        raise FileNotFoundError(
            f"No service account JSON found in {_SECRET_DIR}. "
            "Download your key from Google Cloud Console and place it there."
        )
    return matches[0]


@st.cache_resource(ttl=60)
def get_client() -> gspread.Client:
    """Authenticate and return a gspread client using the local JSON key file."""
    key_path = _find_service_account_file()
    creds = Credentials.from_service_account_file(key_path, scopes=SCOPES)
    return gspread.authorize(creds)


def get_spreadsheet() -> gspread.Spreadsheet:
    client = get_client()
    return client.open_by_key(st.secrets["sheets"]["spreadsheet_id"])


# ── Read helpers ──────────────────────────────────────────────────────────────


def _get_or_create_worksheet(tab_name: str) -> gspread.Worksheet:
    """Get a worksheet by name, creating it if it doesn't exist."""
    spreadsheet = get_spreadsheet()
    try:
        ws = spreadsheet.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=tab_name, rows=100, cols=20)
        # Add default headers for known tabs
        if tab_name == TAB_WORK_HOURS:
            ws.append_row(["Date", "Clock In", "Clock Out", "Status"])
        elif tab_name == TAB_TRANSACTIONS:
            ws.append_row(
                ["Date", "Type", "Account", "Category", "Amount", "Description"]
            )
        elif tab_name == TAB_STARTING_BALANCES:
            ws.append_row(["Month", "Account", "Starting Balance"])
        elif tab_name in (TAB_CASH_IN, TAB_DEBIT_IN):
            ws.append_row(["Date", "Month", "Description", "Amount"])
        elif tab_name in (TAB_CASH_OUT, TAB_DEBIT_OUT):
            ws.append_row(["Date", "Month", "Description", "Category", "Amount"])
    return ws


@st.cache_data(ttl=30)
def read_sheet(tab_name: str) -> pd.DataFrame:
    """Read a full sheet tab into a DataFrame."""
    ws = _get_or_create_worksheet(tab_name)
    records = ws.get_all_records()
    df = pd.DataFrame(records)
    if not df.empty:
        # Record the true Google Sheet row number (2...N)
        df["_SheetRow"] = range(2, 2 + len(df))
    return df


def read_settings() -> dict:
    """Return a dict of lists from the Settings tab."""
    df = read_sheet(TAB_SETTINGS)
    settings = {}
    for col in df.columns:
        settings[col] = df[col].dropna().replace("", pd.NA).dropna().tolist()
    return settings


def read_work_hours() -> pd.DataFrame:
    df = read_sheet(TAB_WORK_HOURS)
    if df.empty:
        return df

    # Support legacy sheets that didn't have Status
    if "Status" not in df.columns:
        df["Status"] = "Actual"
    df["Status"] = df["Status"].replace("", "Actual").fillna("Actual")

    # Convert Date column strictly using the expected format
    df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y", errors="coerce")

    # Clean up empty time fields
    df["Clock In"] = df["Clock In"].astype(str).replace("", pd.NA)
    df["Clock Out"] = df["Clock Out"].astype(str).replace("", pd.NA)

    # Convert clock times by combining them with the validated Date
    # `pd.to_datetime` will seamlessly handle both "14:30" (24h) and "02:30 PM" (12h)
    df["Clock In"] = pd.to_datetime(
        df["Date"].dt.strftime("%Y-%m-%d") + " " + df["Clock In"],
        errors="coerce",
    )
    df["Clock Out"] = pd.to_datetime(
        df["Date"].dt.strftime("%Y-%m-%d") + " " + df["Clock Out"],
        errors="coerce",
    )

    # Compute duration in hours
    df["Hours"] = (df["Clock Out"] - df["Clock In"]).dt.total_seconds() / 3600

    return df.dropna(subset=["Date"])


def read_transactions() -> pd.DataFrame:
    df = read_sheet(TAB_TRANSACTIONS)
    if df.empty:
        return df
    df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y", errors="coerce")
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0)
    return df.dropna(subset=["Date"])


def read_starting_balances() -> pd.DataFrame:
    df = read_sheet(TAB_STARTING_BALANCES)
    if df.empty:
        return df
    df["Month"] = pd.to_datetime(df["Month"], errors="coerce")
    df["Starting Balance"] = pd.to_numeric(df["Starting Balance"], errors="coerce")
    return df


# ── Write helpers ─────────────────────────────────────────────────────────────


def append_work_hours(date: str, clock_in: str, clock_out: str, status: str = "Actual"):
    """Append a new row to the Work Hours tab."""
    ws = _get_or_create_worksheet(TAB_WORK_HOURS)
    ws.append_row(
        [date, clock_in, clock_out, status], value_input_option="USER_ENTERED"
    )
    # Invalidate cache so the UI reflects the new data immediately
    read_sheet.clear()


def update_work_hours_row(
    sheet_row: int, date: str, clock_in: str, clock_out: str, status: str
):
    """Update a specific literal row in the Work Hours tab."""
    ws = _get_or_create_worksheet(TAB_WORK_HOURS)
    ws.update(
        values=[[date, clock_in, clock_out, status]],
        range_name=f"A{sheet_row}:D{sheet_row}",
        value_input_option="USER_ENTERED",
    )
    read_sheet.clear()


def append_transaction(
    date: str,
    tx_type: str,
    account: str,
    category: str,
    amount: float,
    description: str,
):
    """Append a new row to the Transactions tab."""
    ws = _get_or_create_worksheet(TAB_TRANSACTIONS)
    ws.append_row(
        [date, tx_type, account, category, amount, description],
        value_input_option="USER_ENTERED",
    )
    read_sheet.clear()


def update_transaction_row(
    sheet_row: int,
    date: str,
    tx_type: str,
    account: str,
    category: str,
    amount: float,
    description: str,
):
    """Update a specific literal row in the Transactions tab."""
    ws = _get_or_create_worksheet(TAB_TRANSACTIONS)
    ws.update(
        values=[[date, tx_type, account, category, amount, description]],
        range_name=f"A{sheet_row}:F{sheet_row}",
        value_input_option="USER_ENTERED",
    )
    read_sheet.clear()


def upsert_starting_balance(month: str, account: str, balance: float):
    """Insert or update a starting balance override."""
    ws = _get_or_create_worksheet(TAB_STARTING_BALANCES)
    all_vals = ws.get_all_values()
    # Look for existing row to update
    for i, row in enumerate(all_vals[1:], start=2):  # skip header
        if len(row) >= 2 and row[0] == month and row[1] == account:
            ws.update_cell(i, 3, balance)
            read_sheet.clear()
            return
    ws.append_row([month, account, balance], value_input_option="USER_ENTERED")
    read_sheet.clear()


def write_settings(settings: dict):
    """
    Overwrite the entire Settings tab with the given dict.
    Keys become column headers; values are lists of items for that column.
    """
    ws = _get_or_create_worksheet(TAB_SETTINGS)
    ws.clear()

    columns = list(settings.keys())
    if not columns:
        return

    max_len = max((len(v) for v in settings.values()), default=0)
    rows: list[list] = [columns]
    for i in range(max_len):
        row = []
        for col in columns:
            vals = settings[col]
            row.append(vals[i] if i < len(vals) else "")
        rows.append(row)

    ws.update(rows, value_input_option="USER_ENTERED")
    read_sheet.clear()


# ── Cash Counts helpers ───────────────────────────────────────────────────────

TAB_CASH_COUNTS = "Cash Counts"


def read_cash_counts() -> pd.DataFrame:
    """Read the monthly cash physical counts tab.
    Columns: Month (YYYY-MM-01), Source, Amount
    """
    df = read_sheet(TAB_CASH_COUNTS)
    if df.empty:
        return df
    df["Month"] = pd.to_datetime(df["Month"], errors="coerce")
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0)
    return df


def upsert_cash_count(month: str, source: str, amount: float):
    """Insert or update a single cash count entry (month + source).
    month should be 'YYYY-MM-01' format.
    """
    ws = _get_or_create_worksheet(TAB_CASH_COUNTS)
    # Ensure header row exists
    all_vals = ws.get_all_values()
    if not all_vals:
        ws.append_row(["Month", "Source", "Amount"])
        all_vals = [["Month", "Source", "Amount"]]

    for i, row in enumerate(all_vals[1:], start=2):
        if len(row) >= 2 and row[0] == month and row[1] == source:
            ws.update_cell(i, 3, amount)
            read_sheet.clear()
            return
    ws.append_row([month, source, amount], value_input_option="USER_ENTERED")
    read_sheet.clear()


# ── Cash In / Cash Out tab helpers ────────────────────────────────────────────


def read_cash_in() -> pd.DataFrame:
    """Read the Cash In tab. Columns: Date, Month, Description, Amount."""
    df = read_sheet(TAB_CASH_IN)
    if df.empty:
        return df
    df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y", errors="coerce")
    df["Month"] = pd.to_datetime(df["Month"], errors="coerce")
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0)
    return df.dropna(subset=["Date"])


def read_cash_out() -> pd.DataFrame:
    """Read the Cash Out tab. Columns: Date, Month, Description, Category, Amount."""
    df = read_sheet(TAB_CASH_OUT)
    if df.empty:
        return df
    df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y", errors="coerce")
    df["Month"] = pd.to_datetime(df["Month"], errors="coerce")
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0)
    return df.dropna(subset=["Date"])


def append_cash_in(date: str, month: str, description: str, amount: float):
    """Append a row to the Cash In tab."""
    ws = _get_or_create_worksheet(TAB_CASH_IN)
    ws.append_row([date, month, description, amount], value_input_option="USER_ENTERED")
    read_sheet.clear()


def append_cash_out(
    date: str, month: str, description: str, category: str, amount: float
):
    """Append a row to the Cash Out tab."""
    ws = _get_or_create_worksheet(TAB_CASH_OUT)
    ws.append_row(
        [date, month, description, category, amount],
        value_input_option="USER_ENTERED",
    )
    read_sheet.clear()


def update_cash_in_row(
    sheet_row: int, date: str, month: str, description: str, amount: float
):
    """Update a specific row in the Cash In tab by its sheet row number."""
    ws = _get_or_create_worksheet(TAB_CASH_IN)
    ws.update(
        values=[[date, month, description, amount]],
        range_name=f"A{sheet_row}:D{sheet_row}",
        value_input_option="USER_ENTERED",
    )
    read_sheet.clear()


def update_cash_out_row(
    sheet_row: int,
    date: str,
    month: str,
    description: str,
    category: str,
    amount: float,
):
    """Update a specific row in the Cash Out tab by its sheet row number."""
    ws = _get_or_create_worksheet(TAB_CASH_OUT)
    ws.update(
        values=[[date, month, description, category, amount]],
        range_name=f"A{sheet_row}:E{sheet_row}",
        value_input_option="USER_ENTERED",
    )
    read_sheet.clear()


# ── Debit In / Debit Out tab helpers ──────────────────────────────────────────


def read_debit_in() -> pd.DataFrame:
    df = read_sheet(TAB_DEBIT_IN)
    if df.empty:
        return df
    df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y", errors="coerce")
    df["Month"] = pd.to_datetime(df["Month"], errors="coerce")
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0)
    return df.dropna(subset=["Date"])


def read_debit_out() -> pd.DataFrame:
    df = read_sheet(TAB_DEBIT_OUT)
    if df.empty:
        return df
    df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y", errors="coerce")
    df["Month"] = pd.to_datetime(df["Month"], errors="coerce")
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0)
    return df.dropna(subset=["Date"])


def append_debit_in(date: str, month: str, description: str, amount: float):
    ws = _get_or_create_worksheet(TAB_DEBIT_IN)
    ws.append_row([date, month, description, amount], value_input_option="USER_ENTERED")
    read_sheet.clear()


def append_debit_out(
    date: str, month: str, description: str, category: str, amount: float
):
    ws = _get_or_create_worksheet(TAB_DEBIT_OUT)
    ws.append_row(
        [date, month, description, category, amount],
        value_input_option="USER_ENTERED",
    )
    read_sheet.clear()


def update_debit_in_row(
    sheet_row: int, date: str, month: str, description: str, amount: float
):
    ws = _get_or_create_worksheet(TAB_DEBIT_IN)
    ws.update(
        values=[[date, month, description, amount]],
        range_name=f"A{sheet_row}:D{sheet_row}",
        value_input_option="USER_ENTERED",
    )
    read_sheet.clear()


def update_debit_out_row(
    sheet_row: int,
    date: str,
    month: str,
    description: str,
    category: str,
    amount: float,
):
    ws = _get_or_create_worksheet(TAB_DEBIT_OUT)
    ws.update(
        values=[[date, month, description, category, amount]],
        range_name=f"A{sheet_row}:E{sheet_row}",
        value_input_option="USER_ENTERED",
    )
    read_sheet.clear()
