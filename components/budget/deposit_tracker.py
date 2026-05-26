"""
Deposit Tracker — shows past cash→debit deposits and suggested future ones.

Past:       Debit In rows where Description starts with "From cash", grouped
            into windows between consecutive paycheck dates (Cash In, Category=Paycheck).

Suggested:  2–4 deposits per month for the current + next 2 months.
            Suggestions are saved to the 'Deposit Suggestions' Google Sheet
            tab on first generation and reloaded on every visit (persistent).
            Re-randomize clears + regenerates all displayed months.

Amount pool: $400–$1,800, $1 increments, excluding multiples of 10.
"""

from __future__ import annotations

import calendar
import datetime
import random

import pandas as pd
import streamlit as st

from utils.gsheets import (
    read_cash_in,
    read_debit_in,
    read_deposit_suggestions,
    write_all_suggestions,
)

_DEPOSIT_PREFIX = "From cash"
_PAYCHECK_CATEGORY = "paycheck"  # case-insensitive match


# ── Suggestion engine ─────────────────────────────────────────────────────────

_AMOUNT_POOL = [a for a in range(400, 1801) if a % 10 != 0]


def _generate_suggestions(
    year: int,
    month: int,
    logged_future_dates: set[datetime.date],
    today: datetime.date,
) -> list[tuple[datetime.date, float]]:
    """
    Generate 2–4 (date, amount) tuples for the given month.
    Uses a truly random seed each call — caller decides when to invoke.

    Constraints:
    - Only future dates (> today)
    - No two deposits within 7 calendar days
    - No repeated weekday within the month
    - Amounts: $400–$1,800 in $1 steps, no multiples of 10
    """
    rng = random.Random()

    target_count = rng.choice([2, 2, 3, 3, 3, 4])

    _, last_day = calendar.monthrange(year, month)
    earliest_day = max(
        today.day + 1 if (today.year == year and today.month == month) else 1,
        5,
    )
    latest_day = last_day - 2

    if earliest_day > latest_day:
        return []

    candidates: list[datetime.date] = []
    for d in range(earliest_day, latest_day + 1):
        dt = datetime.date(year, month, d)
        if dt > today and dt not in logged_future_dates:
            candidates.append(dt)

    rng.shuffle(candidates)

    # Pass 1: strict — no same weekday + 7-day gap
    chosen: list[datetime.date] = []
    for dt in candidates:
        if len(chosen) == target_count:
            break
        if any(abs((dt - c).days) < 7 for c in chosen):
            continue
        if any(c.weekday() == dt.weekday() for c in chosen):
            continue
        chosen.append(dt)

    # Pass 2: relax weekday if fewer than 2 found
    if len(chosen) < 2:
        chosen = []
        for dt in candidates:
            if len(chosen) == target_count:
                break
            if any(abs((dt - c).days) < 7 for c in chosen):
                continue
            chosen.append(dt)

    if not chosen:
        return []

    amounts = rng.sample(_AMOUNT_POOL, min(len(chosen), len(_AMOUNT_POOL)))
    return sorted(zip(chosen, amounts[: len(chosen)]))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _weekday_abbr(dt: datetime.date) -> str:
    return dt.strftime("%a")


def _month_key(year: int, month: int) -> str:
    return f"{year}-{month:02d}-01"


def _next_month(d: datetime.date) -> datetime.date:
    return (d.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)


# ── Past deposits section ─────────────────────────────────────────────────────

def _render_past_deposits(di_df: pd.DataFrame, ci_df: pd.DataFrame, today: datetime.date):
    st.markdown("### 📋 Past Deposits")

    # ── Paychecks from Cash In ────────────────────────────────────────────────
    if ci_df.empty or "Category" not in ci_df.columns:
        paycheck_df = pd.DataFrame()
    else:
        mask = ci_df["Category"].str.strip().str.lower() == _PAYCHECK_CATEGORY
        paycheck_df = ci_df[mask].copy().sort_values("Date").reset_index(drop=True)

    # ── Cash deposits from Debit In ───────────────────────────────────────────
    if di_df.empty or "Description" not in di_df.columns:
        deposit_df = pd.DataFrame()
    else:
        dep_mask = di_df["Description"].str.startswith(_DEPOSIT_PREFIX, na=False)
        deposit_df = di_df[dep_mask].copy().sort_values("Date").reset_index(drop=True)

    if paycheck_df.empty:
        st.info(
            "No paycheck entries found in **Cash In** (Category = 'Paycheck'). "
            "Add your first paycheck there to enable grouping."
        )
        if not deposit_df.empty:
            st.dataframe(
                pd.DataFrame({
                    "Date":    deposit_df["Date"].dt.strftime("%m/%d/%Y"),
                    "Weekday": deposit_df["Date"].dt.strftime("%A"),
                    "Amount":  deposit_df["Amount"].apply(lambda x: f"${x:,.2f}"),
                }),
                hide_index=True,
                width="stretch",
            )
        return

    pay_dates: list[datetime.date] = paycheck_df["Date"].dt.date.tolist()

    # Build windows [pay_date_i → pay_date_{i+1}), last window is open-ended
    windows: list[tuple[datetime.date, datetime.date | None]] = []
    for i, pd_date in enumerate(pay_dates):
        end = pay_dates[i + 1] if i + 1 < len(pay_dates) else None
        windows.append((pd_date, end))

    # Build flat rows — most recent window first
    table_rows: list[dict] = []
    for win_start, win_end in reversed(windows):
        # Paycheck amount for this window
        pc_rows = paycheck_df[paycheck_df["Date"].dt.date == win_start]
        paycheck_amount = pc_rows["Amount"].sum() if not pc_rows.empty else 0.0

        # Deposits in [win_start, win_end)
        if not deposit_df.empty:
            if win_end is not None:
                dep_mask = (
                    (deposit_df["Date"].dt.date >= win_start)
                    & (deposit_df["Date"].dt.date < win_end)
                )
            else:
                dep_mask = deposit_df["Date"].dt.date >= win_start
            window_deps = deposit_df[dep_mask].sort_values("Date").reset_index(drop=True)
        else:
            window_deps = pd.DataFrame()

        pc_date_str = win_start.strftime("%m/%d/%Y")
        pc_amt_str = f"${paycheck_amount:,.2f}"

        if window_deps.empty:
            # Show one row for the paycheck with no deposit data
            table_rows.append({
                "Pay Date":   pc_date_str,
                "Pay Amount": pc_amt_str,
                "Dep Date":   "—",
                "Weekday":    "—",
                "Amount":     "—",
            })
        else:
            for i, (_, dep) in enumerate(window_deps.iterrows()):
                table_rows.append({
                    "Pay Date":   pc_date_str if i == 0 else "",
                    "Pay Amount": pc_amt_str  if i == 0 else "",
                    "Dep Date":   dep["Date"].strftime("%m/%d/%Y"),
                    "Weekday":    _weekday_abbr(dep["Date"].date()),
                    "Amount":     f"${dep['Amount']:,.2f}",
                })

    if not table_rows:
        st.info("No deposits found yet.")
        return

    st.dataframe(
        pd.DataFrame(table_rows),
        hide_index=True,
        width="stretch",
        column_config={
            "Pay Date":   st.column_config.TextColumn("Pay Date"),
            "Pay Amount": st.column_config.TextColumn("Pay Amount"),
            "Dep Date":   st.column_config.TextColumn("Deposit Date"),
            "Weekday":    st.column_config.TextColumn("Day"),
            "Amount":     st.column_config.TextColumn("Amount"),
        },
    )




# ── Render ────────────────────────────────────────────────────────────────────

def render():
    st.markdown("## 💵 Deposit Tracker")
    st.caption(
        "Tracks cash → debit account deposits. "
        "Past deposits are grouped by paycheck window. "
        "Suggestions are saved and persist across page reloads."
    )

    try:
        di_df = read_debit_in()
        ci_df = read_cash_in()
        sug_df = read_deposit_suggestions()
    except Exception as e:
        st.error(f"Could not load data: {e}")
        return

    today = datetime.date.today()

    # ── Past deposits (grouped by paycheck window) ────────────────────────────
    st.markdown("---")
    _render_past_deposits(di_df, ci_df, today)

    # ── Suggested deposits ────────────────────────────────────────────────────
    st.markdown("---")

    col_head, col_btn = st.columns([3, 1])
    col_head.markdown("### 🎲 Suggested Deposits")
    col_head.caption(
        "2–4 deposits per month — irregular dates, weekdays, and amounts. "
        "Adjust amounts as you see fit before depositing."
    )

    # Collect future-logged dates to exclude from suggestions
    logged_future_dates: set[datetime.date] = set()
    if not di_df.empty:
        mask = di_df["Description"].str.startswith(_DEPOSIT_PREFIX, na=False)
        future_mask = mask & (di_df["Date"].dt.date > today)
        logged_future_dates = set(di_df[future_mask]["Date"].dt.date.tolist())

    # Build list of 3 months to display
    month_start = datetime.date(today.year, today.month, 1)
    display_months: list[datetime.date] = []
    m = month_start
    for _ in range(3):
        display_months.append(m)
        m = _next_month(m)

    display_month_keys = {_month_key(m.year, m.month) for m in display_months}

    # Load stored suggestions
    stored: dict[str, list[tuple[datetime.date, float]]] = {}
    if not sug_df.empty:
        for mk, group in sug_df.groupby("Month"):
            if mk in display_month_keys:
                stored[mk] = [
                    (row["Date"].date(), float(row["Amount"]))
                    for _, row in group.sort_values("Date").iterrows()
                ]

    if col_btn.button(
        "🔀 Re-randomize",
        key="reseed_deposits",
        help="Generate a fresh set of suggestions for all displayed months",
    ):
        kept_rows: list[dict] = []
        if not sug_df.empty:
            for _, row in sug_df.iterrows():
                if row["Month"] not in display_month_keys:
                    kept_rows.append({
                        "Month":  row["Month"],
                        "Date":   row["Date"].strftime("%m/%d/%Y"),
                        "Amount": float(row["Amount"]),
                    })
        write_all_suggestions(kept_rows)
        stored = {}
        st.rerun()

    all_new_rows: list[dict] = []
    any_suggestions = False

    for month_dt in display_months:
        yr, mo = month_dt.year, month_dt.month
        mk = _month_key(yr, mo)
        month_name = month_dt.strftime("%B %Y")

        if mk in stored and stored[mk]:
            suggestions = stored[mk]
        else:
            suggestions = _generate_suggestions(yr, mo, logged_future_dates, today)
            for dt, amt in suggestions:
                all_new_rows.append({
                    "Month":  mk,
                    "Date":   dt.strftime("%m/%d/%Y"),
                    "Amount": amt,
                })

        if not suggestions:
            st.markdown(f"**{month_name}** — *No future dates available for suggestions.*")
            continue

        any_suggestions = True

        total_sug = sum(amt for _, amt in suggestions)
        st.markdown(
            f"**{month_name}** &nbsp;·&nbsp; "
            f"{len(suggestions)} deposits &nbsp;·&nbsp; "
            f"Est. total: **${total_sug:,.2f}**"
        )

        rows = [
            {
                "Date":    dt.strftime("%m/%d/%Y"),
                "Weekday": dt.strftime("%A"),
                "Amount":  f"${amt:,.2f}",
            }
            for dt, amt in suggestions
        ]
        st.dataframe(
            pd.DataFrame(rows),
            hide_index=True,
            width="stretch",
            column_config={
                "Date":    st.column_config.TextColumn("Date"),
                "Weekday": st.column_config.TextColumn("Weekday"),
                "Amount":  st.column_config.TextColumn("Suggested Amount"),
            },
        )

    if not any_suggestions:
        st.info("No suggestions could be generated — all future dates are past or fully booked.")

    if all_new_rows:
        existing_rows: list[dict] = []
        if not sug_df.empty:
            new_months = {r["Month"] for r in all_new_rows}
            for _, row in sug_df.iterrows():
                if row["Month"] not in new_months:
                    existing_rows.append({
                        "Month":  row["Month"],
                        "Date":   row["Date"].strftime("%m/%d/%Y"),
                        "Amount": float(row["Amount"]),
                    })
        with st.spinner("Saving suggestions…"):
            write_all_suggestions(existing_rows + all_new_rows)
