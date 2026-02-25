import pandas as pd

import utils.gsheets as core


def read_credit_tx() -> pd.DataFrame:
    df = core.read_sheet(core.TAB_CREDIT_TX)
    if df.empty:
        return df
    df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y", errors="coerce")
    df["Month"] = pd.to_datetime(df["Month"], errors="coerce")
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0)
    return df.dropna(subset=["Date"])


def append_credit_tx(
    date: str, month: str, description: str, category: str, amount: float
):
    ws = core.get_or_create_worksheet(core.TAB_CREDIT_TX)
    ws.append_row(
        [date, month, description, category, amount],
        value_input_option="USER_ENTERED",
    )
    core.invalidate_cache()


def update_credit_tx_row(
    sheet_row: int,
    date: str,
    month: str,
    description: str,
    category: str,
    amount: float,
):
    ws = core.get_or_create_worksheet(core.TAB_CREDIT_TX)
    ws.update(
        values=[[date, month, description, category, amount]],
        range_name=f"A{sheet_row}:E{sheet_row}",
        value_input_option="USER_ENTERED",
    )
    core.invalidate_cache()
