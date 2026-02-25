import pandas as pd

from utils.gsheets import (
    TAB_WORK_HOURS,
    get_or_create_worksheet,
    invalidate_cache,
    read_sheet,
)


def read_work_hours() -> pd.DataFrame:
    df = read_sheet(TAB_WORK_HOURS)
    if df.empty:
        return df

    if "Status" not in df.columns:
        df["Status"] = "Actual"
    df["Status"] = df["Status"].replace("", "Actual").fillna("Actual")

    df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y", errors="coerce")
    df["Clock In"] = df["Clock In"].astype(str).replace("", pd.NA)
    df["Clock Out"] = df["Clock Out"].astype(str).replace("", pd.NA)

    df["Clock In"] = pd.to_datetime(
        df["Date"].dt.strftime("%Y-%m-%d") + " " + df["Clock In"],
        errors="coerce",
    )
    df["Clock Out"] = pd.to_datetime(
        df["Date"].dt.strftime("%Y-%m-%d") + " " + df["Clock Out"],
        errors="coerce",
    )
    df["Hours"] = (df["Clock Out"] - df["Clock In"]).dt.total_seconds() / 3600
    return df.dropna(subset=["Date"])


def append_work_hours(date: str, clock_in: str, clock_out: str, status: str = "Actual"):
    ws = get_or_create_worksheet(TAB_WORK_HOURS)
    ws.append_row(
        [date, clock_in, clock_out, status], value_input_option="USER_ENTERED"
    )
    invalidate_cache()


def update_work_hours_row(
    sheet_row: int, date: str, clock_in: str, clock_out: str, status: str
):
    ws = get_or_create_worksheet(TAB_WORK_HOURS)
    ws.update(
        values=[[date, clock_in, clock_out, status]],
        range_name=f"A{sheet_row}:D{sheet_row}",
        value_input_option="USER_ENTERED",
    )
    invalidate_cache()
