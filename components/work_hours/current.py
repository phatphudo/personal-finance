import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils.gsheets import append_work_hours, read_settings, read_work_hours
from utils.helpers import (
    get_all_pay_periods,
    get_pay_period_label,
    get_pay_period_start,
)


def render():
    st.markdown("## 🗓️ Current Pay Period")

    try:
        df = read_work_hours()
        settings = read_settings()
    except Exception as e:
        st.error(f"Could not load data: {e}")
        return

    hourly_rates: dict[str, float] = {}
    rate_names = settings.get("Hourly Rate Names", [])
    rate_values = settings.get("Hourly Rate Values", [])
    for name, val in zip(rate_names, rate_values):
        try:
            hourly_rates[str(name)] = float(val)
        except (ValueError, TypeError):
            pass

    today = datetime.date.today()

    # ── Log new shift ──────────────────────────────────────────────────────
    st.markdown("---")
    with st.expander("➕ Log New Shift", expanded=False):
        with st.form("log_shift_form"):
            col1, col2, col3, col4 = st.columns(4)
            shift_date = col1.date_input("Date", value=today)
            clock_in = col2.text_input("Clock In (HH:MM)", value="09:00")
            clock_out = col3.text_input("Clock Out (HH:MM)", value="17:00")
            status = col4.selectbox("Status", ["Actual", "Scheduled"])
            submitted = st.form_submit_button("Save Shift", type="primary")

        if submitted:
            try:
                # Parse input string to ensure valid time
                ci_time = pd.to_datetime(clock_in).time()
                co_time = pd.to_datetime(clock_out).time()

                date_str = shift_date.strftime("%m/%d/%Y")
                ci_str = ci_time.strftime("%H:%M")
                co_str = co_time.strftime("%H:%M")

                with st.spinner("Saving to Google Sheets…"):
                    append_work_hours(date_str, ci_str, co_str, status)
                st.success(f"Shift saved: [{status}] {date_str} {ci_str} → {co_str}")
                st.rerun()
            except Exception:
                st.error(
                    "⚠️ Invalid time format. Please enter as 24-hour HH:MM (e.g., '14:30' or '08:00')."
                )

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

    total_hours = period_df["Hours"].sum() if not period_df.empty else 0.0

    # ── Pay summary metrics ────────────────────────────────────────────────
    st.markdown("---")
    cols = st.columns(1 + len(hourly_rates))
    cols[0].metric("Total Hours", f"{total_hours:.2f} hrs")
    for i, (name, rate) in enumerate(hourly_rates.items()):
        pay = total_hours * rate
        cols[i + 1].metric(f"@ ${rate:.2f}/hr ({name})", f"${pay:,.2f}")

    # ── Shifts table ───────────────────────────────────────────────────────
    st.markdown("### Shifts This Period")
    if period_df.empty:
        st.info("No shifts logged for this pay period yet.")
    else:

        def _fmt_hm(h_float):
            if pd.isna(h_float):
                return ""
            hrs = int(h_float)
            mins = int(round((h_float - hrs) * 60))
            return f"{hrs:02d} hrs {mins:02d} min"

        week1_mask = period_df["Date"].dt.date < (
            period_start + datetime.timedelta(days=7)
        )
        week1_df = period_df[week1_mask]
        week2_df = period_df[~week1_mask]

        VIEW_COLS = [
            "_SheetRow",
            "Weekday",
            "Date",
            "Clock In",
            "Clock Out",
            "Status",
            "Hours and Minutes",
            "Hours",
        ]

        def _build_display(w_df):
            """Return a display-ready DataFrame (strings, no datetimes)."""
            d = w_df.copy().reset_index(drop=True)
            d["Weekday"] = d["Date"].dt.strftime("%A")
            d["Date"] = d["Date"].dt.strftime("%m/%d/%Y")
            d["Clock In"] = d["Clock In"].dt.strftime("%H:%M")
            d["Clock Out"] = d["Clock Out"].dt.strftime("%H:%M")
            d["Hours and Minutes"] = d["Hours"].apply(_fmt_hm)
            d["Hours"] = d["Hours"].round(2)
            return d[VIEW_COLS]

        def _render_week(w_df, title, key):
            """Render one week's data editor. Returns (orig, edited) DataFrames,
            or (None, None) when the week has no data."""
            if w_df.empty:
                st.markdown(f"**{title}** — *No shifts logged*")
                return None, None

            w_total = w_df["Hours"].sum()
            st.markdown(f"**{title}**")

            metrics_parts = [f"**Hours:** {w_total:.2f}"]
            for name, rate in hourly_rates.items():
                w_pay = w_total * rate
                metrics_parts.append(f"**{name} (\${rate:.2f})** = \${w_pay:,.2f}")
            st.caption(" | ".join(metrics_parts))

            orig = _build_display(w_df)
            edited = st.data_editor(
                orig,
                key=key,
                width="stretch",
                hide_index=True,
                column_config={
                    "_SheetRow": None,
                    "Weekday": st.column_config.Column(disabled=True),
                    "Status": st.column_config.SelectboxColumn(
                        "Status", options=["Actual", "Scheduled"], required=True
                    ),
                    "Hours and Minutes": st.column_config.Column(disabled=True),
                    "Hours": st.column_config.Column(disabled=True),
                },
            )
            return orig, edited

        col_w1, col_w2 = st.columns(2)
        w1_title = f"Week 1 ({period_start.strftime('%m/%d')} – {(period_start + datetime.timedelta(days=6)).strftime('%m/%d')})"
        w2_title = f"Week 2 ({(period_start + datetime.timedelta(days=7)).strftime('%m/%d')} – {(period_start + datetime.timedelta(days=13)).strftime('%m/%d')})"

        with col_w1:
            orig_w1, edited_w1 = _render_week(week1_df, w1_title, "wk1_editor")
        with col_w2:
            orig_w2, edited_w2 = _render_week(week2_df, w2_title, "wk2_editor")

        # ── Save Shift Changes button ───────────────────────────────────────
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
                        ):
                            update_work_hours_row(
                                int(old["_SheetRow"]),
                                new["Date"],
                                new["Clock In"],
                                new["Clock Out"],
                                new["Status"],
                            )
                            saved += 1

            if saved:
                st.success(f"✅ Saved {saved} shift change(s)!")
                st.rerun()
            else:
                st.info("No changes detected.")

        st.markdown("---")
        # Daily bar chart
        fig = go.Figure(
            go.Bar(
                x=period_df["Date"].dt.strftime("%a %m/%d"),
                y=period_df["Hours"].round(2),
                marker_color="#6C63FF",
                text=period_df["Hours"].round(2),
                textposition="outside",
            )
        )
        fig.update_layout(
            title="Hours Per Shift",
            xaxis_title="Date",
            yaxis_title="Hours",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font_color="#e0e0e0",
            height=300,
            margin=dict(t=40, b=20),
        )
        st.plotly_chart(fig, width="stretch")
