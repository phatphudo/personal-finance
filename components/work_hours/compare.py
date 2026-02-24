import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.gsheets import read_settings, read_work_hours
from utils.helpers import get_all_pay_periods, get_pay_period_label


def render():
    st.markdown("## 📊 Pay Period Comparison")

    try:
        df = read_work_hours()
        settings = read_settings()
    except Exception as e:
        st.error(f"Could not load data: {e}")
        return

    if df.empty:
        st.info("No work hours data found. Log some shifts first.")
        return

    hourly_rates: dict[str, float] = {}
    rate_names = settings.get("Hourly Rate Names", [])
    rate_values = settings.get("Hourly Rate Values", [])
    for name, val in zip(rate_names, rate_values):
        try:
            hourly_rates[str(name)] = float(val)
        except (ValueError, TypeError):
            pass

    all_periods = get_all_pay_periods(df)
    period_labels = {get_pay_period_label(p): p for p in all_periods}
    all_labels = list(period_labels.keys())

    selected_labels = st.multiselect(
        "Select Pay Periods to Compare",
        all_labels,
        default=all_labels[: min(4, len(all_labels))],
        key="wh_compare_periods",
    )

    if not selected_labels:
        st.warning("Select at least one pay period above.")
        return

    selected_starts = [period_labels[lbl] for lbl in selected_labels]

    # ── Build comparison dataframe ─────────────────────────────────────────
    rows = []
    for start in selected_starts:
        end = start + pd.Timedelta(days=13)
        mask = (df["Date"].dt.date >= start) & (df["Date"].dt.date <= end)
        period_df = df[mask]
        total_hours = period_df["Hours"].sum()
        row = {
            "Period": get_pay_period_label(start),
            "Hours": round(total_hours, 2),
        }
        for name, rate in hourly_rates.items():
            row[f"${rate:.2f} ({name})"] = round(total_hours * rate, 2)
        rows.append(row)

    comparison_df = pd.DataFrame(rows)

    # ── Summary table ──────────────────────────────────────────────────────
    st.dataframe(comparison_df, width='stretch', hide_index=True)

    # ── Hours bar chart ────────────────────────────────────────────────────
    fig_hours = go.Figure(
        go.Bar(
            x=comparison_df["Period"],
            y=comparison_df["Hours"],
            marker_color="#6C63FF",
            text=comparison_df["Hours"],
            textposition="outside",
        )
    )
    fig_hours.update_layout(
        title="Total Hours Per Pay Period",
        xaxis_title="Pay Period",
        yaxis_title="Hours",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font_color="#e0e0e0",
        height=350,
        margin=dict(t=40, b=60),
        xaxis_tickangle=-30,
    )
    st.plotly_chart(fig_hours, width='stretch')

    # ── Pay comparison chart (grouped bars, one per rate) ──────────────────
    if hourly_rates:
        rate_cols = [c for c in comparison_df.columns if c.startswith("$")]
        fig_pay = go.Figure()
        colors = px.colors.qualitative.Pastel
        for i, col in enumerate(rate_cols):
            fig_pay.add_trace(
                go.Bar(
                    name=col,
                    x=comparison_df["Period"],
                    y=comparison_df[col],
                    marker_color=colors[i % len(colors)],
                    text=comparison_df[col].apply(lambda v: f"${v:,.0f}"),
                    textposition="outside",
                )
            )
        fig_pay.update_layout(
            barmode="group",
            title="Estimated Pay Per Period (by Rate)",
            xaxis_title="Pay Period",
            yaxis_title="USD",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font_color="#e0e0e0",
            height=400,
            margin=dict(t=40, b=60),
            xaxis_tickangle=-30,
        )
        st.plotly_chart(fig_pay, width='stretch')
