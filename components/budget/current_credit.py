import pandas as pd
import streamlit as st

from utils.gsheets import append_credit_tx, update_credit_tx_row

# ── Credit Card section ───────────────────────────────────────────────────────


def render_credit(
    cred_df,
    sel_year,
    sel_mon,
    month_key,
    today,
    credit_cards,
    expense_cats,
):
    if not credit_cards:
        st.info("No Credit Cards configured. Add them in ⚙️ Settings.")
        return

    # One sub-tab per card (future-proof for multiple cards)
    if len(credit_cards) == 1:
        _render_card(
            cred_df,
            credit_cards[0],
            sel_year,
            sel_mon,
            month_key,
            today,
            expense_cats,
        )
    else:
        card_tabs = st.tabs([f"💳 {c}" for c in credit_cards])
        for tab, card in zip(card_tabs, credit_cards):
            with tab:
                _render_card(
                    cred_df,
                    card,
                    sel_year,
                    sel_mon,
                    month_key,
                    today,
                    expense_cats,
                )


def _render_card(cred_df, card_name, sel_year, sel_mon, month_key, today, expense_cats):
    # ── Filter to this card's transactions for the selected month ────────────
    def _filter(df):
        if df.empty:
            return pd.DataFrame()
        card_match = df[
            "Category"
        ].notna()  # all rows (card is stored in description context)
        # Filter by Month billing-period tag; fallback to Date
        if "Month" in df.columns and not df["Month"].isna().all():
            period = (df["Month"].dt.year == sel_year) & (
                df["Month"].dt.month == sel_mon
            )
        else:
            period = (df["Date"].dt.year == sel_year) & (df["Date"].dt.month == sel_mon)
        # Filter by card (stored in a hidden Card column if present, else show all)
        if "Card" in df.columns:
            card_match = df["Card"] == card_name
        return df[period & card_match].copy()

    tx = _filter(cred_df)

    total_spending = tx["Amount"].sum() if not tx.empty else 0.0

    # ── Metrics ───────────────────────────────────────────────────────────────
    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("Total Charges", f"${total_spending:,.2f}")
    col_m2.metric("# Transactions", len(tx))
    if not tx.empty:
        cat_top = tx.groupby("Category")["Amount"].sum().idxmax()
        col_m3.metric("Top Category", cat_top)

    st.markdown("---")

    # ── Transaction editor ────────────────────────────────────────────────────
    st.markdown("##### 📋 Transactions")
    orig = _build_display(tx)

    edited = st.data_editor(
        orig,
        key=f"credit_tx_editor_{month_key}_{card_name}",
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
                options=expense_cats or ["General"],
                default=expense_cats[0] if expense_cats else "General",
                required=True,
            ),
            "Amount": st.column_config.NumberColumn(
                "Amount ($)", min_value=0.0, format="$%.2f", default=0.0
            ),
        },
    )

    if st.button("💾 Save Transactions", key=f"save_credit_{month_key}_{card_name}"):
        _sync_changes(orig, edited, month_key, card_name)

    # ── Spending breakdown chart ──────────────────────────────────────────────
    if not tx.empty:
        try:
            import plotly.express as px

            st.markdown("---")
            st.markdown("##### 📊 Spending Breakdown")
            cat_totals = tx.groupby("Category")["Amount"].sum().reset_index()
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
                height=320,
                margin=dict(t=20, b=20),
            )
            st.plotly_chart(fig, use_container_width=True)
        except ImportError:
            pass


def _build_display(tx):
    """Prepare the Credit Transactions dataframe for the data editor."""
    cols = ["_SheetRow", "Date", "Description", "Category", "Amount"]
    if tx.empty:
        return pd.DataFrame(
            {
                "_SheetRow": pd.Series([], dtype="Int64"),
                "Date": pd.Series([], dtype="str"),
                "Description": pd.Series([], dtype="str"),
                "Category": pd.Series([], dtype="str"),
                "Amount": pd.Series([], dtype="float"),
            }
        )
    df = tx.copy().reset_index(drop=True)
    df["Date"] = df["Date"].dt.strftime("%m/%d")
    df["Description"] = df.get("Description", "").fillna("").astype(str)
    df["Amount"] = df["Amount"].astype(float).round(2)
    return df[cols]


def _sync_changes(orig, edited, month_key, card_name):
    orig_len = len(orig)
    saved = 0

    with st.spinner("Saving…"):
        for idx in range(len(edited)):
            row = edited.iloc[idx]
            amt = row.get("Amount", 0)
            date_val = str(row.get("Date", "")).strip()
            if pd.isna(amt) or amt == 0 or date_val in ("", "nan", "NaT", "None"):
                continue
            cat = row.get("Category") or "General"

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
                    update_credit_tx_row(
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
                append_credit_tx(
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
