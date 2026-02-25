import pandas as pd

import utils.gsheets as core


def read_starting_balances() -> pd.DataFrame:
    df = core.read_sheet(core.TAB_STARTING_BALANCES)
    if df.empty:
        return df
    df["Month"] = pd.to_datetime(df["Month"], errors="coerce")
    df["Starting Balance"] = pd.to_numeric(df["Starting Balance"], errors="coerce")
    return df


def upsert_starting_balance(month: str, account: str, balance: float):
    ws = core.get_or_create_worksheet(core.TAB_STARTING_BALANCES)
    all_vals = ws.get_all_values()
    for i, row in enumerate(all_vals[1:], start=2):
        if len(row) >= 2 and row[0] == month and row[1] == account:
            ws.update_cell(i, 3, balance)
            core.invalidate_cache()
            return
    ws.append_row([month, account, balance], value_input_option="USER_ENTERED")
    core.invalidate_cache()
