import pandas as pd

from utils.gsheets import (
    TAB_SETTINGS,
    get_or_create_worksheet,
    invalidate_cache,
    read_sheet,
)


def read_settings() -> dict:
    """Return a dict of lists from the Settings tab."""
    df = read_sheet(TAB_SETTINGS)
    settings = {}
    for col in df.columns:
        settings[col] = df[col].dropna().replace("", pd.NA).dropna().tolist()
    return settings


def write_settings(settings: dict):
    """
    Overwrite the entire Settings tab with the given dict.
    Keys become column headers; values are lists of items for that column.
    """
    ws = get_or_create_worksheet(TAB_SETTINGS)
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
    invalidate_cache()
