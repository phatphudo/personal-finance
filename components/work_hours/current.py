import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.settings import get_default_rates
from utils.gsheets import (
    append_work_hours,
    get_period_rates,
    read_availability,
    read_pay_periods,
    read_settings,
    read_work_hours,
    upsert_pay_period_info,
    upsert_pay_period_rates,
    write_availability,
)
from utils.helpers import (
    get_all_pay_periods,
    get_pay_period_label,
    get_pay_period_start,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_hhmm(s: str) -> float | None:
    """Parse HH:MM duration string to decimal hours. Returns None on failure."""
    try:
        parts = s.strip().split(":")
        h, m = int(parts[0]), int(parts[1])
        return h + m / 60
    except Exception:
        return None


def _parse_time(s: str) -> datetime.time | None:
    try:
        return pd.to_datetime(s).time()
    except Exception:
        return None


def _shift_hours(clock_in: str, clock_out: str) -> float | None:
    """Return decimal hours between two HH:MM strings, or None if unparseable."""
    ci = _parse_time(clock_in)
    co = _parse_time(clock_out)
    if ci is None or co is None:
        return None
    delta = datetime.datetime.combine(
        datetime.date.today(), co
    ) - datetime.datetime.combine(datetime.date.today(), ci)
    return delta.total_seconds() / 3600


def _fmt_hm(h_float) -> str:
    """Format decimal hours as HH:MM."""
    if pd.isna(h_float) or h_float is None:
        return ""
    hrs = int(h_float)
    mins = int(round((h_float - hrs) * 60))
    return f"{hrs:02d}:{mins:02d}"


def render():
    st.markdown("## 🗓️ Current Pay Period")

    try:
        df = read_work_hours()
        settings = read_settings()
        df_pp = read_pay_periods()
    except Exception as e:
        st.error(f"Could not load data: {e}")
        return

    today = datetime.date.today()
    default_cur, default_exp = get_default_rates(settings)

    # ── Period selector ────────────────────────────────────────────────────
    all_periods = get_all_pay_periods(df) if not df.empty else []
    current_period_start = get_pay_period_start(today)

    if all_periods and current_period_start not in all_periods:
        all_periods = [current_period_start] + list(all_periods)
    elif not all_periods:
        all_periods = [current_period_start]

    period_labels = {get_pay_period_label(p): p for p in all_periods}
    default_label = get_pay_period_label(current_period_start)

    selected_label = st.selectbox(
        "Pay Period",
        list(period_labels.keys()),
        index=(
            list(period_labels.keys()).index(default_label)
            if default_label in period_labels
            else 0
        ),
        key="wh_current_period",
    )
    period_start = period_labels[selected_label]
    period_end = period_start + datetime.timedelta(days=13)

    # ── Filter data for selected period ────────────────────────────────────
    if not df.empty:
        mask = (df["Date"].dt.date >= period_start) & (df["Date"].dt.date <= period_end)
        period_df = df[mask].copy()
    else:
        period_df = pd.DataFrame()

    # ── Rate editor for this period ─────────────────────────────────────────
    cur_rate, exp_rate = get_period_rates(period_start, default_cur, default_exp)
    with st.expander("⚙️ Pay Rates for this Period", expanded=False):
        col_rc, col_re, col_save = st.columns([1, 1, 1])
        new_cur = col_rc.number_input(
            "Current Rate ($/hr)", value=cur_rate, min_value=0.0, step=0.25,
            format="%.2f", key=f"cur_rate_{period_start}"
        )
        new_exp = col_re.number_input(
            "Expected Rate ($/hr)", value=exp_rate, min_value=0.0, step=0.25,
            format="%.2f", key=f"exp_rate_{period_start}"
        )
        col_save.markdown("&nbsp;")  # spacer
        if col_save.button("💾 Save Rates", key=f"save_rates_{period_start}", type="primary"):
            with st.spinner("Saving rates…"):
                upsert_pay_period_rates(period_start, new_cur, new_exp)
            st.success(f"Rates saved: Current ${new_cur:.2f} | Expected ${new_exp:.2f}")
            st.rerun()
        cur_rate, exp_rate = new_cur, new_exp  # use edited values immediately

    # ── Availability template panel ────────────────────────────────────────
    avail_df = read_availability()

    with st.expander("📋 Weekly Availability Template", expanded=False):
        st.caption(
            "Set your recurring weekly schedule. "
            "Use the **Apply Availability** button under each week to bulk-add Scheduled shifts."
        )

        edited_avail = st.data_editor(
            avail_df,
            key="avail_editor",
            hide_index=True,
            width="stretch",
            column_config={
                "Day": st.column_config.Column("Day", disabled=True),
                "Clock In": st.column_config.TextColumn(
                    "Clock In", help="HH:MM (leave blank for day off)"
                ),
                "Clock Out": st.column_config.TextColumn(
                    "Clock Out", help="HH:MM (leave blank for day off)"
                ),
                "Break": st.column_config.TextColumn(
                    "Break", help="HH:MM break duration (default 01:00)"
                ),
            },
        )

        if st.button("💾 Save Availability", key="save_avail_btn", type="primary"):
            rows = edited_avail.to_dict(orient="records")
            with st.spinner("Saving availability…"):
                write_availability(rows)
            st.success("✅ Availability template saved!")
            st.rerun()

    with st.expander("➕ Log New Shift", expanded=False):
        with st.form("log_shift_form"):
            col1, col2, col3, col4 = st.columns(4)
            shift_date = col1.date_input("Date", value=today)
            clock_in = col2.text_input("Clock In (HH:MM)", value="09:00")
            clock_out = col3.text_input("Clock Out (HH:MM)", value="17:00")
            break_val = col4.text_input(
                "Break (HH:MM)", value="00:00", help="Estimated break, e.g. 00:30"
            )
            submitted = st.form_submit_button("Save Shift", type="primary")

        if submitted:
            try:
                ci_time = _parse_time(clock_in)
                co_time = _parse_time(clock_out)
                if ci_time is None or co_time is None:
                    raise ValueError("bad time")

                shift_h = _shift_hours(clock_in, clock_out)
                break_f = _parse_hhmm(break_val)
                if break_f is None:
                    raise ValueError(f"Cannot parse '{break_val}' as HH:MM")

                work_h = shift_h - break_f  # derived: shift − break

                if work_h <= 0:
                    st.error("⚠️ Break time equals or exceeds shift duration.")
                else:
                    date_str = shift_date.strftime("%m/%d/%Y")
                    ci_str = ci_time.strftime("%H:%M")
                    co_str = co_time.strftime("%H:%M")
                    with st.spinner("Saving to Google Sheets…"):
                        append_work_hours(
                            date_str, ci_str, co_str, "Scheduled", break_time=break_val
                        )
                    st.success(
                        f"Scheduled: {date_str} {ci_str}→{co_str} "
                        f"| break: {break_val} | est. work: {_fmt_hm(work_h)}"
                    )
                    st.rerun()
            except Exception:
                st.error("⚠️ Invalid input. Times must be HH:MM (e.g. 07:30).")

    total_hours = period_df["Hours"].sum() if not period_df.empty else 0.0
    total_break = period_df["Break"].sum() if not period_df.empty else 0.0

    # ── Sync current rate and total hours to pay periods database ──────────
    try:
        df_pp = read_pay_periods()
        match = df_pp[df_pp["Pay Period"] == period_start]
        db_hours = None
        db_rate = None
        if not match.empty:
            db_hours = match.iloc[0]["Total Hours"]
            db_rate = match.iloc[0]["Current Rate"]

        cur_rate_rounded = round(cur_rate, 2)
        db_rate_rounded = round(float(db_rate), 2) if (db_rate is not None and pd.notna(db_rate) and db_rate != "") else None
        rate_changed = db_rate_rounded != cur_rate_rounded

        hours_changed = False
        computed_rounded = None
        if not period_df.empty:
            computed_rounded = round(total_hours, 2)
            db_rounded = round(float(db_hours), 2) if (db_hours is not None and pd.notna(db_hours) and db_hours != "") else None
            hours_changed = db_rounded != computed_rounded

        if rate_changed or hours_changed:
            upsert_pay_period_info(
                period_start,
                current_rate=cur_rate_rounded if rate_changed else None,
                total_hours=computed_rounded if hours_changed else None,
            )
    except Exception:
        pass

    # ── Pay summary metrics ────────────────────────────────────────────────
    st.markdown("---")
    metric_cols = st.columns(4)
    metric_cols[0].metric("Total Hours", f"{total_hours:.2f} hrs")
    metric_cols[1].metric("Total Break", f"{total_break:.2f} hrs")
    metric_cols[2].metric(f"Current (${cur_rate:.2f}/hr)", f"${total_hours * cur_rate:,.2f}")
    metric_cols[3].metric(f"Expected (${exp_rate:.2f}/hr)", f"${total_hours * exp_rate:,.2f}")

    # ── Shifts table ───────────────────────────────────────────────────────
    st.markdown("### Shifts This Period")

    week1_start = period_start
    week2_start = period_start + datetime.timedelta(days=7)

    if not period_df.empty:
        week1_mask = period_df["Date"].dt.date < week2_start
        week1_df = period_df[week1_mask]
        week2_df = period_df[~week1_mask]
    else:
        week1_df = pd.DataFrame()
        week2_df = pd.DataFrame()

    VIEW_COLS = [
        "_SheetRow",
        "Weekday",
        "Date",
        "Clock In",
        "Clock Out",
        "Status",
        "Work Hrs",
        "Break",
        "Shift",
    ]

    def _build_display(w_df):
        """Return a display-ready DataFrame (strings, no datetimes)."""
        d = w_df.copy().reset_index(drop=True)
        d["Weekday"] = d["Date"].dt.strftime("%A")
        d["Date"] = d["Date"].dt.strftime("%m/%d/%Y")
        d["Clock In"] = d["Clock In"].dt.strftime("%H:%M")
        d["Clock Out"] = d["Clock Out"].dt.strftime("%H:%M")
        d["Work Hrs"] = d["Hours"].apply(_fmt_hm)
        d["Break"] = d["Break"].apply(_fmt_hm)
        d["Shift"] = d["Hours"].apply(_fmt_hm)
        return d[VIEW_COLS]

    def _render_week(w_df, title, key):
        """Render one week block with summary caption and data editor."""
        if w_df.empty:
            st.markdown(f"**{title}** — *No shifts logged*")
            return None, None

        st.markdown(f"**{title}**")

        w_total = w_df["Hours"].sum()
        w_break = w_df["Break"].sum()

        parts = [f"Hours: {w_total:.2f}"]
        parts.append(f"Break: {w_break:.2f}")
        parts.append(f"Current (&#36;{cur_rate:.2f}) = &#36;{w_total * cur_rate:,.2f}")
        parts.append(f"Expected (&#36;{exp_rate:.2f}) = &#36;{w_total * exp_rate:,.2f}")
        with_break_pay = (w_total + w_break) * cur_rate
        parts.append(f"With break (&#36;{cur_rate:.2f}) = &#36;{with_break_pay:,.2f}")
        st.caption(" | ".join(parts))

        orig = _build_display(w_df)
        edited = st.data_editor(
            orig,
            key=key,
            width="stretch",
            hide_index=True,
            column_config={
                "_SheetRow": None,
                "Weekday": st.column_config.Column(disabled=True),
                "Shift": st.column_config.Column(disabled=True),
                "Work Hrs": st.column_config.TextColumn(
                    "Work Hrs",
                    help="Actual hours worked HH:MM — editable for Actual shifts",
                ),
                "Break": st.column_config.TextColumn(
                    "Break", help="Break time HH:MM — editable for Scheduled shifts"
                ),
                "Status": st.column_config.SelectboxColumn(
                    "Status", options=["Actual", "Scheduled"], required=True
                ),
            },
        )
        return orig, edited

    def _apply_availability_for_week(week_start: datetime.date, week_num: int, w_df: pd.DataFrame):
        """Append scheduled shifts from the availability template for the given week."""
        # Existing dates in this week
        existing_dates: set[datetime.date] = set()
        if not w_df.empty:
            existing_dates = set(w_df["Date"].dt.date.tolist())

        # Build weekday-name → concrete date mapping for this week
        weekday_to_date: dict[str, datetime.date] = {}
        for offset in range(7):
            d = week_start + datetime.timedelta(days=offset)
            weekday_to_date[d.strftime("%A")] = d

        added = 0
        skipped = 0
        errors: list[str] = []

        template_rows = avail_df.to_dict(orient="records")
        for entry in template_rows:
            day_name = entry.get("Day", "")
            ci = str(entry.get("Clock In", "")).strip()
            co = str(entry.get("Clock Out", "")).strip()
            br = str(entry.get("Break", "")).strip() or "01:00"

            if not ci or not co:
                continue  # off-day

            target_date = weekday_to_date.get(day_name)
            if target_date is None:
                continue

            if target_date in existing_dates:
                skipped += 1
                continue

            ci_t = _parse_time(ci)
            co_t = _parse_time(co)
            if ci_t is None or co_t is None:
                errors.append(f"{day_name}: invalid Clock In/Out — skipped")
                continue
            if _parse_hhmm(br) is None:
                errors.append(f"{day_name}: invalid Break '{br}' — skipped")
                continue

            date_str = target_date.strftime("%m/%d/%Y")
            append_work_hours(date_str, ci, co, "Scheduled", break_time=br)
            added += 1

        for e in errors:
            st.warning(e)
        if added:
            st.success(f"✅ Added {added} scheduled shift(s) for Week {week_num}.")
            if skipped:
                st.info(f"ℹ️ {skipped} day(s) already had shifts — skipped.")
            st.rerun()
        elif skipped and not errors:
            st.info("ℹ️ All days for this week already have shifts logged — nothing added.")
        else:
            st.info("ℹ️ No working days in template matched this week.")

    w1_title = (
        f"Week 1 ({week1_start.strftime('%m/%d')} – "
        f"{(week1_start + datetime.timedelta(days=6)).strftime('%m/%d')})"
    )
    w2_title = (
        f"Week 2 ({week2_start.strftime('%m/%d')} – "
        f"{(week2_start + datetime.timedelta(days=6)).strftime('%m/%d')})"
    )

    col_w1, col_w2 = st.columns(2)
    with col_w1:
        orig_w1, edited_w1 = _render_week(week1_df, w1_title, "wk1_editor")
        if st.button(
            "📅 Apply Availability",
            key="apply_avail_w1",
            help="Bulk-add scheduled shifts for Week 1 from your availability template",
        ):
            with st.spinner("Applying availability to Week 1…"):
                _apply_availability_for_week(week1_start, 1, week1_df)
    with col_w2:
        orig_w2, edited_w2 = _render_week(week2_df, w2_title, "wk2_editor")
        if st.button(
            "📅 Apply Availability",
            key="apply_avail_w2",
            help="Bulk-add scheduled shifts for Week 2 from your availability template",
        ):
            with st.spinner("Applying availability to Week 2…"):
                _apply_availability_for_week(week2_start, 2, week2_df)


    # ── Save Shift Changes ──────────────────────────────────────────────
    if st.button("💾 Save Shift Changes", key="save_shift_changes", type="primary"):
        from utils.gsheets import update_work_hours_row

        saved = 0
        pairs = []
        if orig_w1 is not None:
            pairs.append((orig_w1, edited_w1))
        if orig_w2 is not None:
            pairs.append((orig_w2, edited_w2))

        with st.spinner("Saving shift changes…"):
            for orig, edited in pairs:
                for idx in range(len(orig)):
                    old = orig.iloc[idx]
                    new = edited.iloc[idx]
                    if (
                        old["Date"] != new["Date"]
                        or old["Clock In"] != new["Clock In"]
                        or old["Clock Out"] != new["Clock Out"]
                        or old["Status"] != new["Status"]
                        or old["Work Hrs"] != new["Work Hrs"]
                        or old["Break"] != new["Break"]
                    ):
                        status_val = new["Status"]
                        if status_val == "Actual":
                            wh = new["Work Hrs"]
                            if _parse_hhmm(wh) is None:
                                st.warning(
                                    f"Row {idx+1}: Work Hrs '{wh}' is not valid HH:MM — skipped."
                                )
                                continue
                            update_work_hours_row(
                                int(old["_SheetRow"]),
                                new["Date"],
                                new["Clock In"],
                                new["Clock Out"],
                                status_val,
                                work_hours=wh,
                            )
                        else:
                            br = new["Break"]
                            if _parse_hhmm(br) is None:
                                st.warning(
                                    f"Row {idx+1}: Break '{br}' is not valid HH:MM — skipped."
                                )
                                continue
                            update_work_hours_row(
                                int(old["_SheetRow"]),
                                new["Date"],
                                new["Clock In"],
                                new["Clock Out"],
                                status_val,
                                break_time=br,
                            )
                        saved += 1

        if saved:
            st.success(f"✅ Saved {saved} shift change(s)!")
            st.rerun()
        else:
            st.info("No changes detected.")

    st.markdown("---")

    # ── Daily bar chart ─────────────────────────────────────────────────
    if not period_df.empty:
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                name="Work Hours",
                x=period_df["Date"].dt.strftime("%a %m/%d"),
                y=period_df["Hours"].round(2),
                marker_color="#6C63FF",
                text=period_df["Hours"].round(2),
                textposition="outside",
            )
        )
        fig.add_trace(
            go.Bar(
                name="Break",
                x=period_df["Date"].dt.strftime("%a %m/%d"),
                y=period_df["Break"].round(2),
                marker_color="#F5A623",
                text=period_df["Break"].round(2),
                textposition="outside",
            )
        )
        fig.update_layout(
            title="Hours Per Shift",
            barmode="stack",
            xaxis_title="Date",
            yaxis_title="Hours",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font_color="#e0e0e0",
            height=300,
            margin=dict(t=40, b=20),
        )
        st.plotly_chart(fig, width="stretch")
