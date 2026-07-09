"""Deterministic suitability engine with a per-recommendation audit trail.

SEBI-style suitability means a documented assessment — not a prompt asking the
model to "consider age and risk". This module is that assessment:

- Every investment product (MF schemes + vanilla deposit/pension products) is
  scored against the customer's measurable factors: risk band, age, horizon,
  monthly surplus, emergency buffer, current equity allocation, and the
  behaviour signals derived from raw transactions (income stability, SIP
  discipline).
- Output is a verdict (SUITABLE / SUITABLE_WITH_CAUTION / NOT_SUITABLE) with
  the explicit reasons, and EVERY assessment is appended to an audit log —
  "recommended X because profile=Y, horizon=Z" is queryable per customer.

The advisory agent must call this before recommending anything; the LLM
narrates the verdict, it does not produce it.
"""

from datetime import datetime

from . import analytics, data

RISK_BAND = {"Conservative": 2, "Moderate": 3, "Moderately Aggressive": 4, "Aggressive": 5}
PRODUCT_RISK = {"Low": 1, "Low to Moderate": 2, "Moderate": 3, "Moderately High": 4, "High": 5}

# Vanilla non-MF products with their risk level, lock-in (years) and hard
# regulatory eligibility flags (checked deterministically, before scoring).
VANILLA_PRODUCTS = [
    {"name": "Fixed Deposit (Amrit Mahotsav 444 days)", "risk": 1, "lock_in_years": 1.2, "kind": "deposit"},
    {"name": "Recurring Deposit", "risk": 1, "lock_in_years": 1, "kind": "deposit"},
    {"name": "Public Provident Fund (PPF)", "risk": 1, "lock_in_years": 15, "kind": "deposit",
     "resident_only": True},
    {"name": "National Pension System (NPS)", "risk": 3, "lock_in_years": 20, "kind": "pension"},
    {"name": "Sukanya Samriddhi Yojana", "risk": 1, "lock_in_years": 21, "kind": "deposit",
     "resident_only": True, "requires_minor_daughter": True},
]

MF_LOCK_IN = {"LIC MF ELSS Tax Saver": 3}  # years; other schemes are open-ended

# Audit trail: every suitability assessment ever made, queryable per customer.
AUDIT_LOG: list[dict] = []


def _customer_factors(cid):
    c = data.get_customer(cid)
    p = data.portfolio_summary(cid)
    b = analytics.behavioral_profile(c)
    eq = sum(h["current"] for h in p["holdings"]
             if "Equity" in h["asset_class"] or "Hybrid" in h["asset_class"])
    eq += p["external_market_linked"]  # AA-linked equity at other institutions
    eq_pct = round(eq / p["total_assets"] * 100) if p["total_assets"] else 0
    ideal_eq = max(20, min(70, 100 - c["age"]))
    horizon = max(1, 60 - c["age"])  # years to a normal retirement age
    return {
        "age": c["age"],
        "segment": c["segment"],
        "residency": c["residency"],
        "minor_daughter": c["minor_daughter"],
        "risk_profile": c["risk_profile"],
        "risk_band": RISK_BAND.get(c["risk_profile"], 3),
        "horizon_years": horizon,
        "monthly_surplus": c["monthly_income"] - p["avg_monthly_expenses"] - p["monthly_sip"],
        "emergency_months": round(c["savings_balance"] / max(p["avg_monthly_expenses"], 1), 1),
        "equity_pct": eq_pct, "ideal_equity_pct": ideal_eq,
        "income_stability": b["income_stability"],
        "sip_discipline_pct": b["sip_discipline_pct"],
    }


def _candidates():
    out = []
    for s in data.MF_SCHEMES:
        out.append({"name": s["name"], "risk": PRODUCT_RISK[s["risk"]],
                    "lock_in_years": MF_LOCK_IN.get(s["name"], 0), "kind": "mutual_fund",
                    "asset_class": s["class"], "cagr3y": s["cagr3y"]})
    out.extend(VANILLA_PRODUCTS)
    return out


def _assess_one(product, f):
    """Score one product against customer factors. Returns (verdict, score, reasons)."""
    reasons, cautions, score = [], [], 100

    # Hard regulatory eligibility — checked before any scoring.
    if product.get("resident_only") and f["residency"] == "NRI":
        return "NOT_SUITABLE", 0, [
            f"Not eligible: NRIs cannot open new {product['name'].split(' (')[0]} accounts "
            "(residency rule) — an NRE/FCNR deposit or mutual fund route applies instead"]
    if product.get("requires_minor_daughter") and not f["minor_daughter"]:
        return "NOT_SUITABLE", 0, [
            "Not eligible: Sukanya Samriddhi requires a resident girl child under 10 on record"]

    gap = product["risk"] - f["risk_band"]
    if gap >= 2:
        return "NOT_SUITABLE", 0, [
            f"Product risk ({product['risk']}/5) is well above the customer's "
            f"{f['risk_profile']} appetite (band {f['risk_band']}/5)"]
    if gap == 1:
        cautions.append(f"Risk one notch above the {f['risk_profile']} band — only for a satellite allocation")
        score -= 25
    else:
        reasons.append(f"Risk {product['risk']}/5 fits the {f['risk_profile']} profile (band {f['risk_band']}/5)")

    if product["risk"] >= 4 and f["age"] >= 50:
        cautions.append(f"High-volatility product at age {f['age']} — shortened recovery window")
        score -= 20
    if product["risk"] >= 4 and f["emergency_months"] < 3:
        cautions.append(f"Emergency buffer is only {f['emergency_months']} months — market-linked risk on a thin cushion")
        score -= 15

    if product["lock_in_years"] > 0:
        if f["income_stability"] != "Stable" and product["lock_in_years"] >= 3:
            cautions.append(f"{product['lock_in_years']}-year lock-in with {f['income_stability'].lower()} income — liquidity risk")
            score -= 15
        elif product["lock_in_years"] <= f["horizon_years"]:
            reasons.append(f"{product['lock_in_years']}-year lock-in sits inside the ~{f['horizon_years']}-year horizon")
        else:
            cautions.append(f"Lock-in ({product['lock_in_years']}y) exceeds the ~{f['horizon_years']}-year horizon")
            score -= 20

    is_equity = product["kind"] == "mutual_fund" and "Equity" in product.get("asset_class", "")
    if is_equity and f["equity_pct"] < f["ideal_equity_pct"] - 10:
        reasons.append(f"Equity is underweight ({f['equity_pct']}% vs ~{f['ideal_equity_pct']}% ideal) — adds needed growth allocation")
        score += 5
    if is_equity and f["equity_pct"] > f["ideal_equity_pct"] + 10:
        cautions.append(f"Equity already overweight ({f['equity_pct']}% vs ~{f['ideal_equity_pct']}% ideal) — would add concentration")
        score -= 15
    if product["kind"] == "deposit" and f["equity_pct"] > f["ideal_equity_pct"] + 10:
        reasons.append("Adds debt ballast to an equity-heavy allocation")
        score += 5

    if product["kind"] == "mutual_fund" and f["sip_discipline_pct"] >= 90:
        reasons.append(f"SIP debited in {f['sip_discipline_pct']}% of observed months — proven investing discipline")

    verdict = "SUITABLE" if not cautions else ("SUITABLE_WITH_CAUTION" if score >= 50 else "NOT_SUITABLE")
    return verdict, max(score, 0), reasons + cautions


def assess(cid, product_name=None, via="agent_tool"):
    """Assess one product (fuzzy name match) or rank all candidates.
    Every call is written to the audit trail."""
    f = _customer_factors(cid)
    cands = _candidates()
    if product_name:
        pl = product_name.lower()
        match = next((p for p in cands if pl in p["name"].lower()
                      or all(w in p["name"].lower() for w in pl.split()[:2])), None)
        if not match:
            return {"error": f"No catalog product matching '{product_name}'.",
                    "catalog": [p["name"] for p in cands]}
        cands = [match]

    results = []
    for p in cands:
        verdict, score, reasons = _assess_one(p, f)
        results.append({"product": p["name"], "verdict": verdict, "score": score, "reasons": reasons})
    results.sort(key=lambda r: -r["score"])

    c = data.get_customer(cid)
    for r in (results if product_name else results[:5]):
        AUDIT_LOG.append({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "customer_id": cid, "customer_name": c["name"],
            "product": r["product"], "verdict": r["verdict"],
            "reasons": r["reasons"], "factors": f, "via": via,
        })

    return {"assessed_for": c["name"], "factors": f,
            "assessments": results if product_name else results[:5],
            "note": "Deterministic suitability engine — every assessment is recorded in the advice audit trail."}


def audit_trail(cid, limit=20):
    entries = [e for e in AUDIT_LOG if e["customer_id"] == cid]
    return list(reversed(entries))[:limit]
