"""Synthetic bank data layer for the Saarthi prototype.

Generates a deterministic, realistic mini-bank: customers across segments,
accounts, categorized transactions, holdings, loans and joint-account links.
Round-1 submissions use self-generated synthetic data per IDBI's instructions.
"""

import random
from datetime import date, timedelta

random.seed(42)

TODAY = date.today()

MF_SCHEMES = [
    {"name": "IDBI Nifty 50 Index Fund", "class": "Equity - Large Cap", "risk": "Moderate", "cagr3y": 14.2},
    {"name": "IDBI Flexi Cap Fund", "class": "Equity - Flexi Cap", "risk": "Moderately High", "cagr3y": 16.8},
    {"name": "IDBI Midcap Opportunities Fund", "class": "Equity - Mid Cap", "risk": "High", "cagr3y": 21.4},
    {"name": "IDBI Corporate Bond Fund", "class": "Debt - Corporate Bond", "risk": "Low to Moderate", "cagr3y": 7.1},
    {"name": "IDBI Balanced Advantage Fund", "class": "Hybrid - Dynamic", "risk": "Moderate", "cagr3y": 11.6},
    {"name": "IDBI ELSS Tax Saver Fund", "class": "Equity - ELSS", "risk": "Moderately High", "cagr3y": 15.9},
    {"name": "IDBI Liquid Fund", "class": "Debt - Liquid", "risk": "Low", "cagr3y": 6.4},
]

PRODUCT_CATALOG = {
    "vanilla": [
        {"product": "Fixed Deposit (Amrit Mahotsav 444 days)", "rate": "7.35% p.a.", "type": "FD"},
        {"product": "Recurring Deposit", "rate": "6.80% p.a.", "type": "RD"},
        {"product": "Mutual Fund SIPs (direct, execution-only)", "rate": "market linked", "type": "MF"},
        {"product": "Public Provident Fund (PPF)", "rate": "7.10% p.a.", "type": "PPF"},
        {"product": "National Pension System (NPS)", "rate": "market linked", "type": "NPS"},
        {"product": "Sukanya Samriddhi Yojana", "rate": "8.20% p.a.", "type": "SSY"},
    ],
    "regulated": [
        {"product": "Term / Life Insurance (LIC, Ageas Federal)", "note": "IRDAI regulated - requires certified advisor"},
        {"product": "ULIPs", "note": "IRDAI regulated - requires certified advisor"},
        {"product": "Health Insurance", "note": "IRDAI regulated - requires certified advisor"},
        {"product": "Portfolio Management Services (PMS)", "note": "SEBI regulated - requires RIA/RM"},
        {"product": "Structured products / AIFs", "note": "SEBI regulated - requires RIA/RM"},
        {"product": "Demat / direct equity advisory", "note": "SEBI regulated - requires certified advisor"},
    ],
}

LOAN_RATES = {"home": 8.45, "auto": 9.10, "personal": 10.75, "education": 9.25, "mortgage": 9.00}


def _months_back(n):
    """First-of-month dates for the last n months, oldest first."""
    out = []
    y, m = TODAY.year, TODAY.month
    for _ in range(n):
        m -= 1
        if m == 0:
            m, y = 12, y - 1
        out.append(date(y, m, 1))
    return list(reversed(out))


def _gen_transactions(income, profile):
    """12 months of categorized transactions from a spending profile."""
    txns = []
    for month_start in _months_back(12):
        txns.append({
            "date": str(month_start + timedelta(days=0)),
            "desc": profile.get("income_desc", "SALARY CREDIT"),
            "category": "Income", "amount": round(income * random.uniform(0.97, 1.03) if profile.get("variable_income") else income),
            "type": "credit",
        })
        for cat, (lo, hi, desc) in profile["spends"].items():
            amt = round(random.uniform(lo, hi))
            if amt > 0:
                txns.append({
                    "date": str(month_start + timedelta(days=random.randint(2, 26))),
                    "desc": desc, "category": cat, "amount": amt, "type": "debit",
                })
    return txns


def _holdings(picks):
    out = []
    for scheme_idx, monthly_sip, months in picks:
        s = MF_SCHEMES[scheme_idx]
        invested = monthly_sip * months
        current = round(invested * (1 + s["cagr3y"] / 100 * months / 24 * random.uniform(0.85, 1.1)))
        out.append({
            "type": "Mutual Fund", "name": s["name"], "asset_class": s["class"],
            "sip_monthly": monthly_sip, "invested": invested, "current": current,
            "returns_pct": round((current - invested) / invested * 100, 1),
        })
    return out


CUSTOMERS = {
    "C001": {
        "id": "C001", "name": "Rohan Sharma", "age": 32, "gender": "M",
        "occupation": "Software Engineer, salaried", "segment": "Mass Affluent",
        "risk_profile": "Moderate", "monthly_income": 185000,
        "partner_id": "C002", "joint_account": True,
        "savings_balance": 412000,
        "fd": [{"amount": 300000, "rate": 7.35, "maturity": "2027-03-15"}],
        "nps": 260000, "epf": 780000,
        "holdings": _holdings([(0, 15000, 30), (1, 10000, 24), (3, 5000, 18)]),
        "loans": [{"type": "Car Loan", "outstanding": 340000, "emi": 14200, "ends": "2028-08-01"}],
        "goals": [
            {"name": "Home down payment", "target": 3000000, "by": "2028-12", "saved": 950000, "joint": True},
            {"name": "Japan trip", "target": 400000, "by": "2027-04", "saved": 140000, "joint": True},
        ],
        "spend_profile": {
            "spends": {
                "Rent": (45000, 45000, "RENT TRANSFER - NOBROKER"),
                "SIP Investments": (30000, 30000, "SIP AUTO DEBIT - MF"),
                "Groceries": (9000, 14000, "UPI - BIGBASKET/ZEPTO"),
                "Dining & Entertainment": (8000, 16000, "UPI - SWIGGY/BOOKMYSHOW"),
                "Utilities & Bills": (4500, 7000, "BILLDESK - ELECTRICITY/BROADBAND"),
                "Shopping": (5000, 18000, "AMAZON/MYNTRA"),
                "Travel & Fuel": (4000, 9000, "UPI - UBER/HPCL"),
                "Loan EMI": (14200, 14200, "ACH DEBIT - CAR LOAN EMI"),
            }
        },
    },
    "C002": {
        "id": "C002", "name": "Priya Sharma", "age": 30, "gender": "F",
        "occupation": "Marketing Manager, salaried", "segment": "Mass Affluent",
        "risk_profile": "Moderately Aggressive", "monthly_income": 140000,
        "partner_id": "C001", "joint_account": True,
        "savings_balance": 356000,
        "fd": [], "nps": 0, "epf": 510000,
        "holdings": _holdings([(2, 12000, 20), (5, 12500, 24)]),
        "loans": [],
        "goals": [
            {"name": "Home down payment", "target": 3000000, "by": "2028-12", "saved": 950000, "joint": True},
            {"name": "Sabbatical fund", "target": 900000, "by": "2027-10", "saved": 310000, "joint": False},
        ],
        "spend_profile": {
            "spends": {
                "SIP Investments": (24500, 24500, "SIP AUTO DEBIT - MF"),
                "Groceries": (7000, 11000, "UPI - BLINKIT"),
                "Dining & Entertainment": (9000, 15000, "UPI - ZOMATO/PVR"),
                "Utilities & Bills": (2500, 4000, "BILLDESK - MOBILE/OTT"),
                "Shopping": (8000, 22000, "NYKAA/AMAZON"),
                "Travel & Fuel": (5000, 9000, "UPI - OLA/INDIGO"),
                "Parents Support": (15000, 15000, "IMPS - FAMILY TRANSFER"),
            }
        },
    },
    "C003": {
        "id": "C003", "name": "Anil Mehta", "age": 54, "gender": "M",
        "occupation": "Business Owner - Textiles", "segment": "HNI",
        "risk_profile": "Conservative", "monthly_income": 650000,
        "partner_id": None, "joint_account": False,
        "savings_balance": 3850000,
        "fd": [{"amount": 5000000, "rate": 7.35, "maturity": "2027-01-10"},
                {"amount": 2500000, "rate": 7.10, "maturity": "2026-11-20"}],
        "nps": 0, "epf": 0,
        "holdings": _holdings([(3, 100000, 30), (4, 75000, 30), (0, 50000, 24)]),
        "loans": [{"type": "Business Mortgage", "outstanding": 8200000, "emi": 128000, "ends": "2031-05-01"}],
        "goals": [
            {"name": "Daughter's wedding", "target": 5000000, "by": "2028-06", "saved": 2100000, "joint": False},
            {"name": "Retirement corpus", "target": 60000000, "by": "2034-01", "saved": 21400000, "joint": False},
        ],
        "spend_profile": {
            "income_desc": "BUSINESS DRAWINGS - MEHTA TEXTILES", "variable_income": True,
            "spends": {
                "SIP Investments": (225000, 225000, "SIP AUTO DEBIT - MF"),
                "Household": (60000, 95000, "MIXED UPI/CARD"),
                "Loan EMI": (128000, 128000, "ACH DEBIT - MORTGAGE EMI"),
                "Club & Lifestyle": (25000, 60000, "CARD - CLUB/GOLF"),
                "Travel": (20000, 120000, "MAKEMYTRIP/CARD"),
                "Insurance Premiums": (18000, 18000, "ACH - PREMIUM DEBIT"),
            }
        },
    },
    "C004": {
        "id": "C004", "name": "Meera Iyer", "age": 27, "gender": "F",
        "occupation": "Freelance Product Designer", "segment": "Mass",
        "risk_profile": "Aggressive", "monthly_income": 95000,
        "partner_id": None, "joint_account": False,
        "savings_balance": 168000,
        "fd": [], "nps": 0, "epf": 0,
        "holdings": _holdings([(2, 8000, 14), (1, 5000, 10)]),
        "loans": [],
        "goals": [
            {"name": "Emergency fund", "target": 500000, "by": "2027-06", "saved": 130000, "joint": False},
            {"name": "MacBook + studio setup", "target": 350000, "by": "2026-12", "saved": 90000, "joint": False},
        ],
        "spend_profile": {
            "income_desc": "NEFT - CLIENT PAYMENTS (FREELANCE)", "variable_income": True,
            "spends": {
                "Rent": (28000, 28000, "UPI - RENT"),
                "SIP Investments": (13000, 13000, "SIP AUTO DEBIT - MF"),
                "Groceries": (5000, 8000, "UPI - DMART/ZEPTO"),
                "Dining & Entertainment": (6000, 14000, "UPI - SWIGGY/SPOTIFY"),
                "Software & Tools": (3000, 6000, "CARD - ADOBE/FIGMA"),
                "Shopping": (3000, 12000, "AMAZON"),
                "Travel & Fuel": (3000, 7000, "UPI - RAPIDO/UBER"),
            }
        },
    },
}

# Pre-generate transactions once (deterministic via seed)
for c in CUSTOMERS.values():
    c["transactions"] = _gen_transactions(c["monthly_income"], c["spend_profile"])

# In-memory RM lead queue (prototype scope; RDS/DynamoDB in production architecture)
LEADS = []


def get_customer(cid):
    return CUSTOMERS.get(cid)


def list_customers():
    return [
        {k: c[k] for k in ("id", "name", "age", "occupation", "segment", "risk_profile", "joint_account", "partner_id")}
        for c in CUSTOMERS.values()
    ]


def _monthly_avg_expenses(c):
    debits = [t for t in c["transactions"] if t["type"] == "debit" and t["category"] != "SIP Investments"]
    return round(sum(t["amount"] for t in debits) / 12)


def _spend_by_category(c):
    out = {}
    for t in c["transactions"]:
        if t["type"] == "debit":
            out[t["category"]] = out.get(t["category"], 0) + t["amount"]
    return {k: round(v / 12) for k, v in sorted(out.items(), key=lambda kv: -kv[1])}


def portfolio_summary(cid):
    c = get_customer(cid)
    if not c:
        return None
    mf_current = sum(h["current"] for h in c["holdings"])
    mf_invested = sum(h["invested"] for h in c["holdings"])
    fd_total = sum(f["amount"] for f in c["fd"])
    assets = c["savings_balance"] + mf_current + fd_total + c["nps"] + c["epf"]
    liabilities = sum(l["outstanding"] for l in c["loans"])
    return {
        "customer": {k: c[k] for k in ("id", "name", "age", "occupation", "segment", "risk_profile", "monthly_income", "joint_account", "partner_id")},
        "net_worth": assets - liabilities,
        "total_assets": assets, "total_liabilities": liabilities,
        "allocation": {
            "Savings": c["savings_balance"], "Fixed Deposits": fd_total,
            "Mutual Funds": mf_current, "NPS": c["nps"], "EPF": c["epf"],
        },
        "holdings": c["holdings"], "fd": c["fd"], "loans": c["loans"], "goals": c["goals"],
        "mf_invested": mf_invested, "mf_current": mf_current,
        "monthly_sip": sum(h["sip_monthly"] for h in c["holdings"]),
        "avg_monthly_expenses": _monthly_avg_expenses(c),
        "spend_by_category": _spend_by_category(c),
    }


def household_summary(cid):
    c = get_customer(cid)
    if not c or not c["partner_id"]:
        return None
    p1, p2 = portfolio_summary(cid), portfolio_summary(c["partner_id"])
    alloc = {k: p1["allocation"][k] + p2["allocation"][k] for k in p1["allocation"]}
    joint_goals = [g for g in p1["goals"] if g.get("joint")]
    return {
        "members": [p1["customer"], p2["customer"]],
        "net_worth": p1["net_worth"] + p2["net_worth"],
        "total_assets": p1["total_assets"] + p2["total_assets"],
        "total_liabilities": p1["total_liabilities"] + p2["total_liabilities"],
        "combined_income": p1["customer"]["monthly_income"] + p2["customer"]["monthly_income"],
        "combined_expenses": p1["avg_monthly_expenses"] + p2["avg_monthly_expenses"],
        "combined_sip": p1["monthly_sip"] + p2["monthly_sip"],
        "allocation": alloc, "joint_goals": joint_goals,
        "individual": {cid: p1, c["partner_id"]: p2},
    }


def loan_affordability(cid, loan_amount, tenure_years, loan_type="home", household=False):
    """EMI + FOIR-based affordability, individually or as a household."""
    rate = LOAN_RATES.get(loan_type, 9.5)
    r = rate / 12 / 100
    n = int(tenure_years * 12)
    emi = round(loan_amount * r * (1 + r) ** n / ((1 + r) ** n - 1))

    if household:
        h = household_summary(cid)
        if not h:
            household = False
    if household:
        income, expenses = h["combined_income"], h["combined_expenses"]
        existing_emi = sum(l["emi"] for m in h["individual"].values() for l in m["loans"])
        who = " + ".join(m["name"] for m in h["members"])
    else:
        p = portfolio_summary(cid)
        income, expenses = p["customer"]["monthly_income"], p["avg_monthly_expenses"]
        existing_emi = sum(l["emi"] for l in p["loans"])
        who = p["customer"]["name"]

    foir = round((existing_emi + emi) / income * 100, 1)  # banks cap ~50-55%
    surplus_after = income - expenses - emi  # expenses already include existing EMIs
    verdict = "COMFORTABLE" if foir <= 40 else "AFFORDABLE_WITH_CARE" if foir <= 52 else "STRETCHED"
    return {
        "assessed_for": who, "household_mode": household, "loan_type": loan_type,
        "loan_amount": loan_amount, "tenure_years": tenure_years, "interest_rate_pct": rate,
        "emi": emi, "existing_emi": existing_emi, "monthly_income": income,
        "avg_monthly_expenses_incl_existing_emi": expenses,
        "foir_pct": foir, "foir_bank_cap_pct": 52,
        "monthly_surplus_after_new_emi": surplus_after,
        "total_interest_payable": emi * n - loan_amount, "verdict": verdict,
    }


def plan_goal(cid, goal_name, household=False):
    """Deterministic goal math: months left, required monthly saving, fair splits."""
    c = get_customer(cid)
    goal = next((g for g in c["goals"] if goal_name.lower() in g["name"].lower()), None)
    if not goal:
        return {"error": f"No goal matching '{goal_name}'. Goals: {[g['name'] for g in c['goals']]}"}
    y, m = map(int, goal["by"].split("-"))
    months_left = max(1, (y - TODAY.year) * 12 + m - TODAY.month)
    remaining = max(0, goal["target"] - goal["saved"])
    required_monthly = round(remaining / months_left)
    out = {
        "goal": goal["name"], "target": goal["target"], "saved": goal["saved"],
        "remaining": remaining, "deadline": goal["by"], "months_left": months_left,
        "required_monthly_saving": required_monthly,
    }
    if household and goal.get("joint") and c["partner_id"]:
        p = get_customer(c["partner_id"])
        total = c["monthly_income"] + p["monthly_income"]
        out["fair_split_options"] = {
            "equal_50_50": {c["name"]: round(required_monthly / 2), p["name"]: round(required_monthly / 2)},
            "income_proportional": {
                c["name"]: round(required_monthly * c["monthly_income"] / total),
                p["name"]: round(required_monthly * p["monthly_income"] / total),
            },
            "income_share_pct": {
                c["name"]: round(c["monthly_income"] / total * 100),
                p["name"]: round(p["monthly_income"] / total * 100),
            },
        }
    return out


def sip_target(cid, target_amount, years, expected_return_pct=12.0):
    """Inverse SIP calculator: monthly SIP needed to reach a target corpus."""
    c = get_customer(cid)
    r = expected_return_pct / 12 / 100
    n = max(1, int(years * 12))
    monthly = target_amount * r / ((1 + r) ** n - 1) if r > 0 else target_amount / n
    monthly = round(monthly)
    p = portfolio_summary(cid)
    surplus = c["monthly_income"] - p["avg_monthly_expenses"] - p["monthly_sip"]
    return {
        "target_amount": target_amount, "years": years,
        "expected_return_pct": expected_return_pct,
        "required_monthly_sip": monthly,
        "total_invested": monthly * n,
        "wealth_gained": round(target_amount - monthly * n),
        "current_monthly_surplus": surplus,
        "fits_in_surplus": monthly <= surplus,
    }


def retirement_projection(cid, retirement_age=60, household=False):
    """Project the retirement corpus from current assets + SIPs, compare with
    the inflation-adjusted corpus needed, and compute the extra SIP to close
    any gap. Assumptions: equity/SIP 12% p.a., EPF/NPS/FD 8% p.a., inflation
    6% p.a., corpus need = 25x first-year retirement expenses (4% rule)."""
    members = [cid]
    c = get_customer(cid)
    if household and c["partner_id"]:
        members.append(c["partner_id"])

    years_left = max(1, retirement_age - max(get_customer(m)["age"] for m in members))
    n = years_left * 12
    r_eq, r_debt, inflation = 0.12 / 12, 0.08 / 12, 0.06

    corpus, monthly_sip, expenses = 0, 0, 0
    for m in members:
        p = portfolio_summary(m)
        cm = get_customer(m)
        eq_now = p["mf_current"]
        debt_now = p["allocation"]["Fixed Deposits"] + cm["nps"] + cm["epf"] + cm["savings_balance"]
        corpus += eq_now * (1 + r_eq) ** n + debt_now * (1 + r_debt) ** n
        corpus += p["monthly_sip"] * (((1 + r_eq) ** n - 1) / r_eq)
        monthly_sip += p["monthly_sip"]
        expenses += p["avg_monthly_expenses"]

    corpus = round(corpus)
    future_monthly_expenses = round(expenses * (1 + inflation) ** years_left)
    corpus_needed = future_monthly_expenses * 12 * 25  # 4% withdrawal rule
    gap = corpus_needed - corpus
    extra_sip = round(gap * r_eq / ((1 + r_eq) ** n - 1)) if gap > 0 else 0
    return {
        "assessed_for": [get_customer(m)["name"] for m in members],
        "retirement_age": retirement_age, "years_to_retirement": years_left,
        "projected_corpus": corpus,
        "current_monthly_sip": monthly_sip,
        "todays_monthly_expenses": expenses,
        "monthly_expenses_at_retirement_inflation_adjusted": future_monthly_expenses,
        "corpus_needed_4pct_rule": corpus_needed,
        "surplus_or_gap": corpus - corpus_needed,
        "on_track": corpus >= corpus_needed,
        "extra_monthly_sip_to_close_gap": extra_sip,
        "assumptions": "equity 12% p.a., debt/EPF/NPS 8% p.a., inflation 6% p.a., corpus = 25x first-year expenses",
    }


def tax_summary(cid):
    """Section 80C / 80CCD(1B) utilization from actual holdings and payroll."""
    c = get_customer(cid)
    elss_annual = sum(h["sip_monthly"] for h in c["holdings"] if "ELSS" in h["name"]) * 12
    # Employee EPF contribution ~12% of basic (basic ~40% of gross) for salaried
    epf_annual = round(c["monthly_income"] * 0.40 * 0.12) * 12 if c["epf"] > 0 else 0
    used_80c = min(150000, elss_annual + epf_annual)
    headroom_80c = 150000 - used_80c
    nps_50k_used = c["nps"] > 0  # simplification: NPS contributors use 80CCD(1B)
    headroom_80ccd1b = 0 if nps_50k_used else 50000
    # Marginal slab (new regime approx) just for savings framing
    annual_income = c["monthly_income"] * 12
    slab = 30 if annual_income > 2400000 else 25 if annual_income > 2000000 else 20 if annual_income > 1600000 else 15
    potential_saving = round((headroom_80c + headroom_80ccd1b) * slab / 100)
    return {
        "regime_note": "80C/80CCD apply under the old regime; figures are indicative for planning",
        "sec_80c": {"limit": 150000, "used": used_80c, "headroom": headroom_80c,
                     "components": {"ELSS SIPs (annual)": elss_annual, "EPF employee contribution (est.)": epf_annual}},
        "sec_80ccd_1b_nps": {"limit": 50000, "headroom": headroom_80ccd1b},
        "marginal_slab_pct": slab,
        "potential_annual_tax_saving": potential_saving,
        "suggested_actions": [a for a in [
            f"Invest ₹{headroom_80c:,} more in IDBI ELSS Tax Saver Fund to max out 80C" if headroom_80c > 0 else None,
            "Open NPS and claim the extra ₹50,000 deduction under 80CCD(1B)" if headroom_80ccd1b > 0 else None,
        ] if a],
    }


def financial_health(cid):
    """Financial Health Score (0-100) across four measurable pillars."""
    c = get_customer(cid)
    p = portfolio_summary(cid)

    # 1. Emergency buffer: months of expenses covered by savings (target 6)
    months = c["savings_balance"] / max(p["avg_monthly_expenses"], 1)
    s_emergency = round(min(months / 6, 1) * 25)

    # 2. Diversification: equity share vs age-appropriate ideal (100 - age)
    eq = sum(h["current"] for h in p["holdings"] if "Equity" in h["asset_class"] or "Hybrid" in h["asset_class"])
    eq_pct = eq / p["total_assets"] * 100 if p["total_assets"] else 0
    ideal = max(20, min(70, 100 - c["age"]))
    s_divers = round(max(0, 1 - abs(eq_pct - ideal) / ideal) * 25)

    # 3. Debt headroom: existing FOIR vs the ~52% bank cap
    existing_emi = sum(l["emi"] for l in c["loans"])
    foir = existing_emi / c["monthly_income"] * 100
    s_debt = round(max(0, 1 - foir / 52) * 25)

    # 4. Goal funding: average % funded across saved goals
    funded = [min(g["saved"] / g["target"], 1) for g in c["goals"]] or [0]
    s_goals = round(sum(funded) / len(funded) * 25)

    score = s_emergency + s_divers + s_debt + s_goals
    grade = ("Excellent" if score >= 80 else "Good" if score >= 60
             else "Fair" if score >= 40 else "Needs attention")
    return {
        "score": score, "grade": grade,
        "pillars": [
            {"name": "Emergency buffer", "score": s_emergency, "max": 25,
             "detail": f"Savings cover {months:.1f} months of expenses (target 6)"},
            {"name": "Diversification", "score": s_divers, "max": 25,
             "detail": f"{eq_pct:.0f}% market-linked vs ~{ideal}% ideal for age {c['age']}"},
            {"name": "Debt headroom", "score": s_debt, "max": 25,
             "detail": f"Existing EMIs use {foir:.0f}% of income (bank cap ~52%)"},
            {"name": "Goal funding", "score": s_goals, "max": 25,
             "detail": f"Goals are {round(sum(funded) / len(funded) * 100)}% funded on average"},
        ],
    }


def create_lead(cid, product, context, household=False):
    c = get_customer(cid)
    lead = {
        "id": f"L{len(LEADS) + 1:03d}",
        "created": str(TODAY),
        "customer_id": cid, "customer_name": c["name"] if c else cid,
        "segment": c["segment"] if c else "-",
        "product": product, "context": context,
        "household": household, "status": "NEW",
        "priority": "HIGH" if c and c["segment"] == "HNI" else "NORMAL",
    }
    LEADS.append(lead)
    return lead
