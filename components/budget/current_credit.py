import datetime

import pandas as pd
import streamlit as st

from utils.gsheets import (
    append_transaction,
    upsert_starting_balance,
)
from utils.helpers import compute_monthly_balance

# ── Generic account section (Credit / Legacy) ────────────────────────────────


def render_accounts(
    section_title,
    accounts,
    tx_df,
    sb_df,
    sel_year,
    sel_mon,
    today,
    expense_cats,
    income_cats,
):
    if not accounts:
        st.info(f"No {section_title}s configured. Add them in ⚙️ Settings.")
        return

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
    styled = combined.style.format(
        {col: "${:,.2f}".format for col in ["Start", "In", "Out", "End"]}
    )
    st.dataframe(styled, width="stretch", hide_index=True)

    st.markdown("---")

    if not tx_df.empty:
        m = (
            tx_df["Account"].isin(accounts)
            & (tx_df["Date"].dt.year == sel_year)
            & (tx_df["Date"].dt.month == sel_mon)
            & (tx_df["Type"] == "Expense")
        )
        month_exp = tx_df[m]
        if not month_exp.empty:
            import plotly.express as px

            st.markdown("#### 📊 Spending Breakdown")
            cat_totals = month_exp.groupby("Category")["Amount"].sum().reset_index()
            fig = px.pie(
                cat_totals,
                names="Category",
                values="Amount",
                hole=0.45,
                color_discrete_sequence=px.colors.qualitative.Pastel,
            )
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#e0e0e0",
                height=340,
                margin=dict(t=20, b=20),
            )
            st.plotly_chart(fig, width="stretch")

    st.markdown("---")

    with st.expander("➕ Log Transaction", expanded=False):
        with st.form(f"log_tx_{section_title}"):
            c1, c2 = st.columns(2)
            tx_date = c1.date_input("Date", value=today)
            tx_type = c2.selectbox("Type", ["Expense", "Income", "Transfer"])
            c3, c4 = st.columns(2)
            tx_account = c3.selectbox("Account", accounts or ["—"])
            cat_opts = (
                expense_cats
                if tx_type == "Expense"
                else income_cats if tx_type == "Income" else ["Transfer"]
            )
            tx_cat = c4.selectbox("Category", cat_opts or ["—"])
            c5, c6 = st.columns(2)
            tx_amount = c5.number_input(
                "Amount ($)", min_value=0.0, step=0.01, format="%.2f"
            )
            tx_desc = c6.text_input("Description (optional)")
            submitted = st.form_submit_button("Save Transaction", type="primary")

        if submitted:
            with st.spinner("Saving…"):
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

    with st.expander("⚙️ Override Starting Balance", expanded=False):
        with st.form(f"override_bal_{section_title}"):
            c1, c2 = st.columns(2)
            ov_account = c1.selectbox(
                "Account", accounts or ["—"], key=f"ov_{section_title}"
            )
            ov_balance = c2.number_input(
                "Starting Balance ($)",
                step=0.01,
                format="%.2f",
                key=f"ovbal_{section_title}",
            )
            if st.form_submit_button("Set Override"):
                month_str = datetime.date(sel_year, sel_mon, 1).strftime("%Y-%m-01")
                with st.spinner("Saving…"):
                    upsert_starting_balance(month_str, ov_account, ov_balance)
                st.success(f"Override set for {ov_account}.")
                st.rerun()
