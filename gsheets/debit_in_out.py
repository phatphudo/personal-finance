import pandas as pd

from utils.gsheets import (
    TAB_DEBIT_IN,
    TAB_DEBIT_OUT,
    get_or_create_worksheet,
    invalidate_cache,
    read_sheet,
)


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
    ws = get_or_create_worksheet(TAB_DEBIT_IN)
    ws.append_row([date, month, description, amount], value_input_option="USER_ENTERED")
    invalidate_cache()


def append_debit_out(
    date: str, month: str, description: str, category: str, amount: float
):
    ws = get_or_create_worksheet(TAB_DEBIT_OUT)
    ws.append_row(
        [date, month, description, category, amount],
        value_input_option="USER_ENTERED",
    )
    invalidate_cache()


def update_debit_in_row(
    sheet_row: int, date: str, month: str, description: str, amount: float
):
    ws = get_or_create_worksheet(TAB_DEBIT_IN)
    ws.update(
        values=[[date, month, description, amount]],
        range_name=f"A{sheet_row}:D{sheet_row}",
        value_input_option="USER_ENTERED",
    )
    invalidate_cache()


def update_debit_out_row(
    sheet_row: int,
    date: str,
    month: str,
    description: str,
    category: str,
    amount: float,
):
    ws = get_or_create_worksheet(TAB_DEBIT_OUT)
    ws.update(
        values=[[date, month, description, category, amount]],
        range_name=f"A{sheet_row}:E{sheet_row}",
        value_input_option="USER_ENTERED",
    )
    invalidate_cache()
