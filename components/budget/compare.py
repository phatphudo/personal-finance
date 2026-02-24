import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.gsheets import read_settings, read_starting_balances, read_transactions
from utils.helpers import compute_monthly_balance, get_all_months, month_label


def render():
    st.markdown("## 📅 Monthly Comparison")

    try:
        tx_df = read_transactions()
        sb_df = read_starting_balances()
        settings = read_settings()
    except Exception as e:
        st.error(f"Could not load data: {e}")
        return

    if tx_df.empty:
        st.info("No transaction data found yet.")
        return

    cash_sources = settings.get("Cash Sources", [])
    bank_accounts = settings.get("Bank Accounts", [])
    credit_cards = settings.get("Credit Cards", [])
    all_accounts = cash_sources + bank_accounts + credit_cards

    all_months = get_all_months(tx_df)
    month_options = {month_label(m): m for m in all_months}

    selected_labels = st.multiselect(
        "Select Months to Compare",
        list(month_options.keys()),
        default=list(month_options.keys())[: min(6, len(month_options))],
        key="budget_compare_months",
    )

    if not selected_labels:
        st.warning("Select at least one month.")
        return

    selected_months = [month_options[lbl] for lbl in selected_labels]

    # ── 1. Income vs Expense trend ─────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Income vs. Expenses")
    trend_rows = []
    for m in selected_months:
        mask = (tx_df["Date"].dt.year == m.year) & (tx_df["Date"].dt.month == m.month)
        mdf = tx_df[mask]
        inc = mdf[mdf["Type"] == "Income"]["Amount"].sum()
        exp = mdf[mdf["Type"] == "Expense"]["Amount"].sum()
        trend_rows.append(
            {"Month": month_label(m), "Income": inc, "Expenses": exp, "Net": inc - exp}
        )

    trend_df = pd.DataFrame(trend_rows)
    fig_trend = go.Figure()
    fig_trend.add_trace(
        go.Bar(
            name="Income",
            x=trend_df["Month"],
            y=trend_df["Income"],
            marker_color="#00C49A",
            text=trend_df["Income"].map("${:,.0f}".format),
            textposition="outside",
        )
    )
    fig_trend.add_trace(
        go.Bar(
            name="Expenses",
            x=trend_df["Month"],
            y=trend_df["Expenses"],
            marker_color="#FF6B6B",
            text=trend_df["Expenses"].map("${:,.0f}".format),
            textposition="outside",
        )
    )
    fig_trend.add_trace(
        go.Scatter(
            name="Net",
            x=trend_df["Month"],
            y=trend_df["Net"],
            mode="lines+markers+text",
            text=trend_df["Net"].map("${:,.0f}".format),
            textposition="top center",
            line=dict(color="#6C63FF", width=2),
            marker=dict(size=8),
        )
    )
    fig_trend.update_layout(
        barmode="group",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font_color="#e0e0e0",
        height=420,
        margin=dict(t=20, b=60),
        xaxis_tickangle=-30,
    )
    st.plotly_chart(fig_trend, width='stretch')

    # ── 2. Spending by category heatmap / grouped bars ─────────────────────
    st.markdown("---")
    st.markdown("#### Spending by Category")
    cat_rows = []
    for m in selected_months:
        mask = (
            (tx_df["Date"].dt.year == m.year)
            & (tx_df["Date"].dt.month == m.month)
            & (tx_df["Type"] == "Expense")
        )
        mdf = tx_df[mask]
        by_cat = mdf.groupby("Category")["Amount"].sum()
        row = {"Month": month_label(m)}
        row.update(by_cat.to_dict())
        cat_rows.append(row)

    cat_df = pd.DataFrame(cat_rows).fillna(0).set_index("Month")

    if not cat_df.empty:
        fig_cat = px.bar(
            cat_df.reset_index().melt(
                id_vars="Month", var_name="Category", value_name="Amount"
            ),
            x="Month",
            y="Amount",
            color="Category",
            barmode="stack",
            color_discrete_sequence=px.colors.qualitative.Pastel,
        )
        fig_cat.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font_color="#e0e0e0",
            height=420,
            margin=dict(t=20, b=60),
            xaxis_tickangle=-30,
        )
        st.plotly_chart(fig_cat, width='stretch')

    # ── 3. Account ending balances over time ───────────────────────────────
    st.markdown("---")
    st.markdown("#### Account Balance Trend")
    account_filter = st.multiselect(
        "Accounts to track",
        all_accounts,
        default=all_accounts[: min(4, len(all_accounts))],
        key="compare_accounts",
    )

    if account_filter:
        bal_rows = []
        for m in selected_months:
            row = {"Month": month_label(m)}
            for acct in account_filter:
                b = compute_monthly_balance(tx_df, sb_df, acct, m.year, m.month)
                row[acct] = round(b["ending"], 2)
            bal_rows.append(row)

        bal_df = pd.DataFrame(bal_rows)
        fig_bal = go.Figure()
        colors = px.colors.qualitative.Pastel
        for i, acct in enumerate(account_filter):
            fig_bal.add_trace(
                go.Scatter(
                    name=acct,
                    x=bal_df["Month"],
                    y=bal_df[acct],
                    mode="lines+markers+text",
                    text=bal_df[acct].map("${:,.0f}".format),
                    textposition="top center",
                    line=dict(color=colors[i % len(colors)], width=2),
                    marker=dict(size=8),
                )
            )
        fig_bal.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font_color="#e0e0e0",
            height=400,
            margin=dict(t=20, b=60),
            xaxis_tickangle=-30,
        )
        st.plotly_chart(fig_bal, width='stretch')

    # ── 4. Raw summary table ───────────────────────────────────────────────
    st.markdown("---")
    with st.expander("📋 Summary Table"):
        fmt = "${:,.2f}".format
        display = trend_df.copy()
        for col in ["Income", "Expenses", "Net"]:
            display[col] = display[col].map(fmt)
        st.dataframe(display, width='stretch', hide_index=True)
