"""
Shared utility functions used across components.
"""

import datetime

import pandas as pd

# ── Pay period helpers ────────────────────────────────────────────────────────

# Anchor date: a known Monday that starts a pay period.
# Adjust this to match YOUR actual pay schedule.
PAY_PERIOD_ANCHOR = datetime.date(2026, 2, 9)  # a known Monday start


def get_pay_period_start(date: datetime.date) -> datetime.date:
    """Return the Monday that begins the 14-day pay period containing `date`."""
    delta = (date - PAY_PERIOD_ANCHOR).days
    period_number = delta // 14
    return PAY_PERIOD_ANCHOR + datetime.timedelta(days=period_number * 14)


def get_pay_period_label(start: datetime.date) -> str:
    end = start + datetime.timedelta(days=13)
    return f"{start.strftime('%b %d')} – {end.strftime('%b %d, %Y')}"


def get_all_pay_periods(df: pd.DataFrame) -> list[datetime.date]:
    """Return sorted unique pay-period start dates found in the dataframe."""
    if df.empty:
        return []
    starts = df["Date"].dt.date.apply(get_pay_period_start)
    return sorted(starts.unique(), reverse=True)


# ── Month helpers ─────────────────────────────────────────────────────────────


def get_all_months(df: pd.DataFrame) -> list[datetime.date]:
    """Return sorted unique (year, month) period starts from a transactions df."""
    if df.empty:
        return []
    months = df["Date"].dt.to_period("M").dt.to_timestamp().dt.date.unique()
    return sorted(months, reverse=True)


def month_label(d: datetime.date) -> str:
    return datetime.date(d.year, d.month, 1).strftime("%B %Y")


# ── Balance helpers ───────────────────────────────────────────────────────────


def compute_monthly_balance(
    transactions: pd.DataFrame,
    starting_balances: pd.DataFrame,
    account: str,
    year: int,
    month: int,
) -> dict:
    """
    Returns a dict with keys: starting, income, expenses, ending.
    Looks up a manual starting balance override; otherwise uses the
    prior month's ending balance (recursive for one step).
    """
    # Check for manual override
    manual = pd.DataFrame()
    if not starting_balances.empty:
        manual = starting_balances[
            (starting_balances["Month"].dt.year == year)
            & (starting_balances["Month"].dt.month == month)
            & (starting_balances["Account"] == account)
        ]

    if not manual.empty and pd.notna(manual.iloc[0]["Starting Balance"]):
        starting = float(manual.iloc[0]["Starting Balance"])
    else:
        # Use prior month's ending as starting
        if month == 1:
            prior_year, prior_month = year - 1, 12
        else:
            prior_year, prior_month = year, month - 1

        prior = compute_monthly_balance(
            transactions, starting_balances, account, prior_year, prior_month
        )
        starting = prior["ending"]

    mask = (
        (transactions["Account"] == account)
        & (transactions["Date"].dt.year == year)
        & (transactions["Date"].dt.month == month)
    )
    month_tx = transactions[mask]

    income = month_tx[month_tx["Type"] == "Income"]["Amount"].sum()
    expenses = month_tx[month_tx["Type"] == "Expense"]["Amount"].sum()
    transfers_in = month_tx[
        (month_tx["Type"] == "Transfer") & (month_tx["Amount"] > 0)
    ]["Amount"].sum()
    transfers_out = month_tx[
        (month_tx["Type"] == "Transfer") & (month_tx["Amount"] < 0)
    ]["Amount"].sum()

    ending = starting + income - expenses + transfers_in + transfers_out

    return {
        "starting": starting,
        "income": income,
        "expenses": expenses,
        "ending": ending,
    }
