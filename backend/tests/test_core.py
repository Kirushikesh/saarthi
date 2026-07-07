"""LLM-free tests for Saarthi's deterministic core: compliance gate patterns,
transaction classifier, behavioural signals, suitability engine, loan math."""

import pytest

from app import agents, analytics, data, suitability


# ---------------------------------------------------------------- gate patterns
REGULATED_QUERIES = [
    "Should I buy term insurance?",
    "Tell me about ULIPs",
    "should I buy that LIC policy my uncle suggested",
    "मुझे टर्म इंश्योरेंस के बारे में बताओ",       # Hindi
    "मुझे बीमा चाहिए",                                # Hindi
    "mujhe bima chahiye",                            # romanized Hindi
    "காப்பீடு வாங்கலாமா?",                          # Tamil
    "బీమా తీసుకోవాలా?",                              # Telugu
    "ವಿಮೆ ಬೇಕು",                                     # Kannada
    "আমি বিমা কিনতে চাই",                            # Bengali
    "मला विमा हवा आहे",                              # Marathi
    "which stock should I buy for quick gains",
    "open a demat account and suggest shares",
]

VANILLA_QUERIES = [
    "How are my mutual funds doing?",
    "Can I afford a 50 lakh home loan?",
    "रिटायरमेंट के लिए कितना बचाना चाहिए?",
    "What are the FD rates?",
    "எனது முதலீடுகள் எப்படி உள்ளன?",
    "Help me plan a SIP for my goal",
]


@pytest.mark.parametrize("q", REGULATED_QUERIES)
def test_gate_pattern_catches_regulated(q):
    assert agents.REGULATED_PATTERNS.search(q), f"pattern fast-path missed: {q}"


@pytest.mark.parametrize("q", VANILLA_QUERIES)
def test_gate_pattern_no_false_positive(q):
    assert not agents.REGULATED_PATTERNS.search(q), f"pattern false positive: {q}"


# ---------------------------------------------------------------- classifier
def test_classifier_full_coverage():
    for cid, stats in data.CLASSIFIER_STATS.items():
        assert stats["coverage_pct"] == 100.0, f"{cid}: unclassified narrations"


def test_transactions_are_raw_then_classified():
    txn = data.CUSTOMERS["C001"]["transactions"][0]
    assert analytics.categorize(txn["desc"]) == txn["category"]


def test_categorize_known_narrations():
    assert analytics.categorize("UPI - SWIGGY/BOOKMYSHOW") == "Dining & Entertainment"
    assert analytics.categorize("SIP AUTO DEBIT - MF") == "SIP Investments"
    assert analytics.categorize("ACH DEBIT - CAR LOAN EMI") == "Loan EMI"
    assert analytics.categorize("SALARY CREDIT") == "Income"
    assert analytics.categorize("UNKNOWN MERCHANT XYZ") == "Other"


# ---------------------------------------------------------------- behaviour
def test_behavioral_income_stability():
    assert data.behavior_summary("C001")["income_stability"] == "Stable"       # salaried
    assert data.behavior_summary("C004")["income_stability"] != "Stable"       # freelancer


def test_behavioral_sip_discipline():
    assert data.behavior_summary("C001")["sip_discipline_pct"] == 100


# ---------------------------------------------------------------- suitability
def test_high_risk_fund_not_suitable_for_conservative():
    r = suitability.assess("C003", "Midcap", via="test")
    assert r["assessments"][0]["verdict"] == "NOT_SUITABLE"


def test_liquid_fund_suitable_for_conservative():
    r = suitability.assess("C003", "Liquid", via="test")
    assert r["assessments"][0]["verdict"] == "SUITABLE"


def test_ranking_orders_by_fit():
    r = suitability.assess("C001", via="test")
    scores = [a["score"] for a in r["assessments"]]
    assert scores == sorted(scores, reverse=True)
    assert all(a["reasons"] for a in r["assessments"]), "every verdict must carry reasons"


def test_every_assessment_is_audited():
    before = len(suitability.audit_trail("C002", limit=100))
    suitability.assess("C002", "ELSS", via="test")
    after = suitability.audit_trail("C002", limit=100)
    assert len(after) == before + 1
    entry = after[0]
    assert entry["product"] and entry["verdict"] and entry["reasons"] and entry["factors"]


# ---------------------------------------------------------------- loan math
def test_emi_formula():
    # ₹50L, 20y @ 8.45% → standard amortization EMI ≈ ₹43,233
    r = data.loan_affordability("C001", 5_000_000, 20, "home")
    assert abs(r["emi"] - 43233) <= 60
    assert r["verdict"] in ("COMFORTABLE", "AFFORDABLE_WITH_CARE", "STRETCHED")


def test_health_score_bounds():
    for cid in data.CUSTOMERS:
        h = data.financial_health(cid)
        assert 0 <= h["score"] <= 100
        assert len(h["pillars"]) == 4
