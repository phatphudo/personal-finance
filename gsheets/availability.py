"""
Availability template — read/write for the 'Availability' Google Sheet tab.

Schema: Day | Clock In | Clock Out | Break
- 'Day' is the weekday name (Monday … Sunday).
- Rows for working days have Clock In / Clock Out / Break filled.
- Non-working days are stored with empty time fields.
"""

from __future__ import annotations

import pandas as pd

import utils.gsheets as core

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Default template: Tue/Wed/Thu 10:00–21:30, Sat/Sun 08:00–21:30, break 01:00
_DEFAULTS: dict[str, dict] = {
    "Tuesday":   {"Clock In": "10:00", "Clock Out": "21:30", "Break": "01:00"},
    "Wednesday": {"Clock In": "10:00", "Clock Out": "21:30", "Break": "01:00"},
    "Thursday":  {"Clock In": "10:00", "Clock Out": "21:30", "Break": "01:00"},
    "Saturday":  {"Clock In": "08:00", "Clock Out": "21:30", "Break": "01:00"},
    "Sunday":    {"Clock In": "08:00", "Clock Out": "21:30", "Break": "01:00"},
}


def read_availability() -> pd.DataFrame:
    """
    Return the availability template as a 7-row DataFrame (one per weekday).
    Rows from the sheet are merged with defaults; missing days get empty strings.
    Always returns exactly 7 rows in Mon–Sun order.
    """
    raw = core.read_sheet(core.TAB_AVAILABILITY)

    # Build a lookup from sheet: Day → {Clock In, Clock Out, Break}
    sheet_map: dict[str, dict] = {}
    if not raw.empty and "Day" in raw.columns:
        for _, row in raw.iterrows():
            day = str(row.get("Day", "")).strip()
            if day in WEEKDAYS:
                sheet_map[day] = {
                    "Clock In":  str(row.get("Clock In", "")).strip(),
                    "Clock Out": str(row.get("Clock Out", "")).strip(),
                    "Break":     str(row.get("Break", "")).strip(),
                }

    rows = []
    for day in WEEKDAYS:
        if sheet_map:
            # Sheet exists — use stored values (may be empty for off-days)
            entry = sheet_map.get(day, {"Clock In": "", "Clock Out": "", "Break": ""})
        else:
            # Sheet is empty/new — seed with defaults
            entry = _DEFAULTS.get(day, {"Clock In": "", "Clock Out": "", "Break": ""})
        rows.append({"Day": day, **entry})

    return pd.DataFrame(rows)


def write_availability(rows: list[dict]) -> None:
    """
    Overwrite the Availability sheet with the provided rows.

    Each dict must have keys: Day, Clock In, Clock Out, Break.
    Only rows where Clock In is non-empty are written (off-days are skipped
    to keep the sheet clean), but the template logic always stores all 7 days
    so the UI can re-read them in order.
    """
    ws = core.get_or_create_worksheet(core.TAB_AVAILABILITY)

    # Clear existing data rows (keep header in row 1)
    # We do a full clear + re-write to avoid stale rows.
    ws.clear()
    ws.append_row(["Day", "Clock In", "Clock Out", "Break"], value_input_option="USER_ENTERED")

    data = [
        [r["Day"], r.get("Clock In", ""), r.get("Clock Out", ""), r.get("Break", "")]
        for r in rows
    ]
    if data:
        ws.append_rows(data, value_input_option="USER_ENTERED")

    core.invalidate_cache()
