"""
Pay Periods sheet — 3 columns: Pay Period | Current Rate | Expected Rate

Pay Period is stored as the period-start date string "MM/DD/YYYY"
(matching the anchor format used in utils/helpers.py).
"""
import datetime

import pandas as pd

import utils.gsheets as core


def _label_to_date(label: str) -> datetime.date | None:
    try:
        return datetime.datetime.strptime(label, "%m/%d/%Y").date()
    except Exception:
        return None


def read_pay_periods() -> pd.DataFrame:
    """Return all rows as a DataFrame with columns: Pay Period (date), Current Rate, Expected Rate."""
    df = core.read_sheet(core.TAB_PAY_PERIODS)
    if df.empty:
        return pd.DataFrame(columns=["Pay Period", "Current Rate", "Expected Rate", "_SheetRow"])
    for col in ("Current Rate", "Expected Rate"):
        if col not in df.columns:
            df[col] = ""
    df["Current Rate"] = pd.to_numeric(df["Current Rate"], errors="coerce")
    df["Expected Rate"] = pd.to_numeric(df["Expected Rate"], errors="coerce")
    df["Pay Period"] = pd.to_datetime(df["Pay Period"], format="%m/%d/%Y", errors="coerce").dt.date
    return df.dropna(subset=["Pay Period"])


def get_period_rates(period_start: datetime.date, default_current: float, default_expected: float) -> tuple[float, float]:
    """Return (current_rate, expected_rate) for a given period start date."""
    df = read_pay_periods()
    if df.empty:
        return default_current, default_expected
    row = df[df["Pay Period"] == period_start]
    if row.empty:
        return default_current, default_expected
    r = row.iloc[0]
    cur = float(r["Current Rate"]) if pd.notna(r["Current Rate"]) else default_current
    exp = float(r["Expected Rate"]) if pd.notna(r["Expected Rate"]) else default_expected
    return cur, exp


def upsert_pay_period_rates(
    period_start: datetime.date,
    current_rate: float,
    expected_rate: float,
):
    """Insert or update the rates for a pay period."""
    ws = core.get_or_create_worksheet(core.TAB_PAY_PERIODS)
    df = read_pay_periods()

    period_str = period_start.strftime("%m/%d/%Y")
    match = df[df["Pay Period"] == period_start]

    if not match.empty:
        sheet_row = int(match.iloc[0]["_SheetRow"])
        ws.update(
            values=[[period_str, current_rate, expected_rate]],
            range_name=f"A{sheet_row}:C{sheet_row}",
            value_input_option="USER_ENTERED",
        )
    else:
        ws.append_row(
            [period_str, current_rate, expected_rate],
            value_input_option="USER_ENTERED",
        )

    core.invalidate_cache()
