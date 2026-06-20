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
    """Return all rows as a DataFrame with columns: Pay Period (date), Current Rate, Expected Rate, Total Hours."""
    df = core.read_sheet(core.TAB_PAY_PERIODS)
    if df.empty:
        return pd.DataFrame(columns=["Pay Period", "Current Rate", "Expected Rate", "Total Hours", "_SheetRow"])
    for col in ("Current Rate", "Expected Rate", "Total Hours"):
        if col not in df.columns:
            df[col] = ""
    df["Current Rate"] = pd.to_numeric(df["Current Rate"], errors="coerce")
    df["Expected Rate"] = pd.to_numeric(df["Expected Rate"], errors="coerce")
    df["Total Hours"] = pd.to_numeric(df["Total Hours"], errors="coerce")
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


def upsert_pay_period_info(
    period_start: datetime.date,
    current_rate: float | None = None,
    expected_rate: float | None = None,
    total_hours: float | None = None,
):
    """Insert or update the rates and/or total hours for a pay period."""
    ws = core.get_or_create_worksheet(core.TAB_PAY_PERIODS)
    df = read_pay_periods()

    period_str = period_start.strftime("%m/%d/%Y")
    match = df[df["Pay Period"] == period_start]

    if not match.empty:
        row = match.iloc[0]
        sheet_row = int(row["_SheetRow"])
        
        # Fall back to existing values if not specified
        cur = current_rate if current_rate is not None else (float(row["Current Rate"]) if pd.notna(row["Current Rate"]) else "")
        exp = expected_rate if expected_rate is not None else (float(row["Expected Rate"]) if pd.notna(row["Expected Rate"]) else "")
        hours = total_hours if total_hours is not None else (float(row["Total Hours"]) if pd.notna(row["Total Hours"]) else "")

        ws.update(
            values=[[period_str, cur, exp, hours]],
            range_name=f"A{sheet_row}:D{sheet_row}",
            value_input_option="USER_ENTERED",
        )
    else:
        cur = current_rate if current_rate is not None else ""
        exp = expected_rate if expected_rate is not None else ""
        hours = total_hours if total_hours is not None else ""
        ws.append_row(
            [period_str, cur, exp, hours],
            value_input_option="USER_ENTERED",
        )

    core.invalidate_cache()


def upsert_pay_period_rates(
    period_start: datetime.date,
    current_rate: float,
    expected_rate: float,
):
    """Insert or update the rates for a pay period (delegates to upsert_pay_period_info)."""
    upsert_pay_period_info(period_start, current_rate=current_rate, expected_rate=expected_rate)
