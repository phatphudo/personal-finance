import streamlit as st

from utils.gsheets import read_settings, write_settings

# The canonical ordered list of setting keys
SETTING_KEYS = [
    "Hourly Rate Names",
    "Hourly Rate Values",
    "Cash Sources",
    "Bank Accounts",
    "Credit Cards",
    "Spending Categories",
    "Income Categories",
]

SETTING_DESCRIPTIONS = {
    "Hourly Rate Names": "Labels for each hourly rate (e.g. Base, Raise, Holiday)",
    "Hourly Rate Values": "Dollar value for each rate — must match order above (e.g. 18.50)",
    "Cash Sources": "Your cash buckets (e.g. Vault, Wallet, Reserve)",
    "Bank Accounts": "Bank / debit accounts (e.g. Main Checking)",
    "Credit Cards": "Credit card names (e.g. Amex Blue, Chase Sapphire)",
    "Spending Categories": "Expense categories (e.g. Rent, Groceries, Auto)",
    "Income Categories": "Income types (e.g. Paycheck, Tips, Cashback)",
}


def _list_editor(label: str, description: str, items: list[str], key: str) -> list[str]:
    """Render an editable text area for a list of items (one per line)."""
    st.markdown(f"**{label}**")
    st.caption(description)
    raw = st.text_area(
        label,
        value="\n".join(str(x) for x in items),
        height=120,
        label_visibility="collapsed",
        key=key,
        placeholder="One item per line…",
    )
    return [line.strip() for line in raw.splitlines() if line.strip()]


def render():
    st.markdown("## ⚙️ Settings")
    st.markdown(
        "Configure your hourly rates, accounts, and spending categories here. "
        "Changes are saved directly to your Google Sheet."
    )

    try:
        settings = read_settings()
    except Exception as e:
        st.error(f"Could not load settings: {e}")
        settings = {}

    # Ensure all keys exist (first-run or empty sheet)
    for key in SETTING_KEYS:
        if key not in settings:
            settings[key] = []

    st.markdown("---")

    # ── Hourly Rates (paired columns) ─────────────────────────────────────
    st.markdown("### ⏱️ Hourly Rates")
    st.caption(
        "Add one rate per line. The **Names** and **Values** lists must have the same number of entries."
    )
    col_name, col_val = st.columns(2)
    with col_name:
        new_rate_names = _list_editor(
            "Hourly Rate Names",
            SETTING_DESCRIPTIONS["Hourly Rate Names"],
            settings["Hourly Rate Names"],
            key="set_rate_names",
        )
    with col_val:
        new_rate_values = _list_editor(
            "Hourly Rate Values",
            SETTING_DESCRIPTIONS["Hourly Rate Values"],
            settings["Hourly Rate Values"],
            key="set_rate_values",
        )

    if len(new_rate_names) != len(new_rate_values):
        st.warning(
            f"⚠️ Mismatch: {len(new_rate_names)} name(s) vs {len(new_rate_values)} value(s). "
            "Make sure both lists have the same number of lines."
        )

    # ── Cash sources ──────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🪙 Cash Sources")
    new_cash = _list_editor(
        "Cash Sources",
        SETTING_DESCRIPTIONS["Cash Sources"],
        settings["Cash Sources"],
        key="set_cash",
    )

    # ── Bank accounts ─────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🏦 Bank / Debit Accounts")
    new_banks = _list_editor(
        "Bank Accounts",
        SETTING_DESCRIPTIONS["Bank Accounts"],
        settings["Bank Accounts"],
        key="set_banks",
    )

    # ── Credit cards ──────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 💳 Credit Cards")
    new_cards = _list_editor(
        "Credit Cards",
        SETTING_DESCRIPTIONS["Credit Cards"],
        settings["Credit Cards"],
        key="set_cards",
    )

    # ── Categories ────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🏷️ Transaction Categories")
    col_inc, col_exp = st.columns(2)
    with col_inc:
        new_income_cats = _list_editor(
            "Income Categories",
            SETTING_DESCRIPTIONS["Income Categories"],
            settings["Income Categories"],
            key="set_income_cats",
        )
    with col_exp:
        new_expense_cats = _list_editor(
            "Spending Categories",
            SETTING_DESCRIPTIONS["Spending Categories"],
            settings["Spending Categories"],
            key="set_expense_cats",
        )

    # ── Save ──────────────────────────────────────────────────────────────
    st.markdown("---")
    if st.button("💾 Save All Settings", type="primary", width='stretch'):
        updated = {
            "Hourly Rate Names": new_rate_names,
            "Hourly Rate Values": new_rate_values,
            "Cash Sources": new_cash,
            "Bank Accounts": new_banks,
            "Credit Cards": new_cards,
            "Spending Categories": new_expense_cats,
            "Income Categories": new_income_cats,
        }
        with st.spinner("Saving to Google Sheets…"):
            write_settings(updated)
        st.success("✅ Settings saved successfully!")
        st.rerun()
