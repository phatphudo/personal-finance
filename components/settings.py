import streamlit as st

from utils.gsheets import read_settings, write_settings

# The canonical ordered list of setting keys
SETTING_KEYS = [
    "Default Current Rate",
    "Default Expected Rate",
    "Cash Sources",
    "Bank Accounts",
    "Credit Cards",
    "Spending Categories",
    "Income Categories",
]

SETTING_DESCRIPTIONS = {
    "Default Current Rate": "Default current hourly rate for new pay periods (e.g. 18.50)",
    "Default Expected Rate": "Default expected/raise hourly rate for new pay periods (e.g. 19.00)",
    "Cash Sources": "Your cash buckets (e.g. Vault, Wallet, Reserve)",
    "Bank Accounts": "Bank / debit accounts (e.g. Main Checking)",
    "Credit Cards": "Credit card names (e.g. Amex Blue, Chase Sapphire)",
    "Spending Categories": "Expense categories (e.g. Rent, Groceries, Auto)",
    "Income Categories": "Income types (e.g. Paycheck, Tips, Cashback)",
}

DEFAULT_CURRENT_RATE = 19.50
DEFAULT_EXPECTED_RATE = 20.00


def get_default_rates(settings: dict) -> tuple[float, float]:
    """Return (default_current_rate, default_expected_rate) from settings."""
    try:
        cur = float(settings.get("Default Current Rate", [DEFAULT_CURRENT_RATE])[0])
    except (TypeError, ValueError, IndexError):
        cur = DEFAULT_CURRENT_RATE
    try:
        exp = float(settings.get("Default Expected Rate", [DEFAULT_EXPECTED_RATE])[0])
    except (TypeError, ValueError, IndexError):
        exp = DEFAULT_EXPECTED_RATE
    return cur, exp


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
        "Configure your default hourly rates, accounts, and spending categories here. "
        "Changes are saved directly to your Google Sheet."
    )

    try:
        settings = read_settings()
    except Exception as e:
        st.error(f"Could not load settings: {e}")
        settings = {}

    # Ensure all keys exist
    for key in SETTING_KEYS:
        if key not in settings:
            settings[key] = []

    st.markdown("---")

    # ── Default Hourly Rates ──────────────────────────────────────────────
    st.markdown("### ⏱️ Default Hourly Rates")
    st.caption(
        "These are the **default** rates used when a new pay period is created. "
        "You can override rates per-period in the **Current Pay Period** view."
    )
    default_cur, default_exp = get_default_rates(settings)
    col_cur, col_exp = st.columns(2)
    with col_cur:
        st.markdown("**Default Current Rate ($)**")
        new_cur = st.number_input(
            "Default Current Rate",
            value=default_cur,
            min_value=0.0,
            step=0.25,
            format="%.2f",
            label_visibility="collapsed",
            key="set_default_cur_rate",
        )
    with col_exp:
        st.markdown("**Default Expected Rate ($)**")
        new_exp = st.number_input(
            "Default Expected Rate",
            value=default_exp,
            min_value=0.0,
            step=0.25,
            format="%.2f",
            label_visibility="collapsed",
            key="set_default_exp_rate",
        )

    # ── Cash sources ──────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🪙 Cash Sources")
    new_cash = _list_editor(
        "Cash Sources",
        SETTING_DESCRIPTIONS["Cash Sources"],
        settings.get("Cash Sources", []),
        key="set_cash",
    )

    # ── Bank accounts ─────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🏦 Bank / Debit Accounts")
    new_banks = _list_editor(
        "Bank Accounts",
        SETTING_DESCRIPTIONS["Bank Accounts"],
        settings.get("Bank Accounts", []),
        key="set_banks",
    )

    # ── Credit cards ──────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 💳 Credit Cards")
    new_cards = _list_editor(
        "Credit Cards",
        SETTING_DESCRIPTIONS["Credit Cards"],
        settings.get("Credit Cards", []),
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
            settings.get("Income Categories", []),
            key="set_income_cats",
        )
    with col_exp:
        new_expense_cats = _list_editor(
            "Spending Categories",
            SETTING_DESCRIPTIONS["Spending Categories"],
            settings.get("Spending Categories", []),
            key="set_expense_cats",
        )

    # ── Save ──────────────────────────────────────────────────────────────
    st.markdown("---")
    if st.button("💾 Save All Settings", type="primary", width="stretch"):
        updated = {
            "Default Current Rate": [new_cur],
            "Default Expected Rate": [new_exp],
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
