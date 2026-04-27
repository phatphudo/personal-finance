import pandas as pd

import utils.gsheets as core


def _hhmm_to_hours(s) -> float | None:
    """Parse 'HH:MM' duration string to decimal hours. Returns None on failure."""
    try:
        s = str(s).strip()
        if not s or s.lower() in ("nan", "none", ""):
            return None
        h, m = s.split(":")
        return int(h) + int(m) / 60
    except Exception:
        return None


def read_work_hours() -> pd.DataFrame:
    df = core.read_sheet(core.TAB_WORK_HOURS)
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

    shift_hours = (df["Clock Out"] - df["Clock In"]).dt.total_seconds() / 3600

    hours_list = []
    break_list = []
    for i in df.index:
        row = df.loc[i]
        shift_h = float(shift_hours.loc[i]) if pd.notna(shift_hours.loc[i]) else 0.0
        status = str(row.get("Status", "Actual"))

        if status == "Actual":
            # Work Hours column is authoritative; Break is derived
            wh = _hhmm_to_hours(row.get("Work Hours", ""))
            if wh is not None and wh > 0:
                hours_list.append(wh)
                break_list.append(max(0.0, shift_h - wh))
            else:
                # Fallback: no stored work hours → assume full shift, no break
                hours_list.append(shift_h)
                break_list.append(0.0)
        else:
            # Scheduled: Break column is authoritative; Work Hours is derived
            br = _hhmm_to_hours(row.get("Break", ""))
            if br is not None and br >= 0:
                hours_list.append(max(0.0, shift_h - br))
                break_list.append(br)
            else:
                hours_list.append(shift_h)
                break_list.append(0.0)

    df["Hours"] = hours_list
    df["Break"] = break_list

    return df.dropna(subset=["Date"])


def append_work_hours(
    date: str,
    clock_in: str,
    clock_out: str,
    status: str = "Actual",
    work_hours: str | None = None,  # HH:MM — filled for Actual rows
    break_time: str | None = None,  # HH:MM — filled for Scheduled rows
):
    ws = core.get_or_create_worksheet(core.TAB_WORK_HOURS)
    ws.append_row(
        [date, clock_in, clock_out, status, work_hours or "", break_time or ""],
        value_input_option="USER_ENTERED",
    )
    core.invalidate_cache()


def update_work_hours_row(
    sheet_row: int,
    date: str,
    clock_in: str,
    clock_out: str,
    status: str,
    work_hours: str | None = None,  # HH:MM — filled for Actual rows
    break_time: str | None = None,  # HH:MM — filled for Scheduled rows
):
    ws = core.get_or_create_worksheet(core.TAB_WORK_HOURS)
    ws.update(
        values=[
            [date, clock_in, clock_out, status, work_hours or "", break_time or ""]
        ],
        range_name=f"A{sheet_row}:F{sheet_row}",
        value_input_option="USER_ENTERED",
    )
    core.invalidate_cache()
