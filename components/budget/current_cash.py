import pandas as pd
import streamlit as st

from utils.gsheets import (
    append_cash_in,
    append_cash_out,
    append_debit_in,
    update_cash_in_row,
    update_cash_out_row,
    upsert_cash_count,
    upsert_starting_balance,
)

_CAT_DEPOSIT_DEBIT = "Deposit to Debit"
_CAT_ADD_VAULT = "Add to Vault"
_CAT_WITHDRAWAL_CASH = "Withdrawal"  # auto-created when withdrawing from Debit


# ── Cash section ──────────────────────────────────────────────────────────────


def render_cash(
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
):
    if not cash_sources:
        st.info("No Cash Sources configured. Add them in ⚙️ Settings.")
        return

    # ── Pull this month's cash transactions from dedicated tabs ──────────────────────
    # Filter by the stored `Month` column (billing-period tag), NOT the raw Date.
    # Transactions physically dated in adjacent months (e.g. Jan 29 → Feb period)
    # will correctly appear under whichever month was selected when they were saved.
    def _filter_month(df):
        if df.empty:
            return pd.DataFrame()
        if "Month" in df.columns and not df["Month"].isna().all():
            return df[
                (df["Month"].dt.year == sel_year) & (df["Month"].dt.month == sel_mon)
            ].copy()
        # Fallback for rows saved before Month column existed
        return df[
            (df["Date"].dt.year == sel_year) & (df["Date"].dt.month == sel_mon)
        ].copy()

    income_tx = _filter_month(ci_df)
    spending_tx = _filter_month(co_df)

    # Separate withdrawal transfers from real income
    withdrawal_inc_tx = (
        income_tx[income_tx["Category"] == _CAT_WITHDRAWAL_CASH]
        if not income_tx.empty
        else pd.DataFrame()
    )
    regular_income_tx = (
        income_tx[income_tx["Category"] != _CAT_WITHDRAWAL_CASH]
        if not income_tx.empty
        else pd.DataFrame()
    )

    total_income = regular_income_tx["Amount"].sum() if not regular_income_tx.empty else 0.0
    total_withdrawal_in = withdrawal_inc_tx["Amount"].sum() if not withdrawal_inc_tx.empty else 0.0

    regular_spending_tx = (
        spending_tx[~spending_tx["Category"].isin([_CAT_DEPOSIT_DEBIT, _CAT_ADD_VAULT])]
        if not spending_tx.empty
        else pd.DataFrame()
    )
    deposit_tx = (
        spending_tx[spending_tx["Category"] == _CAT_DEPOSIT_DEBIT]
        if not spending_tx.empty
        else pd.DataFrame()
    )
    vault_tx = (
        spending_tx[spending_tx["Category"] == _CAT_ADD_VAULT]
        if not spending_tx.empty
        else pd.DataFrame()
    )

    total_spending = (
        regular_spending_tx["Amount"].sum() if not regular_spending_tx.empty else 0.0
    )
    total_deposit = deposit_tx["Amount"].sum() if not deposit_tx.empty else 0.0
    total_vault = vault_tx["Amount"].sum() if not vault_tx.empty else 0.0

    # ── Remaining from previous month ──────────────────────────────────────
    prev_actual = 0.0
    if not sb_df.empty:
        match = sb_df[
            (sb_df["Month"].dt.year == sel_year)
            & (sb_df["Month"].dt.month == sel_mon)
            & (sb_df["Account"] == "Cash")
        ]
        if not match.empty:
            prev_actual = float(match.iloc[0]["Starting Balance"])

    override_key = f"cash_remaining_{month_key}"
    if override_key not in st.session_state:
        st.session_state[override_key] = prev_actual

    remaining = st.session_state[override_key]
    total_cash_in = remaining + total_income + total_withdrawal_in
    total_cash_out = total_spending + total_deposit + total_vault
    expected_balance = total_cash_in - total_cash_out

    # ── Actual balance from physical counts ────────────────────────────────
    # NOTE: cc_df (cash_counts sheet) is shared — it also stores the debit
    # account actual balance. Restrict both aggregates to cash_sources only
    # so the debit balance never bleeds into cash metrics.
    actual_balance = 0.0
    total_in_hand = 0.0
    if not cc_df.empty:
        month_counts = cc_df[
            (cc_df["Month"].dt.year == sel_year)
            & (cc_df["Month"].dt.month == sel_mon)
            & (cc_df["Source"].isin(cash_sources))  # exclude debit account row
        ]
        active_counts = month_counts[month_counts["Source"].isin(active_sources)]
        actual_balance = active_counts["Amount"].sum()
        total_in_hand = month_counts["Amount"].sum()

    balance_diff = actual_balance - expected_balance

    # ══════════════════════════════════════════════════════════════════
    # METRICS — 2 columns: left = Cash Flow, right = Balance Snapshot
    # ══════════════════════════════════════════════════════════════════
    col_flow, col_bal = st.columns(2)

    with col_flow:
        st.markdown("##### 💸 Cash Flow")
        f1, f2 = st.columns(2)
        f1.metric("Total Income", f"${total_income:,.2f}")
        f2.metric("Total Spending", f"${total_spending:,.2f}")
        f3, f4 = st.columns(2)
        f3.metric(
            "Total Cash In",
            f"${total_cash_in:,.2f}",
            help="Previous month remaining + Total Income + Withdrawals from Debit",
        )
        f4.metric(
            "Total Cash Out",
            f"${total_cash_out:,.2f}",
            help="Spending + Deposit to Debit + Add to Vault",
        )

    with col_bal:
        st.markdown("##### 📊 Balance Snapshot")
        b1, b2 = st.columns(2)
        b1.metric(
            "Expected Balance", f"${expected_balance:,.2f}", help="Cash In − Cash Out"
        )
        b2.metric(
            "Actual Balance",
            f"${actual_balance:,.2f}",
            help="Sum of physically counted active sources (excl. Vault)",
        )
        b3, b4 = st.columns(2)
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
            help="Actual − Expected",
        )
        b4.metric(
            "Total In Hand",
            f"${total_in_hand:,.2f}",
            help="Sum of all sources including Vault",
        )

    # ── Remaining override & physical counts ───────────────────────────────
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
                key=f"remaining_input_{month_key}",
            )
            if st.button(
                "💾 Save Starting Balance",
                key=f"apply_remaining_{month_key}",
                width="stretch",
            ):
                st.session_state[override_key] = new_remaining
                with st.spinner("Saving..."):
                    upsert_starting_balance(month_key, "Cash", new_remaining)
                st.success("Starting balance saved!")
                st.rerun()

        with col_ec:
            st.markdown("#### 🎯 End of Month Counts")
            st.caption("Physical tally of active sources.")

            grid_cols = st.columns(2)
            new_counts = {}
            for i, src in enumerate(cash_sources):
                cur = 0.0
                if not cc_df.empty:
                    match = cc_df[
                        (cc_df["Month"].dt.year == sel_year)
                        & (cc_df["Month"].dt.month == sel_mon)
                        & (cc_df["Source"] == src)
                    ]
                    if not match.empty:
                        cur = float(match.iloc[0]["Amount"])

                target_col = grid_cols[i % 2]
                new_counts[src] = target_col.number_input(
                    src,
                    value=cur,
                    min_value=0.0,
                    step=0.01,
                    format="%.2f",
                    key=f"cash_count_{month_key}_{src}",
                )

            if st.button(
                "💾 Save Cash Counts",
                key=f"save_cash_counts_{month_key}",
                width="stretch",
            ):
                with st.spinner("Saving counts…"):
                    for src, amt in new_counts.items():
                        upsert_cash_count(month_key, src, amt)
                st.success("Cash counts saved!")
                st.rerun()

    st.markdown("---")

    # ══════════════════════════════════════════════════════════════════
    # INCOME / SPENDING TABLES — side by side
    # ══════════════════════════════════════════════════════════════════
    col_in, col_out = st.columns(2)

    with col_in:
        st.markdown("##### ⬆️ Cash In (Income)")
        _cash_in_editor(income_tx, month_key, today, income_cats)

    with col_out:
        st.markdown("##### ⬇️ Cash Out (Spending)")
        _cash_out_editor(spending_tx, month_key, today, bank_accounts, expense_cats)


def _build_in_display(income_tx):
    """Prepare the Cash In dataframe for the data editor."""
    cols = ["_SheetRow", "Date", "Description", "Category", "Amount"]
    if income_tx.empty:
        return pd.DataFrame(
            {
                "_SheetRow": pd.Series([], dtype="Int64"),
                "Date": pd.Series([], dtype="str"),
                "Description": pd.Series([], dtype="str"),
                "Category": pd.Series([], dtype="str"),
                "Amount": pd.Series([], dtype="float"),
            }
        )
    df = income_tx.copy().reset_index(drop=True)
    df["Date"] = df["Date"].dt.strftime("%m/%d")
    df["Description"] = df.get("Description", "").fillna("").astype(str)
    df["Category"] = df.get("Category", "").fillna("").astype(str)
    df["Amount"] = df["Amount"].astype(float).round(2)
    return df[cols]


def _build_out_display(spending_tx, expense_cats):
    """Prepare the Cash Out dataframe for the data editor."""
    cols = ["_SheetRow", "Date", "Description", "Category", "Amount"]
    if spending_tx.empty:
        return pd.DataFrame(
            {
                "_SheetRow": pd.Series([], dtype="Int64"),
                "Date": pd.Series([], dtype="str"),
                "Description": pd.Series([], dtype="str"),
                "Category": pd.Series([], dtype="str"),
                "Amount": pd.Series([], dtype="float"),
            }
        )
    df = spending_tx.copy().reset_index(drop=True)
    df["Date"] = df["Date"].dt.strftime("%m/%d")
    df["Description"] = df.get("Description", "").fillna("").astype(str)
    df["Amount"] = df["Amount"].astype(float).round(2)

    if not expense_cats:
        expense_cats = ["Other"]

    valid_cats = expense_cats + [_CAT_DEPOSIT_DEBIT, _CAT_ADD_VAULT]
    default_cat = expense_cats[0]

    # Normalise categories into our system
    def _normalise(cat):
        return cat if cat in valid_cats else default_cat

    df["Category"] = df["Category"].apply(_normalise)
    return df[cols]


def _cash_in_editor(income_tx, month_key, today, income_cats):
    orig = _build_in_display(income_tx)

    if not income_cats:
        income_cats = ["Other"]

    edited = st.data_editor(
        orig,
        key=f"cash_in_editor_{month_key}",
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

    if st.button("💾 Save Income Changes", key=f"save_in_{month_key}"):
        _sync_in_changes(orig, edited, month_key)


def _sync_in_changes(orig, edited, month_key):
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
                    update_cash_in_row(
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
                append_cash_in(
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


def _cash_out_editor(spending_tx, month_key, today, bank_accounts, expense_cats):
    if not expense_cats:
        expense_cats = ["Other"]

    orig = _build_out_display(spending_tx, expense_cats)

    options = expense_cats + [_CAT_DEPOSIT_DEBIT, _CAT_ADD_VAULT]

    edited = st.data_editor(
        orig,
        key=f"cash_out_editor_{month_key}",
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        column_config={
            "_SheetRow": None,  # hidden
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

    if st.button("💾 Save Spending Changes", key=f"save_out_{month_key}"):
        _sync_out_changes(orig, edited, month_key, bank_accounts, expense_cats)


def _sync_out_changes(orig, edited, month_key, bank_accounts, expense_cats):
    debit_account = bank_accounts[0] if bank_accounts else None
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
                    update_cash_out_row(
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
                append_cash_out(
                    full_date,
                    month_key,
                    str(row["Description"]),
                    cat,
                    float(row["Amount"]),
                )
                if cat == _CAT_DEPOSIT_DEBIT and debit_account:
                    # Log as an incoming transfer into Debit Instead
                    desc = (
                        f"From cash: {row['Description']}"
                        if str(row["Description"])
                        else "From cash"
                    )
                    append_debit_in(
                        full_date,
                        month_key,
                        desc,
                        "Deposit",
                        float(row["Amount"]),
                    )
                saved += 1

    if saved:
        st.success(f"Saved {saved} change(s)!")
        st.rerun()
    else:
        st.info("No changes detected.")
