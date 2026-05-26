"""
Deposit Suggestions sheet CRUD.

Schema: Month (YYYY-MM-01) | Date (MM/DD/YYYY) | Amount (float)

One row per suggested deposit. Suggestions for a month are written once
(first visit) and persist until explicitly cleared (re-randomize).
"""

from __future__ import annotations

import datetime

import pandas as pd

import utils.gsheets as core


def read_deposit_suggestions() -> pd.DataFrame:
    """Return all stored suggestions as a DataFrame."""
    df = core.read_sheet(core.TAB_DEPOSIT_SUGGESTIONS)
    if df.empty:
        return pd.DataFrame(columns=["Month", "Date", "Amount"])
    df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y", errors="coerce")
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce")
    df["Month"] = df["Month"].astype(str).str.strip()
    return df.dropna(subset=["Date", "Amount"])


def write_all_suggestions(rows: list[dict]) -> None:
    """
    Overwrite the entire Deposit Suggestions sheet with the provided rows.
    Each dict: {"Month": "YYYY-MM-01", "Date": "MM/DD/YYYY", "Amount": float}
    """
    ws = core.get_or_create_worksheet(core.TAB_DEPOSIT_SUGGESTIONS)
    ws.clear()
    ws.append_row(["Month", "Date", "Amount"], value_input_option="USER_ENTERED")
    if rows:
        data = [[r["Month"], r["Date"], r["Amount"]] for r in rows]
        ws.append_rows(data, value_input_option="USER_ENTERED")
    core.invalidate_cache()
