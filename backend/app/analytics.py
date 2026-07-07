"""Behavioral analytics over raw transactions.

The synthetic data layer generates transactions as a bank statement would
arrive: date, narration, amount, direction — NO category labels. This module
derives everything downstream from those raw narrations:

- `categorize`: a merchant/narration classifier (rules engine over UPI/NEFT/
  ACH/card narration tokens — the same approach production spend-categorizers
  bootstrap with before an ML model takes over).
- `behavioral_profile`: 12-month behavioural signals per customer — income
  stability, savings rate, SIP discipline, discretionary share — plus a
  behavioural segment label. These signals feed the suitability engine and
  the advisory brain, which is what makes recommendations *behaviour-derived*
  rather than profile-form-derived.
"""

from statistics import mean, pstdev

# Narration-token rules, first match wins. Order matters: specific before broad
# (e.g. SIP before generic UPI merchants).
MERCHANT_RULES = [
    (("SALARY",), "Income"),
    (("CLIENT PAYMENTS", "FREELANCE"), "Income"),
    (("BUSINESS DRAWINGS",), "Income"),
    (("SIP AUTO DEBIT", "SIP -"), "SIP Investments"),
    (("RENT",), "Rent"),
    (("LOAN EMI", "MORTGAGE EMI"), "Loan EMI"),
    (("PREMIUM",), "Insurance Premiums"),
    (("FAMILY TRANSFER",), "Parents Support"),
    (("BIGBASKET", "ZEPTO", "BLINKIT", "DMART", "GROFERS"), "Groceries"),
    (("SWIGGY", "ZOMATO", "BOOKMYSHOW", "PVR", "SPOTIFY", "NETFLIX"), "Dining & Entertainment"),
    (("ELECTRICITY", "BROADBAND", "MOBILE", "OTT", "BILLDESK"), "Utilities & Bills"),
    (("AMAZON", "MYNTRA", "NYKAA", "FLIPKART"), "Shopping"),
    (("MAKEMYTRIP",), "Travel"),
    (("UBER", "OLA", "RAPIDO", "HPCL", "INDIGO", "IRCTC", "FUEL"), "Travel & Fuel"),
    (("ADOBE", "FIGMA",), "Software & Tools"),
    (("CLUB", "GOLF"), "Club & Lifestyle"),
    (("HOUSEHOLD", "SUPERMART"), "Household"),
]

DISCRETIONARY = {"Dining & Entertainment", "Shopping", "Travel", "Travel & Fuel", "Club & Lifestyle"}


def categorize(desc: str) -> str:
    """Classify one raw narration into a spend category."""
    d = desc.upper()
    for tokens, category in MERCHANT_RULES:
        if any(t in d for t in tokens):
            return category
    return "Other"


def categorize_all(transactions: list) -> dict:
    """Label every transaction in place; returns classifier coverage stats."""
    hits = 0
    for t in transactions:
        t["category"] = categorize(t["desc"])
        if t["category"] != "Other":
            hits += 1
    return {"classified": hits, "total": len(transactions),
            "coverage_pct": round(hits / max(len(transactions), 1) * 100, 1)}


def behavioral_profile(customer: dict) -> dict:
    """12-month behavioural signals derived purely from raw transactions."""
    txns = customer["transactions"]

    # Monthly income series from credits (not from the profile field)
    monthly_credits: dict[str, float] = {}
    monthly_debits: dict[str, float] = {}
    sip_months = set()
    debit_by_cat: dict[str, float] = {}
    for t in txns:
        month = t["date"][:7]
        if t["type"] == "credit":
            monthly_credits[month] = monthly_credits.get(month, 0) + t["amount"]
        else:
            monthly_debits[month] = monthly_debits.get(month, 0) + t["amount"]
            debit_by_cat[t["category"]] = debit_by_cat.get(t["category"], 0) + t["amount"]
            if t["category"] == "SIP Investments":
                sip_months.add(month)

    credits = list(monthly_credits.values())
    income_avg = mean(credits) if credits else 0
    income_cv = round(pstdev(credits) / income_avg, 3) if income_avg else 0  # coefficient of variation
    income_stability = "Stable" if income_cv < 0.05 else "Somewhat variable" if income_cv < 0.15 else "Variable"

    total_credits = sum(credits)
    total_debits = sum(monthly_debits.values())
    savings_rate = round((total_credits - total_debits) / total_credits, 3) if total_credits else 0
    sip_discipline = round(len(sip_months) / max(len(monthly_credits), 1), 2)
    discretionary = sum(v for k, v in debit_by_cat.items() if k in DISCRETIONARY)
    non_sip_debits = total_debits - debit_by_cat.get("SIP Investments", 0)
    discretionary_ratio = round(discretionary / non_sip_debits, 3) if non_sip_debits else 0

    if sip_discipline >= 0.9 and savings_rate >= 0.25:
        segment = "Disciplined accumulator"
    elif income_stability != "Stable" and savings_rate >= 0.2:
        segment = "Variable-income saver"
    elif discretionary_ratio > 0.35:
        segment = "Lifestyle spender"
    else:
        segment = "Steady saver"

    return {
        "derived_from": f"{len(txns)} raw transactions over {len(monthly_credits)} months (narration-classified, no pre-labels)",
        "behavioral_segment": segment,
        "income_stability": income_stability,
        "income_variation_coefficient": income_cv,
        "avg_monthly_income_observed": round(income_avg),
        "savings_rate_pct": round(savings_rate * 100, 1),
        "sip_discipline_pct": round(sip_discipline * 100),
        "discretionary_spend_ratio_pct": round(discretionary_ratio * 100, 1),
        "signals": [s for s in [
            f"Income is {income_stability.lower()} (month-to-month variation {income_cv:.0%})",
            f"Saves {savings_rate * 100:.0f}% of inflows on average",
            f"SIP debited in {round(sip_discipline * 100)}% of months — {'strong' if sip_discipline >= 0.9 else 'inconsistent'} investing discipline",
            f"{discretionary_ratio * 100:.0f}% of non-SIP spending is discretionary",
        ]],
    }
