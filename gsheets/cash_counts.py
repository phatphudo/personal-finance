import pandas as pd

from utils.gsheets import (
    TAB_CASH_COUNTS,
    get_or_create_worksheet,
    invalidate_cache,
    read_sheet,
)


def read_cash_counts() -> pd.DataFrame:
    df = read_sheet(TAB_CASH_COUNTS)
    if df.empty:
        return df
    df["Month"] = pd.to_datetime(df["Month"], errors="coerce")
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0)
    return df


def upsert_cash_count(month: str, source: str, amount: float):
    ws = get_or_create_worksheet(TAB_CASH_COUNTS)
    all_vals = ws.get_all_values()
    if not all_vals:
        ws.append_row(["Month", "Source", "Amount"])
        all_vals = [["Month", "Source", "Amount"]]
    for i, row in enumerate(all_vals[1:], start=2):
        if len(row) >= 2 and row[0] == month and row[1] == source:
            ws.update_cell(i, 3, amount)
            invalidate_cache()
            return
    ws.append_row([month, source, amount], value_input_option="USER_ENTERED")
    invalidate_cache()
