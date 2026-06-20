import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.settings import get_default_rates
from utils.gsheets import (
    get_period_rates,
    read_pay_periods,
    read_settings,
    read_work_hours,
)
from utils.helpers import (
    get_all_pay_periods,
    get_pay_period_label,
    get_pay_period_start,
)


def render():
    st.markdown("## 📊 Pay Period Comparison")

    try:
        df = read_work_hours()
        settings = read_settings()
        df_pp = read_pay_periods()
    except Exception as e:
        st.error(f"Could not load data: {e}")
        return

    if df.empty and df_pp.empty:
        st.info("No work hours data found. Log some shifts first.")
        return

    if df.empty:
        df = pd.DataFrame(columns=["Date", "Hours", "Break"])
        df["Date"] = pd.to_datetime(df["Date"])

    default_cur, default_exp = get_default_rates(settings)

    # Exclude the current (potentially incomplete) pay period
    current_period_start = get_pay_period_start(datetime.date.today())
    
    # Get union of periods from both Work Hours and Pay Periods database
    wh_periods = get_all_pay_periods(df) if not df.empty else []
    pp_periods = df_pp["Pay Period"].dropna().tolist() if not df_pp.empty else []
    
    all_periods_set = set(wh_periods) | set(pp_periods)
    all_periods = [p for p in sorted(all_periods_set, reverse=True) if p != current_period_start]

    if not all_periods:
        st.info("No completed pay periods to compare yet.")
        return

    period_labels = {get_pay_period_label(p): p for p in all_periods}
    all_labels = list(period_labels.keys())

    # ── Build rows helper ──────────────────────────────────────────────────
    def _build_rows(starts: list) -> pd.DataFrame:
        pp_df = read_pay_periods()
        rows = []
        for start in starts:
            end = start + pd.Timedelta(days=13)
            
            # Look up saved Total Hours from pay period database
            match = pp_df[pp_df["Pay Period"] == start]
            db_hours = None
            if not match.empty:
                val = match.iloc[0]["Total Hours"]
                if pd.notna(val) and val != "":
                    db_hours = float(val)

            # Filter work hours df for break
            mask = (df["Date"].dt.date >= start) & (df["Date"].dt.date <= end)
            pdf = df[mask]

            total_hours = db_hours if db_hours is not None else 0.0
            total_break = pdf["Break"].sum() if not pdf.empty else 0.0
            cur_rate, _ = get_period_rates(start, default_cur, default_exp)
            rows.append({
                "Period":       get_pay_period_label(start),
                "Hours":        round(total_hours, 2),
                "Break (hrs)":  round(total_break, 2),
                "Rate ($/hr)":  cur_rate,
                "Paycheck ($)": round(total_hours * cur_rate, 2),
            })
        return pd.DataFrame(rows)

    all_rows_df = _build_rows(all_periods)

    # ── All-time metrics (above selector) ─────────────────────────────────
    st.markdown("---")
    st.markdown("#### 📈 All-Time")

    col_h, col_p = st.columns(2)
    with col_h:
        st.markdown("**Hours Worked**")
        m1, m2, m3 = st.columns(3)
        m1.metric("Average", f"{all_rows_df['Hours'].mean():.2f}")
        m2.metric("Min",     f"{all_rows_df['Hours'].min():.2f}")
        m3.metric("Max",     f"{all_rows_df['Hours'].max():.2f}")
    with col_p:
        st.markdown("**Estimated Pay**")
        m4, m5, m6 = st.columns(3)
        m4.metric("Average", f"${all_rows_df['Paycheck ($)'].mean():,.2f}")
        m5.metric("Min",     f"${all_rows_df['Paycheck ($)'].min():,.2f}")
        m6.metric("Max",     f"${all_rows_df['Paycheck ($)'].max():,.2f}")

    # ── Period selector ────────────────────────────────────────────────────
    st.markdown("---")
    selected_labels = st.multiselect(
        "Select Pay Periods to Compare",
        all_labels,
        default=all_labels,
        key="wh_compare_periods",
    )

    if not selected_labels:
        st.warning("Select at least one pay period above.")
        return

    selected_starts = [period_labels[lbl] for lbl in selected_labels]
    sel_df = _build_rows(selected_starts)

    # ── Selected-period metrics ────────────────────────────────────────────
    st.markdown("#### 🔍 Selected Periods")
    col_sh, col_sp = st.columns(2)
    with col_sh:
        st.markdown("**Hours Worked**")
        s1, s2, s3 = st.columns(3)
        s1.metric("Average", f"{sel_df['Hours'].mean():.2f}")
        s2.metric("Min",     f"{sel_df['Hours'].min():.2f}")
        s3.metric("Max",     f"{sel_df['Hours'].max():.2f}")
    with col_sp:
        st.markdown("**Estimated Pay**")
        s4, s5, s6 = st.columns(3)
        s4.metric("Average", f"${sel_df['Paycheck ($)'].mean():,.2f}")
        s5.metric("Min",     f"${sel_df['Paycheck ($)'].min():,.2f}")
        s6.metric("Max",     f"${sel_df['Paycheck ($)'].max():,.2f}")

    # ── Summary table ──────────────────────────────────────────────────────
    st.markdown("---")
    st.dataframe(
        sel_df.style.format({
            "Hours":        "{:.2f}",
            "Break (hrs)":  "{:.2f}",
            "Rate ($/hr)":  "${:.2f}",
            "Paycheck ($)": "${:,.2f}",
        }),
        width="stretch",
        hide_index=True,
    )

    # ── Shared layout ──────────────────────────────────────────────────────
    _LAYOUT = dict(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font_color="#e0e0e0",
        height=360,
        margin=dict(t=50, b=70),
        xaxis_tickangle=-30,
        xaxis_title="Pay Period",
    )

    # ── Hours bar chart ────────────────────────────────────────────────────
    fig_hours = go.Figure(
        go.Bar(
            x=sel_df["Period"],
            y=sel_df["Hours"],
            marker_color="#6C63FF",
            text=sel_df["Hours"].apply(lambda v: f"{v:.1f} h"),
            textposition="outside",
        )
    )
    fig_hours.update_layout(title="Hours Worked Per Pay Period", yaxis_title="Hours", **_LAYOUT)
    st.plotly_chart(fig_hours, width="stretch")

    # ── Estimated Pay bar chart ────────────────────────────────────────────
    fig_pay = go.Figure(
        go.Bar(
            x=sel_df["Period"],
            y=sel_df["Paycheck ($)"],
            marker_color="#4CAF93",
            text=sel_df["Paycheck ($)"].apply(lambda v: f"${v:,.0f}"),
            textposition="outside",
        )
    )
    fig_pay.update_layout(title="Estimated Paycheck Per Pay Period (Current Rate)", yaxis_title="USD", **_LAYOUT)
    st.plotly_chart(fig_pay, width="stretch")
