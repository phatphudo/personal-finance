import pandas as pd

import utils.gsheets as core


def read_cash_in() -> pd.DataFrame:
    df = core.read_sheet(core.TAB_CASH_IN)
    if df.empty:
        return df
    df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y", errors="coerce")
    df["Month"] = pd.to_datetime(df["Month"], errors="coerce")
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0)
    return df.dropna(subset=["Date"])


def read_cash_out() -> pd.DataFrame:
    df = core.read_sheet(core.TAB_CASH_OUT)
    if df.empty:
        return df
    df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y", errors="coerce")
    df["Month"] = pd.to_datetime(df["Month"], errors="coerce")
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0)
    return df.dropna(subset=["Date"])


def append_cash_in(date: str, month: str, description: str, amount: float):
    ws = core.get_or_create_worksheet(core.TAB_CASH_IN)
    ws.append_row([date, month, description, amount], value_input_option="USER_ENTERED")
    core.invalidate_cache()


def append_cash_out(
    date: str, month: str, description: str, category: str, amount: float
):
    ws = core.get_or_create_worksheet(core.TAB_CASH_OUT)
    ws.append_row(
        [date, month, description, category, amount],
        value_input_option="USER_ENTERED",
    )
    core.invalidate_cache()


def update_cash_in_row(
    sheet_row: int, date: str, month: str, description: str, amount: float
):
    ws = core.get_or_create_worksheet(core.TAB_CASH_IN)
    ws.update(
        values=[[date, month, description, amount]],
        range_name=f"A{sheet_row}:D{sheet_row}",
        value_input_option="USER_ENTERED",
    )
    core.invalidate_cache()


def update_cash_out_row(
    sheet_row: int,
    date: str,
    month: str,
    description: str,
    category: str,
    amount: float,
):
    ws = core.get_or_create_worksheet(core.TAB_CASH_OUT)
    ws.update(
        values=[[date, month, description, category, amount]],
        range_name=f"A{sheet_row}:E{sheet_row}",
        value_input_option="USER_ENTERED",
    )
    core.invalidate_cache()
