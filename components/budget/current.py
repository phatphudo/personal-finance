import datetime

import streamlit as st

from components.budget.current_cash import render_cash
from components.budget.current_credit import render_credit
from components.budget.current_debit import render_debit
from components.budget.current_overview import render_overview
from utils.gsheets import (
    read_cash_counts,
    read_cash_in,
    read_cash_out,
    read_credit_tx,
    read_debit_in,
    read_debit_out,
    read_settings,
    read_starting_balances,
)
from utils.helpers import month_label


def render():
    st.markdown("## 💳 Monthly Budget")

    try:
        settings = read_settings()
        cc_df = read_cash_counts()
        ci_df = read_cash_in()
        co_df = read_cash_out()
        di_df = read_debit_in()
        do_df = read_debit_out()
        cred_df = read_credit_tx()
        sb_df = read_starting_balances()
    except Exception as e:
        st.error(f"Could not load data: {e}")
        return

    cash_sources = settings.get("Cash Sources", [])
    bank_accounts = settings.get("Bank Accounts", [])
    credit_cards = settings.get("Credit Cards", [])
    expense_cats = settings.get("Spending Categories", [])
    income_cats = settings.get("Income Categories", [])

    # Vault is the first cash source by convention; all others are "active"
    vault_source = cash_sources[0] if cash_sources else "Vault"
    active_sources = cash_sources[1:] if len(cash_sources) > 1 else []

    # ── Month selector ─────────────────────────────────────────────────────
    today = datetime.date.today()
    # Derive available months from billing-period Month columns across all data sources
    _month_set = set()
    for _df in (ci_df, di_df, cred_df):
        if not _df.empty and "Month" in _df.columns:
            for m in _df["Month"].dropna():
                _month_set.add(datetime.date(m.year, m.month, 1))
    all_months = sorted(_month_set, reverse=True)
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
    month_key = sel_month.strftime("%Y-%m-01")

    render_overview(
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
    )

    st.markdown("---")

    # ── Tabs ────────────────────────────────────────────────────────────────
    tab_cash, tab_debit, tab_credit = st.tabs(
        ["💵 Cash", "🏦 Debit Account", "💳 Credit Cards"]
    )

    with tab_cash:
        render_cash(
            ci_df,
            co_df,
            cc_df,
            sb_df,
            sel_year,
            sel_mon,
            month_key,
            today,
            cash_sources,
            vault_source,
            active_sources,
            bank_accounts,
            income_cats,
            expense_cats,
        )

    with tab_debit:
        render_debit(
            di_df,
            do_df,
            cc_df,
            sb_df,
            sel_year,
            sel_mon,
            month_key,
            today,
            bank_accounts,
            income_cats,
            expense_cats,
        )

    with tab_credit:
        render_credit(
            cred_df,
            sel_year,
            sel_mon,
            month_key,
            today,
            credit_cards,
            expense_cats,
        )
