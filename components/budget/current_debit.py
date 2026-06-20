import pandas as pd
import streamlit as st

from utils.gsheets import (
    append_cash_in,
    append_debit_in,
    append_debit_out,
    update_debit_in_row,
    update_debit_out_row,
    upsert_cash_count,
    upsert_starting_balance,
)

_CAT_CC_PAYMENT = "Credit Card Payment"
_CAT_WITHDRAWAL = "Withdrawal from Debit"


# ── Debit section ─────────────────────────────────────────────────────────────


def render_debit(
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
):
    if not bank_accounts:
        st.info("No Debit Accounts configured. Add them in ⚙️ Settings.")
        return

    debit_account = bank_accounts[0]

    def _filter_month(df):
        if df.empty:
            return pd.DataFrame()
        if "Month" in df.columns and not df["Month"].isna().all():
            return df[
                (df["Month"].dt.year == sel_year) & (df["Month"].dt.month == sel_mon)
            ].copy()
        return df[
            (df["Date"].dt.year == sel_year) & (df["Date"].dt.month == sel_mon)
        ].copy()

    income_tx = _filter_month(di_df)
    spending_tx = _filter_month(do_df)

    # Distinguish standard income vs cash deposits vs family wire transfers
    if not income_tx.empty:
        is_deposit = income_tx["Description"].str.startswith("From cash", na=False)
        is_transfer = income_tx["Category"] == "Transfer"
        regular_income_tx = income_tx[~is_deposit & ~is_transfer]
        deposit_inc_tx = income_tx[is_deposit]
        transfer_inc_tx = income_tx[is_transfer & ~is_deposit]  # Transfer, not a deposit
    else:
        regular_income_tx = pd.DataFrame()
        deposit_inc_tx = pd.DataFrame()
        transfer_inc_tx = pd.DataFrame()

    total_income = (
        regular_income_tx["Amount"].sum() if not regular_income_tx.empty else 0.0
    )
    total_deposit_in = (
        deposit_inc_tx["Amount"].sum() if not deposit_inc_tx.empty else 0.0
    )
    total_transfer_in = (
        transfer_inc_tx["Amount"].sum() if not transfer_inc_tx.empty else 0.0
    )
    total_in = total_income + total_deposit_in + total_transfer_in

    if not spending_tx.empty:
        is_excluded = spending_tx["Category"].isin([_CAT_CC_PAYMENT, _CAT_WITHDRAWAL])
        regular_spending_tx = spending_tx[~is_excluded]
        cc_payment_tx = spending_tx[spending_tx["Category"] == _CAT_CC_PAYMENT]
        withdrawal_tx = spending_tx[spending_tx["Category"] == _CAT_WITHDRAWAL]
    else:
        regular_spending_tx = pd.DataFrame()
        cc_payment_tx = pd.DataFrame()
        withdrawal_tx = pd.DataFrame()

    total_spending = (
        regular_spending_tx["Amount"].sum() if not regular_spending_tx.empty else 0.0
    )
    total_cc_payment = cc_payment_tx["Amount"].sum() if not cc_payment_tx.empty else 0.0
    total_withdrawal = withdrawal_tx["Amount"].sum() if not withdrawal_tx.empty else 0.0
    total_out = total_spending + total_cc_payment + total_withdrawal

    # ── Remaining from previous month ──────────────────────────────────────
    prev_actual = 0.0
    if not sb_df.empty:
        match = sb_df[
            (sb_df["Month"].dt.year == sel_year)
            & (sb_df["Month"].dt.month == sel_mon)
            & (sb_df["Account"] == "Debit")
        ]
        if not match.empty:
            prev_actual = float(match.iloc[0]["Starting Balance"])

    override_key = f"debit_remaining_{month_key}"
    if override_key not in st.session_state:
        st.session_state[override_key] = prev_actual

    remaining = st.session_state[override_key]
    expected_balance = remaining + total_in - total_out

    # ── Actual balance ────────────────────────────────
    actual_balance = 0.0
    if not cc_df.empty:
        month_counts = cc_df[
            (cc_df["Month"].dt.year == sel_year)
            & (cc_df["Month"].dt.month == sel_mon)
            & (cc_df["Source"] == debit_account)
        ]
        if not month_counts.empty:
            actual_balance = month_counts["Amount"].sum()

    balance_diff = actual_balance - expected_balance

    # ══════════════════════════════════════════════════════════════════
    col_flow, col_bal = st.columns(2)

    with col_flow:
        st.markdown(f"##### 🔄 {debit_account} Flow")
        f1, f2 = st.columns(2)
        f1.metric(
            "Total Income",
            f"${total_income:,.2f}",
            help="Real income only — excludes Cash Deposits & Transfers (wire transfers)",
        )
        f2.metric(
            "Total Spending",
            f"${total_spending:,.2f}",
            help="All spending excluding CC Payments",
        )
        f3, f4 = st.columns(2)
        f3.metric("Total In", f"${total_in:,.2f}", help="Income + Cash Deposits + Transfers")
        f4.metric("Total Out", f"${total_out:,.2f}", help="Including CC Payments & Withdrawals")

    with col_bal:
        st.markdown("##### 📊 Balance Snapshot")
        b1, b2 = st.columns(2)
        b1.metric(
            "Expected Balance",
            f"${expected_balance:,.2f}",
            help="Previous Month + Total In - Total Out",
        )
        b2.metric("Actual Balance", f"${actual_balance:,.2f}")

        b3, _ = st.columns(2)
        diff_delta = (
            f"+${balance_diff:,.2f}"
            if balance_diff >= 0
            else f"-${abs(balance_diff):,.2f}"
        )
        b3.metric(
            "Difference",
            f"${balance_diff:,.2f}",
            delta=diff_delta,
            delta_color="normal" if balance_diff >= 0 else "inverse",
        )

    # ── Settings & Balances ───────────────────────────────────────────────
    with st.expander("⚙️ Settings: Balances & Counts", expanded=False):
        col_sb, col_ec = st.columns(2, gap="large")

        with col_sb:
            st.markdown("#### 🏁 Starting Balance")
            st.caption(f"Defaults to stored value of ${prev_actual:,.2f}.")
            new_remaining = st.number_input(
                "Override Amount ($)",
                value=float(remaining),
                step=0.01,
                format="%.2f",
                key=f"debit_remaining_input_{month_key}",
            )
            if st.button(
                "💾 Save Starting Balance",
                key=f"apply_debit_remaining_{month_key}",
                width="stretch",
            ):
                st.session_state[override_key] = new_remaining
                with st.spinner("Saving..."):
                    upsert_starting_balance(month_key, "Debit", new_remaining)
                st.success("Starting balance saved!")
                st.rerun()

        with col_ec:
            st.markdown("#### 🎯 End of Month Count")
            st.caption("Actual balance from bank statement.")

            cur_actual = 0.0
            if not cc_df.empty:
                match = cc_df[
                    (cc_df["Month"].dt.year == sel_year)
                    & (cc_df["Month"].dt.month == sel_mon)
                    & (cc_df["Source"] == debit_account)
                ]
                if not match.empty:
                    cur_actual = float(match.iloc[0]["Amount"])

            new_count = st.number_input(
                debit_account,
                value=cur_actual,
                min_value=0.0,
                step=0.01,
                format="%.2f",
                key=f"debit_count_{month_key}_{debit_account}",
            )

            if st.button(
                "💾 Save Actual Balance",
                key=f"save_debit_count_{month_key}",
                width="stretch",
            ):
                with st.spinner("Saving count…"):
                    upsert_cash_count(month_key, debit_account, new_count)
                st.success("Balance saved!")
                st.rerun()

    st.markdown("---")

    col_in, col_out = st.columns(2)
    with col_in:
        st.markdown("##### ⬇️ Debit In (Income)")
        _debit_in_editor(income_tx, month_key, today, income_cats)

    with col_out:
        st.markdown("##### ⬆️ Debit Out (Spending)")
        _debit_out_editor(spending_tx, month_key, today, expense_cats)


def _build_debit_in_display(df_tx):
    cols = ["_SheetRow", "Date", "Description", "Category", "Amount"]
    if df_tx.empty:
        return pd.DataFrame(
            {
                "_SheetRow": pd.Series([], dtype="Int64"),
                "Date": pd.Series([], dtype="str"),
                "Description": pd.Series([], dtype="str"),
                "Category": pd.Series([], dtype="str"),
                "Amount": pd.Series([], dtype="float"),
            }
        )
    df = df_tx.copy().reset_index(drop=True)
    df["Date"] = df["Date"].dt.strftime("%m/%d")
    df["Description"] = df.get("Description", "").fillna("").astype(str)
    df["Category"] = df.get("Category", "").fillna("").astype(str)
    df["Amount"] = df["Amount"].astype(float).round(2)
    return df[cols]


def _build_debit_out_display(df_tx, expense_cats):
    cols = ["_SheetRow", "Date", "Description", "Category", "Amount"]
    if df_tx.empty:
        return pd.DataFrame(
            {
                "_SheetRow": pd.Series([], dtype="Int64"),
                "Date": pd.Series([], dtype="str"),
                "Description": pd.Series([], dtype="str"),
                "Category": pd.Series([], dtype="str"),
                "Amount": pd.Series([], dtype="float"),
            }
        )
    df = df_tx.copy().reset_index(drop=True)
    df["Date"] = df["Date"].dt.strftime("%m/%d")
    df["Description"] = df.get("Description", "").fillna("").astype(str)
    df["Amount"] = df["Amount"].astype(float).round(2)

    if not expense_cats:
        expense_cats = ["Other"]

    valid_cats = expense_cats + [_CAT_CC_PAYMENT, _CAT_WITHDRAWAL]
    default_cat = expense_cats[0]

    def _normalise(cat):
        return cat if cat in valid_cats else default_cat

    df["Category"] = df["Category"].apply(_normalise)
    return df[cols]


def _debit_in_editor(df_tx, month_key, today, income_cats):
    orig = _build_debit_in_display(df_tx)

    if not income_cats:
        income_cats = ["Other"]

    edited = st.data_editor(
        orig,
        key=f"debit_in_editor_{month_key}",
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        column_config={
            "_SheetRow": None,
            "Date": st.column_config.TextColumn(
                "Date (MM/DD)", default=today.strftime("%m/%d")
            ),
            "Description": st.column_config.TextColumn("Description", default=""),
            "Category": st.column_config.SelectboxColumn(
                "Category",
                options=income_cats,
                default=income_cats[0],
                required=True,
            ),
            "Amount": st.column_config.NumberColumn(
                "Amount ($)", min_value=0.0, format="$%.2f", default=0.0
            ),
        },
    )
    if st.button("💾 Save Debit Income", key=f"save_debit_in_{month_key}"):
        _sync_debit_in_changes(orig, edited, month_key)


def _sync_debit_in_changes(orig, edited, month_key):
    orig_len = len(orig)
    saved = 0
    with st.spinner("Saving…"):
        for idx in range(len(edited)):
            row = edited.iloc[idx]
            amt = row.get("Amount", 0)
            date_val = str(row.get("Date", "")).strip()
            if pd.isna(amt) or amt == 0 or date_val in ("", "nan", "NaT", "None"):
                continue
            if idx < orig_len:
                old = orig.iloc[idx]
                if (
                    old["Date"] != row["Date"]
                    or str(old["Description"]) != str(row["Description"])
                    or str(old["Category"]) != str(row["Category"])
                    or old["Amount"] != row["Amount"]
                ):
                    year = month_key[:4]
                    full_date = f"{row['Date']}/{year}"
                    update_debit_in_row(
                        int(old["_SheetRow"]),
                        full_date,
                        month_key,
                        str(row["Description"]),
                        str(row["Category"]),
                        float(row["Amount"]),
                    )
                    saved += 1
            else:
                year = month_key[:4]
                full_date = f"{row['Date']}/{year}"
                append_debit_in(
                    full_date,
                    month_key,
                    str(row["Description"]),
                    str(row["Category"]),
                    float(row["Amount"]),
                )
                saved += 1

    if saved:
        st.success(f"Saved {saved} change(s)!")
        st.rerun()
    else:
        st.info("No changes detected.")


def _debit_out_editor(df_tx, month_key, today, expense_cats):
    if not expense_cats:
        expense_cats = ["Other"]

    orig = _build_debit_out_display(df_tx, expense_cats)

    options = expense_cats + [_CAT_CC_PAYMENT, _CAT_WITHDRAWAL]

    edited = st.data_editor(
        orig,
        key=f"debit_out_editor_{month_key}",
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        column_config={
            "_SheetRow": None,
            "Date": st.column_config.TextColumn(
                "Date (MM/DD)", default=today.strftime("%m/%d")
            ),
            "Description": st.column_config.TextColumn("Description", default=""),
            "Category": st.column_config.SelectboxColumn(
                "Category",
                options=options,
                default=expense_cats[0],
                required=True,
            ),
            "Amount": st.column_config.NumberColumn(
                "Amount ($)", min_value=0.0, format="$%.2f", default=0.0
            ),
        },
    )
    if st.button("💾 Save Debit Spending", key=f"save_debit_out_{month_key}"):
        _sync_debit_out_changes(orig, edited, month_key, expense_cats)


def _sync_debit_out_changes(orig, edited, month_key, expense_cats):
    orig_len = len(orig)
    saved = 0
    with st.spinner("Saving…"):
        for idx in range(len(edited)):
            row = edited.iloc[idx]
            amt = row.get("Amount", 0)
            date_val = str(row.get("Date", "")).strip()
            if pd.isna(amt) or amt == 0 or date_val in ("", "nan", "NaT", "None"):
                continue
            cat = row.get("Category") or (expense_cats[0] if expense_cats else "Other")
            if idx < orig_len:
                old = orig.iloc[idx]
                if (
                    old["Date"] != row["Date"]
                    or str(old["Description"]) != str(row["Description"])
                    or old["Category"] != cat
                    or old["Amount"] != row["Amount"]
                ):
                    year = month_key[:4]
                    full_date = f"{row['Date']}/{year}"
                    update_debit_out_row(
                        int(old["_SheetRow"]),
                        full_date,
                        month_key,
                        str(row["Description"]),
                        cat,
                        float(row["Amount"]),
                    )
                    saved += 1
            else:
                year = month_key[:4]
                full_date = f"{row['Date']}/{year}"
                append_debit_out(
                    full_date,
                    month_key,
                    str(row["Description"]),
                    cat,
                    float(row["Amount"]),
                )
                if cat == _CAT_WITHDRAWAL:
                    # Auto-create a matching Cash In transaction tagged "Withdrawal"
                    desc = (
                        f"From debit: {row['Description']}"
                        if str(row["Description"]).strip()
                        else "From debit"
                    )
                    append_cash_in(
                        full_date,
                        month_key,
                        desc,
                        "Withdrawal",
                        float(row["Amount"]),
                    )
                saved += 1

    if saved:
        st.success(f"Saved {saved} change(s)!")
        st.rerun()
    else:
        st.info("No changes detected.")
