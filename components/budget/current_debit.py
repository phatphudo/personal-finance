import pandas as pd
import streamlit as st

from utils.gsheets import (
    append_debit_in,
    append_debit_out,
    update_debit_in_row,
    update_debit_out_row,
    upsert_cash_count,
)

_CAT_SPENDING = "Spending"
_CAT_CC_PAYMENT = "Credit Card Payment"
_DEBIT_OUT_CATEGORIES = [_CAT_SPENDING, _CAT_CC_PAYMENT]


# ── Debit section ─────────────────────────────────────────────────────────────


def render_debit(
    di_df,
    do_df,
    cc_df,
    sel_year,
    sel_mon,
    month_key,
    today,
    bank_accounts,
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

    # Distinguish standard income vs cash deposits
    if not income_tx.empty:
        is_deposit = income_tx["Description"].str.startswith("From cash", na=False)
        regular_income_tx = income_tx[~is_deposit]
        deposit_inc_tx = income_tx[is_deposit]
    else:
        regular_income_tx = pd.DataFrame()
        deposit_inc_tx = pd.DataFrame()

    total_income = (
        regular_income_tx["Amount"].sum() if not regular_income_tx.empty else 0.0
    )
    total_deposit_in = (
        deposit_inc_tx["Amount"].sum() if not deposit_inc_tx.empty else 0.0
    )
    total_in = total_income + total_deposit_in

    if not spending_tx.empty:
        is_cc_payment = spending_tx["Category"] == _CAT_CC_PAYMENT
        regular_spending_tx = spending_tx[~is_cc_payment]
        cc_payment_tx = spending_tx[is_cc_payment]
    else:
        regular_spending_tx = pd.DataFrame()
        cc_payment_tx = pd.DataFrame()

    total_spending = (
        regular_spending_tx["Amount"].sum() if not regular_spending_tx.empty else 0.0
    )
    total_cc_payment = cc_payment_tx["Amount"].sum() if not cc_payment_tx.empty else 0.0
    total_out = total_spending + total_cc_payment

    # ── Remaining from previous month ──────────────────────────────────────
    if sel_mon == 1:
        prev_year, prev_mon = sel_year - 1, 12
    else:
        prev_year, prev_mon = sel_year, sel_mon - 1

    prev_actual = 0.0
    if not cc_df.empty:
        prev_counts = cc_df[
            (cc_df["Month"].dt.year == prev_year)
            & (cc_df["Month"].dt.month == prev_mon)
            & (cc_df["Source"] == debit_account)
        ]
        if not prev_counts.empty:
            prev_actual = prev_counts["Amount"].sum()

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
            help="All income excluding Cash Deposits",
        )
        f2.metric(
            "Total Spending",
            f"${total_spending:,.2f}",
            help="All spending excluding CC Payments",
        )
        f3, f4 = st.columns(2)
        f3.metric("Total In", f"${total_in:,.2f}", help="Including Cash Deposits")
        f4.metric("Total Out", f"${total_out:,.2f}", help="Including CC Payments")

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
    with st.expander("⚙️ Settings: Start Balance & End Count", expanded=False):
        st.caption(f"**Previous Month End Balance** defaults to ${prev_actual:,.2f}.")
        c1, c2 = st.columns([2, 1])
        new_remaining = c1.number_input(
            "Override Starting Balance ($)",
            value=float(remaining),
            step=0.01,
            format="%.2f",
            key=f"debit_remaining_input_{month_key}",
        )
        if c2.button(
            "Apply", key=f"apply_debit_remaining_{month_key}", use_container_width=True
        ):
            st.session_state[override_key] = new_remaining
            st.rerun()

        st.markdown("**Manual Debit Account End-of-Month Balance**")
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
        if st.button("💾 Save Actual Balance", key=f"save_debit_count_{month_key}"):
            with st.spinner("Saving count…"):
                upsert_cash_count(month_key, debit_account, new_count)
            st.success("Balance saved!")
            st.rerun()

    st.markdown("---")

    col_in, col_out = st.columns(2)
    with col_in:
        st.markdown("##### ⬇️ Debit In (Income)")
        _debit_in_editor(income_tx, month_key, today)

    with col_out:
        st.markdown("##### ⬆️ Debit Out (Spending)")
        _debit_out_editor(spending_tx, month_key, today)


def _build_debit_in_display(df_tx):
    cols = ["_SheetRow", "Date", "Description", "Amount"]
    if df_tx.empty:
        return pd.DataFrame(
            {
                "_SheetRow": pd.Series([], dtype="Int64"),
                "Date": pd.Series([], dtype="str"),
                "Description": pd.Series([], dtype="str"),
                "Amount": pd.Series([], dtype="float"),
            }
        )
    df = df_tx.copy().reset_index(drop=True)
    df["Date"] = df["Date"].dt.strftime("%m/%d")
    df["Description"] = df.get("Description", "").fillna("").astype(str)
    df["Amount"] = df["Amount"].round(2)
    return df[cols]


def _build_debit_out_display(df_tx):
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
    df["Amount"] = df["Amount"].round(2)

    def _normalise(cat):
        return cat if cat in _DEBIT_OUT_CATEGORIES else _CAT_SPENDING

    df["Category"] = df["Category"].apply(_normalise)
    return df[cols]


def _debit_in_editor(df_tx, month_key, today):
    orig = _build_debit_in_display(df_tx)
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
                    or old["Amount"] != row["Amount"]
                ):
                    year = month_key[:4]
                    full_date = f"{row['Date']}/{year}"
                    update_debit_in_row(
                        int(old["_SheetRow"]),
                        full_date,
                        month_key,
                        str(row["Description"]),
                        float(row["Amount"]),
                    )
                    saved += 1
            else:
                year = month_key[:4]
                full_date = f"{row['Date']}/{year}"
                append_debit_in(
                    full_date, month_key, str(row["Description"]), float(row["Amount"])
                )
                saved += 1

    if saved:
        st.success(f"Saved {saved} change(s)!")
        st.rerun()
    else:
        st.info("No changes detected.")


def _debit_out_editor(df_tx, month_key, today):
    orig = _build_debit_out_display(df_tx)
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
                options=_DEBIT_OUT_CATEGORIES,
                default=_CAT_SPENDING,
                required=True,
            ),
            "Amount": st.column_config.NumberColumn(
                "Amount ($)", min_value=0.0, format="$%.2f", default=0.0
            ),
        },
    )
    if st.button("💾 Save Debit Spending", key=f"save_debit_out_{month_key}"):
        _sync_debit_out_changes(orig, edited, month_key)


def _sync_debit_out_changes(orig, edited, month_key):
    orig_len = len(orig)
    saved = 0
    with st.spinner("Saving…"):
        for idx in range(len(edited)):
            row = edited.iloc[idx]
            amt = row.get("Amount", 0)
            date_val = str(row.get("Date", "")).strip()
            if pd.isna(amt) or amt == 0 or date_val in ("", "nan", "NaT", "None"):
                continue
            cat = row.get("Category") or _CAT_SPENDING
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
                saved += 1

    if saved:
        st.success(f"Saved {saved} change(s)!")
        st.rerun()
    else:
        st.info("No changes detected.")
