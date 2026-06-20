"""
Yearly Overview Dashboard

Replaces the old "Monthly Comparison" view. Shows an auto-detected fiscal
year (Aug → Jul) with Begin/End month selectors defaulting to the current
fiscal year.

Key decisions vs. old compare.py
  - Net worth: cash_counts total MINUS credit balance for that month
  - KPIs: Total Income, Total Spending, Net Savings, Total Paychecks, Peak NW
  - Fiscal year: auto-shifts each year (last Aug → next Jul)
"""

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

# ── Constants ─────────────────────────────────────────────────────────────────
_EXCLUDE_SPENDING = [
    "Deposit to Debit",
    "Add to Vault",
    "Credit Card Payment",
    "Withdrawal from Debit",
]
_EXCLUDE_INCOME = ["Deposit", "Withdrawal", "Transfer"]
_DEPOSIT_PREFIX = "From cash"
_PAYCHECK_CATEGORY = "paycheck"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fiscal_year_bounds(today: datetime.date) -> tuple[datetime.date, datetime.date]:
    """Return (start, end) of the current fiscal year (Aug 1 → Jul 1 next yr)."""
    if today.month >= 8:
        return datetime.date(today.year, 8, 1), datetime.date(today.year + 1, 7, 1)
    return datetime.date(today.year - 1, 8, 1), datetime.date(today.year, 7, 1)


def _month_mask(df: pd.DataFrame, m: datetime.date) -> pd.Series:
    if df is None or df.empty or "Month" not in df.columns:
        return pd.Series(False, index=[] if df is None else df.index)
    return (df["Month"].dt.year == m.year) & (df["Month"].dt.month == m.month)


def _closest_available(
    target: datetime.date,
    available: list[datetime.date],
    prefer_before: bool = True,
) -> datetime.date:
    if target in available:
        return target
    if prefer_before:
        candidates = [m for m in available if m <= target]
        return max(candidates) if candidates else available[0]
    candidates = [m for m in available if m >= target]
    return min(candidates) if candidates else available[-1]


# ── Main render ───────────────────────────────────────────────────────────────

def render():
    st.markdown("## 📅 Yearly Overview")

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

    # ── Collect all months that have any data ─────────────────────────────────
    _month_set: set[datetime.date] = set()
    for _df in (ci_df, co_df, di_df, do_df, cred_df, cc_df):
        if not _df.empty and "Month" in _df.columns:
            for m in _df["Month"].dropna():
                _month_set.add(datetime.date(m.year, m.month, 1))

    all_months = sorted(_month_set)
    if not all_months:
        st.info("No transaction data found yet.")
        return

    cash_sources = settings.get("Cash Sources", [])
    bank_accounts = settings.get("Bank Accounts", [])

    today = datetime.date.today()
    fy_start, fy_end = _fiscal_year_bounds(today)

    default_begin = _closest_available(fy_start, all_months, prefer_before=False)
    default_end = _closest_available(fy_end, all_months, prefer_before=True)

    month_options: dict[str, datetime.date] = {month_label(m): m for m in all_months}
    all_labels = list(month_options.keys())

    # ── Date range selectors ──────────────────────────────────────────────────
    sel_col1, sel_col2 = st.columns(2)
    with sel_col1:
        begin_label = st.selectbox(
            "Begin Month",
            all_labels,
            index=all_labels.index(month_label(default_begin)),
            key="yearly_begin_month",
        )
    with sel_col2:
        end_label = st.selectbox(
            "End Month",
            all_labels,
            index=all_labels.index(month_label(default_end)),
            key="yearly_end_month",
        )

    begin_month = month_options[begin_label]
    end_month = month_options[end_label]

    if begin_month > end_month:
        st.warning("⚠️ Begin Month must be on or before End Month.")
        return

    selected_months = [m for m in all_months if begin_month <= m <= end_month]
    if not selected_months:
        st.warning("No data in selected range.")
        return

    # ── Period header ─────────────────────────────────────────────────────────
    current_month = datetime.date(today.year, today.month, 1)
    months_tracked = sum(1 for m in selected_months if m <= current_month)
    months_total = len(selected_months)

    st.markdown(
        f"**{begin_label} → {end_label}** &nbsp;·&nbsp; "
        f"{months_tracked} of {months_total} months tracked"
        + (f" &nbsp;·&nbsp; *{month_label(current_month)} still in progress*" if current_month in selected_months else "")
    )

    # ── Pre-clean DataFrames ──────────────────────────────────────────────────
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

    # ci_clean / di_clean → Total Income (excludes Transfer + internal movements)
    # ci_received / di_received → Total Received (includes Transfer, excludes only internal movements)

    # Cash In for income: exclude Withdrawal (internal debit→cash) and Transfer
    ci_clean = ci_df.copy() if not ci_df.empty else pd.DataFrame()
    if not ci_clean.empty and "Category" in ci_clean.columns:
        ci_clean = ci_clean[~ci_clean["Category"].isin(_EXCLUDE_INCOME)].copy()

    # Cash In for received: exclude only Withdrawal (internal debit→cash); Transfer stays in
    ci_received = ci_df.copy() if not ci_df.empty else pd.DataFrame()
    if not ci_received.empty and "Category" in ci_received.columns:
        ci_received = ci_received[ci_received["Category"] != "Withdrawal"].copy()

    # Debit In for income: exclude "From cash" deposits AND Transfer
    di_clean = (
        di_df[~di_df["Description"].str.startswith(_DEPOSIT_PREFIX, na=False)].copy()
        if not di_df.empty and "Description" in di_df.columns
        else pd.DataFrame()
    )
    if not di_clean.empty and "Category" in di_clean.columns:
        di_clean = di_clean[~di_clean["Category"].isin(_EXCLUDE_INCOME)].copy()

    # Debit In for received: exclude only "From cash" deposits; Transfer stays in
    di_received = (
        di_df[~di_df["Description"].str.startswith(_DEPOSIT_PREFIX, na=False)].copy()
        if not di_df.empty and "Description" in di_df.columns
        else pd.DataFrame()
    )

    # ── Aggregate per selected month ──────────────────────────────────────────
    trend_rows: list[dict] = []
    cat_rows: list[dict] = []

    for m in selected_months:
        # Income
        inc = 0.0
        if not ci_clean.empty:
            inc += ci_clean[_month_mask(ci_clean, m)]["Amount"].sum()
        if not di_clean.empty:
            inc += di_clean[_month_mask(di_clean, m)]["Amount"].sum()

        # Expenses
        month_exp_dfs = []
        if not co_clean.empty:
            month_exp_dfs.append(co_clean[_month_mask(co_clean, m)])
        if not do_clean.empty:
            month_exp_dfs.append(do_clean[_month_mask(do_clean, m)])
        if not cred_clean.empty:
            month_exp_dfs.append(cred_clean[_month_mask(cred_clean, m)])

        all_month_exp = (
            pd.concat(month_exp_dfs, ignore_index=True) if month_exp_dfs else pd.DataFrame()
        )
        exp = all_month_exp["Amount"].sum() if not all_month_exp.empty else 0.0

        if not all_month_exp.empty and "Category" in all_month_exp.columns:
            by_cat = all_month_exp.groupby("Category")["Amount"].sum()
            row_cat: dict = {"Month": month_label(m)}
            row_cat.update(by_cat.to_dict())
            cat_rows.append(row_cat)

        # Net worth: cash counts total − credit balance for month
        cash_total = 0.0
        if not cc_df.empty:
            month_cc = cc_df[_month_mask(cc_df, m)]
            cash_total = month_cc["Amount"].sum() if not month_cc.empty else 0.0

        cr_bal = 0.0
        if not cred_df.empty:
            month_cr = cred_df[_month_mask(cred_df, m)]
            cr_bal = month_cr["Amount"].sum() if not month_cr.empty else 0.0

        nw = cash_total - cr_bal

        trend_rows.append({
            "Month": month_label(m),
            "Income": inc,
            "Expenses": exp,
            "Net": inc - exp,
            "Networth": nw,
        })

    trend_df = pd.DataFrame(trend_rows)

    # ── KPI metrics ───────────────────────────────────────────────────────────
    st.markdown("---")
    total_income = trend_df["Income"].sum()
    total_spending = trend_df["Expenses"].sum()
    net_savings = total_income - total_spending

    # Total Received: all real inflows in selected range (incl. Transfer, excl. internal movements)
    selected_set = set(selected_months)
    def _in_range(df):
        return df["Month"].apply(
            lambda x: datetime.date(x.year, x.month, 1) in selected_set if pd.notna(x) else False
        )

    total_received = 0.0
    if not ci_received.empty and "Month" in ci_received.columns:
        total_received += ci_received[_in_range(ci_received)]["Amount"].sum()
    if not di_received.empty and "Month" in di_received.columns:
        total_received += di_received[_in_range(di_received)]["Amount"].sum()

    # Current Networth: most recent selected month that has actual cash count data
    current_nw = 0.0
    for _m in reversed(selected_months):
        if not cc_df.empty:
            _month_cc = cc_df[_month_mask(cc_df, _m)]
            if not _month_cc.empty:
                _cash_total = _month_cc["Amount"].sum()
                _cr_bal = 0.0
                if not cred_df.empty:
                    _month_cr = cred_df[_month_mask(cred_df, _m)]
                    _cr_bal = _month_cr["Amount"].sum() if not _month_cr.empty else 0.0
                current_nw = _cash_total - _cr_bal
                break

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric(
        "💵 Total Received",
        f"${total_received:,.2f}",
        help="All real inflows (incl. family transfers) — excludes internal movements like Deposit to Debit & Withdrawal",
    )
    k2.metric(
        "💸 Total Spending",
        f"${total_spending:,.2f}",
        help="All real spending — excludes internal transfers (Deposit to Debit, CC Payment, Withdrawal, Vault)",
    )
    k3.metric(
        "💰 Total Income",
        f"${total_income:,.2f}",
        help="Earned income only — excludes Transfer (family wire) and internal movements",
    )
    net_delta = f"+${net_savings:,.2f}" if net_savings >= 0 else f"-${abs(net_savings):,.2f}"
    k4.metric(
        "📈 Net Savings",
        f"${net_savings:,.2f}",
        delta=net_delta,
        delta_color="normal" if net_savings >= 0 else "inverse",
        help="Total Income − Total Spending",
    )
    k5.metric(
        "🏦 Current Networth",
        f"${current_nw:,.2f}",
        help="Most recent month's cash + bank balances minus outstanding credit card balance",
    )


    # ── 0. Income vs. Expenses ────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 📊 Income vs. Expenses")


    fig_trend = go.Figure()
    fig_trend.add_trace(go.Bar(
        name="Income",
        x=trend_df["Month"],
        y=trend_df["Income"],
        marker_color="#00C49A",
        text=trend_df["Income"].map("${:,.0f}".format),
        textposition="outside",
    ))
    fig_trend.add_trace(go.Bar(
        name="Expenses",
        x=trend_df["Month"],
        y=trend_df["Expenses"],
        marker_color="#FF6B6B",
        text=trend_df["Expenses"].map("${:,.0f}".format),
        textposition="outside",
    ))
    fig_trend.add_trace(go.Scatter(
        name="Net Flow",
        x=trend_df["Month"],
        y=trend_df["Net"],
        mode="lines+markers",
        line=dict(color="#F5A623", width=2, dash="dot"),
        marker=dict(size=8),
    ))
    fig_trend.update_layout(
        barmode="group",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font_color="#e0e0e0",
        height=440,
        margin=dict(t=20, b=60),
        xaxis_tickangle=-30,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig_trend, width="stretch")

    # ── 1. Net Worth Progression ──────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 💰 Net Worth Progression")

    all_accounts = cash_sources + bank_accounts
    account_filter = st.multiselect(
        "Accounts to show",
        all_accounts,
        default=all_accounts[: min(4, len(all_accounts))],
        key="yearly_accounts",
    )

    nw_rows: list[dict] = []
    for m in selected_months:
        row: dict = {"Month": month_label(m)}
        month_cc_data = cc_df[_month_mask(cc_df, m)] if not cc_df.empty else pd.DataFrame()

        total_balance = 0.0
        for acct in account_filter:
            val = 0.0
            if not month_cc_data.empty and "Source" in month_cc_data.columns:
                acct_rows = month_cc_data[month_cc_data["Source"] == acct]
                val = acct_rows["Amount"].sum() if not acct_rows.empty else 0.0
            row[acct] = val
            total_balance += val

        cr_bal = 0.0
        if not cred_df.empty:
            month_cr = cred_df[_month_mask(cred_df, m)]
            cr_bal = month_cr["Amount"].sum() if not month_cr.empty else 0.0

        row["Net Worth"] = total_balance - cr_bal
        nw_rows.append(row)

    nw_df = pd.DataFrame(nw_rows)
    if not nw_df.empty:
        fig_nw = go.Figure()
        colors = px.colors.qualitative.Pastel
        for i, acct in enumerate(account_filter):
            if acct in nw_df.columns:
                fig_nw.add_trace(go.Scatter(
                    name=acct,
                    x=nw_df["Month"],
                    y=nw_df[acct],
                    mode="lines+markers",
                    line=dict(color=colors[i % len(colors)], width=2),
                    marker=dict(size=7),
                ))
        fig_nw.add_trace(go.Scatter(
            name="Net Worth",
            x=nw_df["Month"],
            y=nw_df["Net Worth"],
            mode="lines+markers+text",
            text=nw_df["Net Worth"].map("${:,.0f}".format),
            textposition="top center",
            line=dict(color="#F5A623", width=3),
            marker=dict(size=9, symbol="diamond"),
        ))
        fig_nw.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font_color="#e0e0e0",
            height=400,
            margin=dict(t=30, b=60),
            xaxis_tickangle=-30,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_nw, width="stretch")

    # ── 2. Total Received Breakdown ───────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 💵 Total Received Breakdown")

    # Collect all received rows with category + type for the selected range
    recv_rows: list[dict] = []
    for _df, _type in [(ci_received, "Cash"), (di_received, "Debit")]:
        if not _df.empty and "Category" in _df.columns and "Month" in _df.columns:
            _in_rng = _df["Month"].apply(
                lambda x: datetime.date(x.year, x.month, 1) in selected_set if pd.notna(x) else False
            )
            for _, row in _df[_in_rng].iterrows():
                recv_rows.append({
                    "Month": month_label(datetime.date(row["Month"].year, row["Month"].month, 1)),
                    "Category": row["Category"],
                    "Type": _type,
                    "Source": "Transfer" if str(row["Category"]).strip().lower() == "transfer" else "Earned",
                    "Amount": row["Amount"],
                })

    if recv_rows:
        recv_all = pd.DataFrame(recv_rows)

        # Row 1: monthly stacked bar + full-period category donut
        c1, c2 = st.columns([2, 1])
        with c1:
            recv_by_month_cat = (
                recv_all.groupby(["Month", "Category"])["Amount"]
                .sum()
                .reset_index()
            )
            # Preserve month order
            month_order = [month_label(m) for m in selected_months]
            recv_by_month_cat["Month"] = pd.Categorical(
                recv_by_month_cat["Month"], categories=month_order, ordered=True
            )
            recv_by_month_cat = recv_by_month_cat.sort_values("Month")
            fig_recv_bar = px.bar(
                recv_by_month_cat,
                x="Month",
                y="Amount",
                color="Category",
                barmode="stack",
                title="Monthly Breakdown by Category",
                color_discrete_sequence=px.colors.qualitative.Pastel,
            )
            fig_recv_bar.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#e0e0e0",
                height=380,
                margin=dict(t=40, b=60),
                xaxis_tickangle=-30,
            )
            st.plotly_chart(fig_recv_bar, width="stretch")
        with c2:
            by_cat_total = recv_all.groupby("Category")["Amount"].sum().sort_values(ascending=False)
            fig_recv_donut = px.pie(
                names=by_cat_total.index,
                values=by_cat_total.values,
                hole=0.45,
                title="Full Period by Category",
                color_discrete_sequence=px.colors.qualitative.Pastel,
            )
            fig_recv_donut.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#e0e0e0",
                margin=dict(t=40, b=20),
            )
            st.plotly_chart(fig_recv_donut, width="stretch")

        # Row 2: payment type (Cash vs Debit) + earned vs transfer split
        c3, c4 = st.columns(2)
        with c3:
            by_type = recv_all.groupby("Type")["Amount"].sum().reset_index()
            fig_recv_type = px.pie(
                by_type,
                names="Type",
                values="Amount",
                hole=0.45,
                title="Cash vs. Debit",
                color_discrete_sequence=px.colors.qualitative.Pastel,
            )
            fig_recv_type.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#e0e0e0",
                margin=dict(t=40, b=20),
            )
            st.plotly_chart(fig_recv_type, width="stretch")
        with c4:
            by_source = recv_all.groupby("Source")["Amount"].sum().reset_index()
            fig_recv_source = px.pie(
                by_source,
                names="Source",
                values="Amount",
                hole=0.45,
                title="Earned Income vs. Family Transfers",
                color_discrete_sequence=["#00C49A", "#a855f7"],
            )
            fig_recv_source.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#e0e0e0",
                margin=dict(t=40, b=20),
            )
            st.plotly_chart(fig_recv_source, width="stretch")
    else:
        st.info("No received data in selected range.")

    # ── 3. Income Breakdown ───────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 📈 Income Breakdown")

    inc_rows: list[dict] = []
    selected_set = set(selected_months)
    for _df, _type in [(ci_clean, "Cash"), (di_clean, "Debit")]:
        if not _df.empty and "Category" in _df.columns and "Month" in _df.columns:
            in_range = _df["Month"].apply(
                lambda x: datetime.date(x.year, x.month, 1) in selected_set if pd.notna(x) else False
            )
            for _, row in _df[in_range].iterrows():
                inc_rows.append({"Category": row["Category"], "Type": _type, "Amount": row["Amount"]})

    if inc_rows:
        inc_all = pd.DataFrame(inc_rows)
        c1, c2 = st.columns(2)
        with c1:
            by_cat = inc_all.groupby("Category")["Amount"].sum().sort_values(ascending=False).reset_index()
            fig_inc_cat = px.pie(
                by_cat,
                names="Category",
                values="Amount",
                hole=0.45,
                title="By Category",
                color_discrete_sequence=px.colors.qualitative.Pastel,
            )
            fig_inc_cat.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#e0e0e0",
                margin=dict(t=40, b=20),
            )
            st.plotly_chart(fig_inc_cat, width="stretch")
        with c2:
            by_type = inc_all.groupby("Type")["Amount"].sum().reset_index()
            fig_inc_type = px.pie(
                by_type,
                names="Type",
                values="Amount",
                hole=0.45,
                title="By Payment Type (Cash vs. Debit)",
                color_discrete_sequence=px.colors.qualitative.Pastel,
            )
            fig_inc_type.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#e0e0e0",
                margin=dict(t=40, b=20),
            )
            st.plotly_chart(fig_inc_type, width="stretch")
    else:
        st.info("No income data in selected range.")

    # ── 4. Paycheck Breakdown ─────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 🏦 Paycheck Breakdown")

    pay_rows: list[dict] = []
    if not ci_df.empty and "Category" in ci_df.columns and "Month" in ci_df.columns:
        pay_mask = ci_df["Category"].str.strip().str.lower() == _PAYCHECK_CATEGORY
        in_range_mask = ci_df["Month"].apply(
            lambda x: datetime.date(x.year, x.month, 1) in selected_set if pd.notna(x) else False
        )
        pay_df_filtered = ci_df[pay_mask & in_range_mask].copy()
        if not pay_df_filtered.empty:
            for _, row in pay_df_filtered.iterrows():
                pay_rows.append({
                    "Month": month_label(datetime.date(row["Month"].year, row["Month"].month, 1)),
                    "Source": str(row.get("Description", "Paycheck")).strip() or "Paycheck",
                    "Amount": row["Amount"],
                })

    if pay_rows:
        pay_all = pd.DataFrame(pay_rows)
        total_pay = pay_all["Amount"].sum()
        num_pay = len(pay_all)
        months_with_pay = pay_all["Month"].nunique()
        avg_per_month = total_pay / months_with_pay if months_with_pay else 0.0

        # KPIs
        pk1, pk2, pk3 = st.columns(3)
        pk1.metric("Total Paychecks", f"${total_pay:,.2f}")
        pk2.metric("# of Paychecks", str(num_pay))
        pk3.metric("Avg per Month", f"${avg_per_month:,.2f}")

        st.write("")

        # Charts: monthly bar + by-source donut
        pc1, pc2 = st.columns([2, 1])
        with pc1:
            pay_monthly = (
                pay_all.groupby(["Month", "Source"])["Amount"]
                .sum()
                .reset_index()
            )
            month_order = [month_label(m) for m in selected_months]
            pay_monthly["Month"] = pd.Categorical(
                pay_monthly["Month"], categories=month_order, ordered=True
            )
            pay_monthly = pay_monthly.sort_values("Month")
            fig_pay_bar = px.bar(
                pay_monthly,
                x="Month",
                y="Amount",
                color="Source",
                barmode="stack",
                title="Monthly Paychecks by Source",
                text_auto="$.0f",
                color_discrete_sequence=px.colors.qualitative.Pastel,
            )
            fig_pay_bar.update_traces(textposition="outside")
            fig_pay_bar.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#e0e0e0",
                height=380,
                margin=dict(t=40, b=60),
                xaxis_tickangle=-30,
            )
            st.plotly_chart(fig_pay_bar, width="stretch")
        with pc2:
            by_source = pay_all.groupby("Source")["Amount"].sum().sort_values(ascending=False)
            fig_pay_donut = px.pie(
                names=by_source.index,
                values=by_source.values,
                hole=0.45,
                title="Full Period by Source",
                color_discrete_sequence=px.colors.qualitative.Pastel,
            )
            fig_pay_donut.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#e0e0e0",
                margin=dict(t=40, b=20),
            )
            st.plotly_chart(fig_pay_donut, width="stretch")
    else:
        st.info("No paycheck entries found (Cash In, Category = 'Paycheck') in selected range.")

    # ── 5. Spending Breakdown ─────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 💸 Spending Breakdown")

    cat_df = pd.DataFrame(cat_rows).fillna(0)
    if not cat_df.empty and "Month" in cat_df.columns:
        cat_df = cat_df.set_index("Month")

    if not cat_df.empty:
        c1, c2 = st.columns([2, 1])
        with c1:
            fig_cat = px.bar(
                cat_df.reset_index().melt(id_vars="Month", var_name="Category", value_name="Amount"),
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
                height=400,
                margin=dict(t=20, b=60),
                xaxis_tickangle=-30,
            )
            st.plotly_chart(fig_cat, width="stretch")
        with c2:
            yearly_cat = cat_df.sum().sort_values(ascending=False)
            fig_donut_spend = px.pie(
                names=yearly_cat.index,
                values=yearly_cat.values,
                hole=0.45,
                title="Full Period",
                color_discrete_sequence=px.colors.qualitative.Pastel,
            )
            fig_donut_spend.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#e0e0e0",
                margin=dict(t=40, b=20),
            )
            st.plotly_chart(fig_donut_spend, width="stretch")
    else:
        st.info("No spending data in selected range.")

    # ── 6. Cash Deposit Summary ───────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 💵 Cash Deposit Summary")

    if not di_df.empty and "Description" in di_df.columns and "Month" in di_df.columns:
        dep_mask = di_df["Description"].str.startswith(_DEPOSIT_PREFIX, na=False)
        in_range_mask = di_df["Month"].apply(
            lambda x: datetime.date(x.year, x.month, 1) in selected_set if pd.notna(x) else False
        )
        all_deposits = di_df[dep_mask & in_range_mask].copy()

        if not all_deposits.empty:
            d1, d2, d3 = st.columns(3)
            d1.metric("Total Deposited", f"${all_deposits['Amount'].sum():,.2f}")
            d2.metric("# of Deposits", str(len(all_deposits)))
            d3.metric("Avg per Deposit", f"${all_deposits['Amount'].mean():,.2f}")
        else:
            st.info("No cash → debit deposits recorded in this period.")
    else:
        st.info("No deposit data available.")

    # ── 7. Month-by-Month Summary Table ──────────────────────────────────────
    st.markdown("---")
    with st.expander("📋 Month-by-Month Summary", expanded=True):
        if not trend_df.empty:
            display = trend_df.copy()
            totals_row = {
                "Month": "── TOTAL ──",
                "Income": trend_df["Income"].sum(),
                "Expenses": trend_df["Expenses"].sum(),
                "Net": trend_df["Net"].sum(),
                "Networth": float("nan"),
            }
            display = pd.concat([display, pd.DataFrame([totals_row])], ignore_index=True)
            fmt = "${:,.2f}".format
            for col in ["Income", "Expenses", "Net"]:
                display[col] = display[col].map(fmt)
            display["Networth"] = display["Networth"].apply(
                lambda x: fmt(x) if pd.notna(x) else "—"
            )
            display = display.rename(columns={"Networth": "Net Worth (EOM)"})
            st.dataframe(display, width="stretch", hide_index=True)

    with st.expander("📋 Spending by Category (Detailed)"):
        if not cat_df.empty:
            fmt = "${:,.2f}".format
            display_cat = cat_df.copy()
            for col in display_cat.columns:
                display_cat[col] = display_cat[col].map(fmt)
            st.dataframe(display_cat.reset_index(), width="stretch", hide_index=True)
