import pandas as pd
import streamlit as st


def render_overview(
    ci_df,
    co_df,
    di_df,
    do_df,
    cred_df,
    cc_df,
    sel_year,
    sel_mon,
    cash_sources,
    bank_accounts,
):
    def _get_month_data(df):
        if df is None or df.empty:
            return pd.DataFrame()
        if "Month" in df.columns and not df["Month"].isna().all():
            return df[
                (df["Month"].dt.year == sel_year) & (df["Month"].dt.month == sel_mon)
            ].copy()
        if "Date" in df.columns:
            return df[
                (df["Date"].dt.year == sel_year) & (df["Date"].dt.month == sel_mon)
            ].copy()
        return pd.DataFrame()

    co_spend = _get_month_data(co_df)
    do_spend = _get_month_data(do_df)
    cr_spend = _get_month_data(cred_df)

    # Exclude internal / non-spending
    _EXCLUDE_SPENDING = ["Deposit to Debit", "Add to Vault", "Credit Card Payment", "Withdrawal from Debit"]
    if not co_spend.empty and "Category" in co_spend.columns:
        co_spend = co_spend[~co_spend["Category"].isin(_EXCLUDE_SPENDING)].copy()
    if not do_spend.empty and "Category" in do_spend.columns:
        do_spend = do_spend[~do_spend["Category"].isin(_EXCLUDE_SPENDING)].copy()
    if not cr_spend.empty and "Category" in cr_spend.columns:
        cr_spend = cr_spend[~cr_spend["Category"].isin(_EXCLUDE_SPENDING)].copy()

    if not co_spend.empty:
        co_spend["Type"] = "Cash"
    if not do_spend.empty:
        do_spend["Type"] = "Debit"
    if not cr_spend.empty:
        cr_spend["Type"] = "Credit"

    valid_spend = [df for df in [co_spend, do_spend, cr_spend] if not df.empty]
    spending_all = (
        pd.concat(valid_spend, ignore_index=True) if valid_spend else pd.DataFrame()
    )

    ci_inc = _get_month_data(ci_df)
    di_inc = _get_month_data(di_df)

    # Exclude deposits and withdrawals from income (they are internal transfers)
    _EXCLUDE_INCOME = ["Deposit", "Withdrawal"]
    if not ci_inc.empty and "Category" in ci_inc.columns:
        ci_inc = ci_inc[~ci_inc["Category"].isin(_EXCLUDE_INCOME)].copy()
    if not di_inc.empty and "Category" in di_inc.columns:
        di_inc = di_inc[~di_inc["Category"].isin(_EXCLUDE_INCOME)].copy()

    if not ci_inc.empty:
        ci_inc["Type"] = "Cash"
    if not di_inc.empty:
        di_inc["Type"] = "Debit"

    valid_inc = [df for df in [ci_inc, di_inc] if not df.empty]
    income_all = (
        pd.concat(valid_inc, ignore_index=True) if valid_inc else pd.DataFrame()
    )

    # Calculate overall metrics
    total_income = income_all["Amount"].sum() if not income_all.empty else 0.0
    total_spending = spending_all["Amount"].sum() if not spending_all.empty else 0.0

    total_balance = 0.0
    total_networth = 0.0
    networth_all = pd.DataFrame()
    if not cc_df.empty:
        month_counts = cc_df[
            (cc_df["Month"].dt.year == sel_year) & (cc_df["Month"].dt.month == sel_mon)
        ].copy()

        cash_df = month_counts[month_counts["Source"].isin(cash_sources)].copy()
        if not cash_df.empty:
            cash_df["Type"] = "Cash"

        debit_df = month_counts[month_counts["Source"].isin(bank_accounts)].copy()
        if not debit_df.empty:
            debit_df["Type"] = "Debit"

        valid_nw = [df for df in [cash_df, debit_df] if not df.empty]
        if valid_nw:
            networth_all = pd.concat(valid_nw, ignore_index=True)

        cash_in_hand = cash_df["Amount"].sum() if not cash_df.empty else 0.0
        debit_bal = debit_df["Amount"].sum() if not debit_df.empty else 0.0

        total_balance = cash_in_hand + debit_bal

    # Credit balance = total charges for the month (liability to subtract)
    cr_month = _get_month_data(cred_df)
    credit_balance = cr_month["Amount"].sum() if not cr_month.empty else 0.0

    total_networth = total_balance - credit_balance

    st.markdown("---")
    st.markdown("### 📊 Monthly Overview")

    net_flow = total_income - total_spending

    grp1, grp2 = st.columns(2, gap="large")

    # ── Group 1: Net Worth breakdown ─────────────────────────────────────────
    with grp1:
        st.caption("💰 Net Worth")
        nw_left, nw_right = st.columns([1, 1])
        with nw_right:
            st.metric(
                "Total Balance",
                f"${total_balance:,.2f}",
                help="Cash in hand + Debit balance",
            )
            st.metric(
                "Credit Balance",
                f"${credit_balance:,.2f}",
                help="Outstanding credit card charges this month",
            )
        with nw_left:
            # Spacer to vertically center against the two right-side metrics
            st.write("")
            st.write("")
            st.metric(
                "Total Networth",
                f"${total_networth:,.2f}",
                help="Total Balance − Credit Balance",
            )

    # ── Group 2: Cash Flow breakdown ──────────────────────────────────────────
    with grp2:
        st.caption("📈 Cash Flow")
        cf_left, cf_right = st.columns([1, 1])
        with cf_right:
            st.metric("Total Income", f"${total_income:,.2f}")
            st.metric("Total Spending", f"${total_spending:,.2f}")
        with cf_left:
            # Spacer to vertically center against the two right-side metrics
            st.write("")
            st.write("")
            net_color = "normal" if net_flow >= 0 else "inverse"
            net_delta = f"+${net_flow:,.2f}" if net_flow >= 0 else f"-${abs(net_flow):,.2f}"
            st.metric(
                "Net Flow",
                f"${net_flow:,.2f}",
                delta=net_delta,
                delta_color=net_color,
                help="Total Income − Total Spending",
            )

    try:
        import plotly.express as px

        # Swap tabs: Income first, then Spending
        tab_nw, tab_inc, tab_spend = st.tabs(
            ["💰 Networth", "📈 Income", "💸 Spending"]
        )

        with tab_nw:
            if not networth_all.empty and "Source" in networth_all.columns:
                c1, c2 = st.columns(2)
                with c1:
                    nw_grouped = networth_all.groupby(
                        ["Source", "Type"], as_index=False
                    )["Amount"].sum()
                    fig_bar_nw = px.bar(
                        nw_grouped,
                        x="Source",
                        y="Amount",
                        color="Type",
                        barmode="group",
                        title="Networth by Account/Bucket",
                        color_discrete_sequence=px.colors.qualitative.Pastel,
                    )
                    fig_bar_nw.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)",
                        font_color="#e0e0e0",
                        margin=dict(t=40, b=20),
                    )
                    st.plotly_chart(fig_bar_nw, width="stretch")
                with c2:
                    nw_total = networth_all.groupby("Source", as_index=False)[
                        "Amount"
                    ].sum()
                    fig_pie_nw = px.pie(
                        nw_total,
                        names="Source",
                        values="Amount",
                        hole=0.45,
                        title="Overall Networth Breakdown",
                        color_discrete_sequence=px.colors.qualitative.Pastel,
                    )
                    fig_pie_nw.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)",
                        font_color="#e0e0e0",
                        margin=dict(t=40, b=20),
                    )
                    st.plotly_chart(fig_pie_nw, width="stretch")
            else:
                st.info("No networth data for this month.")

        with tab_inc:
            if not income_all.empty and "Category" in income_all.columns:
                c1, c2 = st.columns(2)
                with c1:
                    inc_grouped = income_all.groupby(
                        ["Category", "Type"], as_index=False
                    )["Amount"].sum()
                    fig_bar_inc = px.bar(
                        inc_grouped,
                        x="Category",
                        y="Amount",
                        color="Type",
                        barmode="group",
                        title="Income by Source",
                        color_discrete_sequence=px.colors.qualitative.Pastel,
                    )
                    fig_bar_inc.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)",
                        font_color="#e0e0e0",
                        margin=dict(t=40, b=20),
                    )
                    st.plotly_chart(fig_bar_inc, width="stretch")
                with c2:
                    inc_total = income_all.groupby("Category", as_index=False)[
                        "Amount"
                    ].sum()
                    fig_pie_inc = px.pie(
                        inc_total,
                        names="Category",
                        values="Amount",
                        hole=0.45,
                        title="Overall Income",
                        color_discrete_sequence=px.colors.qualitative.Pastel,
                    )
                    fig_pie_inc.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)",
                        font_color="#e0e0e0",
                        margin=dict(t=40, b=20),
                    )
                    st.plotly_chart(fig_pie_inc, width="stretch")
            else:
                st.info("No income data for this month.")

        with tab_spend:
            if not spending_all.empty and "Category" in spending_all.columns:
                c1, c2 = st.columns(2)
                with c1:
                    spend_grouped = spending_all.groupby(
                        ["Category", "Type"], as_index=False
                    )["Amount"].sum()
                    fig_bar = px.bar(
                        spend_grouped,
                        x="Category",
                        y="Amount",
                        color="Type",
                        barmode="group",
                        title="Spending by Source",
                        color_discrete_sequence=px.colors.qualitative.Pastel,
                    )
                    fig_bar.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)",
                        font_color="#e0e0e0",
                        margin=dict(t=40, b=20),
                    )
                    st.plotly_chart(fig_bar, width="stretch")
                with c2:
                    spend_total = spending_all.groupby("Category", as_index=False)[
                        "Amount"
                    ].sum()
                    fig_pie = px.pie(
                        spend_total,
                        names="Category",
                        values="Amount",
                        hole=0.45,
                        title="Overall Spending",
                        color_discrete_sequence=px.colors.qualitative.Pastel,
                    )
                    fig_pie.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)",
                        font_color="#e0e0e0",
                        margin=dict(t=40, b=20),
                    )
                    st.plotly_chart(fig_pie, width="stretch")
            else:
                st.info("No spending data for this month.")

    except ImportError:
        pass
