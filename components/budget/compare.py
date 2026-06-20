import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.gsheets import (
    read_cash_counts,
    read_cash_in,
    read_cash_out,
    read_credit_tx,
    read_debit_in,
    read_debit_out,
    read_settings,
)
from utils.helpers import month_label


def render():
    st.markdown("## 📅 Monthly Comparison")

    try:
        ci_df = read_cash_in()
        co_df = read_cash_out()
        di_df = read_debit_in()
        do_df = read_debit_out()
        cred_df = read_credit_tx()
        cc_df = read_cash_counts()
        settings = read_settings()
    except Exception as e:
        st.error(f"Could not load data: {e}")
        return

    _month_set = set()
    for _df in (ci_df, co_df, di_df, do_df, cred_df, cc_df):
        if not _df.empty and "Month" in _df.columns:
            for m in _df["Month"].dropna():
                _month_set.add(datetime.date(m.year, m.month, 1))

    all_months = sorted(_month_set, reverse=True)
    if not all_months:
        st.info("No transaction data found yet.")
        return

    cash_sources = settings.get("Cash Sources", [])
    bank_accounts = settings.get("Bank Accounts", [])

    month_options = {month_label(m): m for m in all_months}

    selected_labels = st.multiselect(
        "Select Months to Compare",
        list(month_options.keys()),
        default=list(month_options.keys())[: min(12, len(month_options))],
        key="budget_compare_months",
    )

    if not selected_labels:
        st.warning("Select at least one month.")
        return

    selected_months = [month_options[lbl] for lbl in selected_labels]

    # Pre-process frames
    _EXCLUDE_SPENDING = ["Deposit to Debit", "Add to Vault", "Credit Card Payment"]

    def _get_month_mask(df, m):
        if df is None or df.empty or "Month" not in df.columns:
            return pd.Series(False, index=df.index if df is not None else [])
        return (df["Month"].dt.year == m.year) & (df["Month"].dt.month == m.month)

    # ── 1. Income vs Expense trend ─────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Income vs. Expenses")
    trend_rows = []

    # Pre-clean the DFs
    co_clean = (
        co_df[~co_df["Category"].isin(_EXCLUDE_SPENDING)].copy()
        if not co_df.empty and "Category" in co_df.columns
        else pd.DataFrame()
    )
    do_clean = (
        do_df[~do_df["Category"].isin(_EXCLUDE_SPENDING)].copy()
        if not do_df.empty and "Category" in do_df.columns
        else pd.DataFrame()
    )
    cred_clean = (
        cred_df[~cred_df["Category"].isin(_EXCLUDE_SPENDING)].copy()
        if not cred_df.empty and "Category" in cred_df.columns
        else pd.DataFrame()
    )

    # Cash In: all rows are real income — no category filter needed
    ci_clean = ci_df.copy() if not ci_df.empty else pd.DataFrame()

    # Debit In: exclude auto-generated cash-transfer rows (description starts with "From cash")
    # This matches the logic in current_debit.py exactly.
    di_clean = (
        di_df[~di_df["Description"].str.startswith("From cash", na=False)].copy()
        if not di_df.empty and "Description" in di_df.columns
        else pd.DataFrame()
    )

    cat_rows = []

    for m in selected_months:
        # Income
        inc = 0.0
        if not ci_clean.empty:
            inc += ci_clean[_get_month_mask(ci_clean, m)]["Amount"].sum()
        if not di_clean.empty:
            inc += di_clean[_get_month_mask(di_clean, m)]["Amount"].sum()

        # Expenses
        exp = 0.0
        month_exp_dfs = []
        if not co_clean.empty:
            month_exp_dfs.append(co_clean[_get_month_mask(co_clean, m)])
        if not do_clean.empty:
            month_exp_dfs.append(do_clean[_get_month_mask(do_clean, m)])
        if not cred_clean.empty:
            month_exp_dfs.append(cred_clean[_get_month_mask(cred_clean, m)])

        all_month_exp = (
            pd.concat(month_exp_dfs, ignore_index=True)
            if month_exp_dfs
            else pd.DataFrame()
        )
        if not all_month_exp.empty:
            exp += all_month_exp["Amount"].sum()

            # Group for category heatmap
            by_cat = all_month_exp.groupby("Category")["Amount"].sum()
            row_cat = {"Month": month_label(m)}
            row_cat.update(by_cat.to_dict())
            cat_rows.append(row_cat)

        # Networth = sum of all account balances (cash counts) for the month
        nw = 0.0
        if not cc_df.empty:
            month_cc = cc_df[_get_month_mask(cc_df, m)]
            if not month_cc.empty:
                nw = month_cc["Amount"].sum()

        trend_rows.append(
            {
                "Month": month_label(m),
                "Income": inc,
                "Expenses": exp,
                "Net": inc - exp,
                "Networth": nw,
            }
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
        go.Bar(
            name="Networth",
            x=trend_df["Month"],
            y=trend_df["Networth"],
            marker_color="#F5A623",
            text=trend_df["Networth"].map("${:,.0f}".format),
            textposition="outside",
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
    st.plotly_chart(fig_trend, width="stretch")

    # ── 2. Spending by category heatmap / grouped bars ─────────────────────
    st.markdown("---")
    st.markdown("#### Spending by Category")
    cat_df = pd.DataFrame(cat_rows).fillna(0)
    if not cat_df.empty and "Month" in cat_df.columns:
        cat_df = cat_df.set_index("Month")
    else:
        cat_df = pd.DataFrame()

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
        st.plotly_chart(fig_cat, width="stretch")

    # ── 3. Account ending balances over time ───────────────────────────────
    st.markdown("---")
    st.markdown("#### Real-world Balances (Cash Counts)")

    all_accounts = cash_sources + bank_accounts

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
            if not cc_df.empty:
                month_counts = cc_df[_get_month_mask(cc_df, m)]
            else:
                month_counts = pd.DataFrame()

            for acct in account_filter:
                if not month_counts.empty:
                    acct_counts = month_counts[month_counts["Source"] == acct]
                    row[acct] = (
                        acct_counts["Amount"].sum() if not acct_counts.empty else 0.0
                    )
                else:
                    row[acct] = 0.0
            bal_rows.append(row)

        bal_df = pd.DataFrame(bal_rows)
        if not bal_df.empty:
            fig_bal = go.Figure()
            colors = px.colors.qualitative.Pastel
            for i, acct in enumerate(account_filter):
                if acct in bal_df.columns:
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
            st.plotly_chart(fig_bal, width="stretch")

    # ── 4. Raw summary table ───────────────────────────────────────────────
    st.markdown("---")
    with st.expander("📋 Trend Summary Table"):
        fmt = "${:,.2f}".format
        if not trend_df.empty:
            display = trend_df.copy()
            for col in ["Income", "Expenses", "Net", "Networth"]:
                display[col] = display[col].map(fmt)
            st.dataframe(display, width="stretch", hide_index=True)

    with st.expander("📋 Category Summary Table"):
        if not cat_df.empty:
            display_cat = cat_df.copy()
            for col in display_cat.columns:
                display_cat[col] = display_cat[col].map(fmt)
            st.dataframe(display_cat.reset_index(), width="stretch", hide_index=True)
