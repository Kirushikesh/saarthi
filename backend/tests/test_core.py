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


# ---------------------------------------------------------------- gate layering
# The vanilla allow-list short-circuits common permitted queries to "not
# regulated" WITHOUT an LLM call, so detect_regulated is deterministic here.
VANILLA_SHORTCIRCUIT = [
    "Can I afford a 50 lakh home loan for 20 years?",
    "क्या मैं 50 लाख का होम लोन ले सकता हूँ?",     # Hindi home loan
    "20 வருடத்திற்கு 50 லட்சம் வீட்டுக் கடன் வாங்க முடியுமா?",  # Tamil loan
    "20 ఏళ్లకు 50 లక్షల హోమ్ లోన్ తీసుకోగలనా?",   # Telugu loan
    "Tell me about NPS",
    "How much should I save for retirement?",
    "How can I save tax this year?",
]


@pytest.mark.parametrize("q", VANILLA_SHORTCIRCUIT)
def test_vanilla_allowlist_shortcircuits_without_llm(q):
    # VANILLA_PATTERNS must hit AND regulated must not — so detect_regulated
    # returns None before reaching the LLM backstop.
    assert agents.VANILLA_PATTERNS.search(q), f"vanilla allow-list missed: {q}"
    assert agents.detect_regulated(q) is None, f"vanilla query gated: {q}"


def test_regulated_wins_when_both_keywords_present():
    # "mutual fund" (vanilla) + "ULIP" (regulated) → regulated fast-path wins,
    # because the regulated check runs before the vanilla short-circuit.
    q = "Should I move my mutual fund money into a ULIP?"
    assert agents.VANILLA_PATTERNS.search(q)
    assert agents.detect_regulated(q) == "pattern"


def test_bare_followup_has_no_keyword_either_way():
    # The ambiguous multi-turn follow-up matches neither list — which is why the
    # LLM backstop (with conversation context) is needed to resolve it.
    q = "Which one would be best for someone like me?"
    assert not agents.REGULATED_PATTERNS.search(q)
    assert not agents.VANILLA_PATTERNS.search(q)


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


# ---------------------------------------------------------------- gate failsafe
def test_backstop_fails_closed_when_llm_unavailable(monkeypatch):
    # If the LLM classifier errors (API degradation), ambiguous queries must
    # route to a human RM — fail closed, not open.
    class Boom:
        def invoke(self, *_a, **_k):
            raise RuntimeError("api down")
    monkeypatch.setattr(agents, "_gate_model", Boom())
    agents._gate_cache.clear()
    assert agents.detect_regulated("Which one would be best for someone like me?") == "llm_failsafe"


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


def test_nri_cannot_open_ppf_or_ssy():
    # Hard regulatory eligibility: C005 is NRI (with a minor daughter — SSY
    # still blocked because it additionally requires resident status).
    for product in ("PPF", "Sukanya"):
        r = suitability.assess("C005", product, via="test")
        assert r["assessments"][0]["verdict"] == "NOT_SUITABLE", product
        assert "Not eligible" in r["assessments"][0]["reasons"][0]


def test_nri_can_use_nps_and_mf():
    for product in ("NPS", "Nifty 50"):
        r = suitability.assess("C005", product, via="test")
        assert r["assessments"][0]["verdict"] != "NOT_SUITABLE", product


def test_ssy_requires_minor_daughter():
    r = suitability.assess("C001", "Sukanya", via="test")  # resident, no daughter
    assert r["assessments"][0]["verdict"] == "NOT_SUITABLE"


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


# ---------------------------------------------------------------- account aggregator
def test_aa_consent_gates_external_holdings():
    # C001 has discoverable accounts but no consent → balances must be hidden.
    s = data.aa_status("C001")
    if s["linked"]:  # reset if a previous test linked it
        data.aa_set("C001", False)
        s = data.aa_status("C001")
    assert s["available"] and not s["linked"]
    assert "accounts" not in s and s["discovered"]
    assert data.portfolio_summary("C001")["external"] is None

    base_assets = data.portfolio_summary("C001")["total_assets"]
    data.aa_set("C001", True)
    p = data.portfolio_summary("C001")
    assert p["external"]["total"] > 0
    assert p["total_assets"] == base_assets + p["external"]["total"]
    assert "Other institutions (via AA)" in p["allocation"]

    data.aa_set("C001", False)  # revocation cuts access instantly
    assert data.portfolio_summary("C001")["external"] is None
    assert any(e["action"] == "AA_CONSENT_REVOKE" for e in data.aa_status("C001")["audit_log"])


# ---------------------------------------------------------------- opportunity leads
def test_opportunity_scan_creates_deduped_leads():
    before = len(data.LEADS)
    created = data.scan_opportunity_leads()
    # C003 (HNI, idle cash + underfunded retirement goal) must be among them
    # unless an earlier scan in this session already flagged him.
    all_opp = [l for l in data.LEADS if l["kind"] == "opportunity"]
    assert any(l["customer_id"] == "C003" for l in all_opp)
    assert all(l["priority"] == "HIGH" for l in all_opp if l["segment"] in ("HNI", "NRI"))
    assert data.scan_opportunity_leads() == []  # deduped: second scan is a no-op
    assert len(data.LEADS) == before + len(created)
