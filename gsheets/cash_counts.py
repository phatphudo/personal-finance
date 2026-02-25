import pandas as pd

import utils.gsheets as core


def read_cash_counts() -> pd.DataFrame:
    df = core.read_sheet(core.TAB_CASH_COUNTS)
    if df.empty:
        return df
    df["Month"] = pd.to_datetime(df["Month"], errors="coerce")
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0)
    return df


def upsert_cash_count(month: str, source: str, amount: float):
    ws = core.get_or_create_worksheet(core.TAB_CASH_COUNTS)
    all_vals = ws.get_all_values()
    if not all_vals:
        ws.append_row(["Month", "Source", "Amount"])
        all_vals = [["Month", "Source", "Amount"]]
    for i, row in enumerate(all_vals[1:], start=2):
        if len(row) >= 2 and row[0] == month and row[1] == source:
            ws.update_cell(i, 3, amount)
            core.invalidate_cache()
            return
    ws.append_row([month, source, amount], value_input_option="USER_ENTERED")
    core.invalidate_cache()
