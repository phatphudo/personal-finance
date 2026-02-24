import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.gsheets import (
    append_transaction,
    read_settings,
    read_starting_balances,
    read_transactions,
    upsert_starting_balance,
)
from utils.helpers import compute_monthly_balance, get_all_months, month_label


def render():
    st.markdown("## 💳 Monthly Budget")

    try:
        tx_df = read_transactions()
        sb_df = read_starting_balances()
        settings = read_settings()
    except Exception as e:
        st.error(f"Could not load data: {e}")
        return

    cash_sources = settings.get("Cash Sources", [])
    bank_accounts = settings.get("Bank Accounts", [])
    credit_cards = settings.get("Credit Cards", [])
    expense_cats = settings.get("Spending Categories", [])
    income_cats = settings.get("Income Categories", [])
    all_accounts = cash_sources + bank_accounts + credit_cards

    # ── Month selector ─────────────────────────────────────────────────────
    today = datetime.date.today()
    all_months = get_all_months(tx_df) if not tx_df.empty else []
    current_month = datetime.date(today.year, today.month, 1)
    if current_month not in all_months:
        all_months = [current_month] + list(all_months)

    month_options = {month_label(m): m for m in all_months}
    default_label = month_label(current_month)
    selected_label = st.selectbox(
        "Month",
        list(month_options.keys()),
        index=(
            list(month_options.keys()).index(default_label)
            if default_label in month_options
            else 0
        ),
        key="budget_current_month",
    )
    sel_month = month_options[selected_label]
    sel_year, sel_mon = sel_month.year, sel_month.month

    st.markdown("---")

    # ── Account balance summary grid ───────────────────────────────────────
    def _balance_row(acct):
        if tx_df.empty:
            return {"Account": acct, "Start": 0.0, "In": 0.0, "Out": 0.0, "End": 0.0}
        b = compute_monthly_balance(tx_df, sb_df, acct, sel_year, sel_mon)
        return {
            "Account": acct,
            "Start": b["starting"],
            "In": b["income"],
            "Out": b["expenses"],
            "End": b["ending"],
        }

    def _section(title: str, accounts: list, color: str):
        if not accounts:
            return
        st.markdown(f"#### {title}")
        rows = [_balance_row(a) for a in accounts]
        sdf = pd.DataFrame(rows)
        totals = pd.DataFrame(
            [
                {
                    "Account": "**Total**",
                    "Start": sdf["Start"].sum(),
                    "In": sdf["In"].sum(),
                    "Out": sdf["Out"].sum(),
                    "End": sdf["End"].sum(),
                }
            ]
        )
        combined = pd.concat([sdf, totals], ignore_index=True)

        def fmt(v):
            return f"${v:,.2f}"

        styled = combined.style.format(
            {"Start": fmt, "In": fmt, "Out": fmt, "End": fmt}
        )
        st.dataframe(styled, width='stretch', hide_index=True)

    _section("🪙 Cash", cash_sources, "#6C63FF")
    _section("🏦 Bank / Debit", bank_accounts, "#00C49A")
    _section("💳 Credit Cards", credit_cards, "#FF6B6B")

    # ── Spending by category (current month) ───────────────────────────────
    st.markdown("---")
    st.markdown("#### Spending Breakdown")
    if not tx_df.empty:
        month_mask = (
            (tx_df["Date"].dt.year == sel_year)
            & (tx_df["Date"].dt.month == sel_mon)
            & (tx_df["Type"] == "Expense")
        )
        month_exp = tx_df[month_mask]
        if not month_exp.empty:
            cat_totals = month_exp.groupby("Category")["Amount"].sum().reset_index()
            fig_pie = px.pie(
                cat_totals,
                names="Category",
                values="Amount",
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Pastel,
            )
            fig_pie.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#e0e0e0",
                height=380,
                margin=dict(t=20, b=20),
            )
            st.plotly_chart(fig_pie, width='stretch')

            st.dataframe(
                cat_totals.sort_values("Amount", ascending=False).assign(
                    Amount=lambda d: d["Amount"].map("${:,.2f}".format)
                ),
                width='stretch',
                hide_index=True,
            )
        else:
            st.info("No expense transactions this month.")
    else:
        st.info("No transaction data yet.")

    # ── Log transaction ────────────────────────────────────────────────────
    st.markdown("---")
    with st.expander("➕ Log New Transaction", expanded=False):
        with st.form("log_tx_form"):
            col1, col2, col3 = st.columns(3)
            tx_date = col1.date_input("Date", value=today)
            tx_type = col2.selectbox("Type", ["Expense", "Income", "Transfer"])
            tx_account = col3.selectbox(
                "Account", all_accounts if all_accounts else ["—"]
            )
            col4, col5 = st.columns(2)
            cat_options = (
                expense_cats
                if tx_type == "Expense"
                else income_cats if tx_type == "Income" else ["Transfer"]
            )
            tx_cat = col4.selectbox("Category", cat_options if cat_options else ["—"])
            tx_amount = col5.number_input(
                "Amount", min_value=0.0, step=0.01, format="%.2f"
            )
            tx_desc = st.text_input("Description (optional)")
            submitted = st.form_submit_button("Save Transaction", type="primary")

        if submitted:
            with st.spinner("Saving to Google Sheets…"):
                append_transaction(
                    tx_date.strftime("%m/%d/%Y"),
                    tx_type,
                    tx_account,
                    tx_cat,
                    tx_amount,
                    tx_desc,
                )
            st.success("Transaction saved!")
            st.rerun()

    # ── Override starting balance ──────────────────────────────────────────
    with st.expander("⚙️ Override Starting Balance", expanded=False):
        with st.form("override_balance_form"):
            col1, col2 = st.columns(2)
            ov_account = col1.selectbox(
                "Account", all_accounts if all_accounts else ["—"], key="ov_acct"
            )
            ov_balance = col2.number_input(
                "Starting Balance", step=0.01, format="%.2f", key="ov_bal"
            )
            if st.form_submit_button("Set Override"):
                month_str = sel_month.strftime("%Y-%m-01")
                with st.spinner("Saving…"):
                    upsert_starting_balance(month_str, ov_account, ov_balance)
                st.success(f"Override set for {ov_account} in {selected_label}.")
                st.rerun()
