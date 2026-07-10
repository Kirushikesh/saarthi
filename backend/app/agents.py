"""Saarthi agent brain, built on LangChain's `create_agent`.

Architecture:
- One LangChain agent per (customer, household_mode), cached. Tools are
  closures bound to the customer so the model can never query another
  customer's data.
- The Compliance & Suitability Gate is real middleware (`wrap_model_call`),
  not just prompt text: when a regulated-product intent is detected it
  injects a hard directive into the system message and flags the event.
- The same agent serves the text chat API and the realtime voice layer
  (see voice.py), which delegates to it via an `ask_saarthi` tool.
"""

import json
import os
import queue
import re
import threading
import time
from contextvars import ContextVar
from typing import Callable

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.tools import tool
from langchain_core.messages import AIMessage, AIMessageChunk, SystemMessage
from langchain_aws import ChatBedrockConverse

from . import data, suitability

def _get_llm(temperature: float = 0.7):
    model_id = os.environ.get(
        "LLM_MODEL",
        "arn:aws:bedrock:us-west-2:329597158967:inference-profile/us.anthropic.claude-sonnet-4-6"
    )
    return ChatBedrockConverse(
        model=model_id,
        region_name=os.environ.get("AWS_REGION", "us-west-2"),
        temperature=temperature,
        provider="anthropic",
    )

# Per-request event log (tool calls, gate triggers) — contextvar so concurrent
# requests don't interleave.
_events: ContextVar[list] = ContextVar("saarthi_events")

# Per-turn telemetry for the performance report (in-memory, prototype scope).
METRICS: list[dict] = []
# gpt-4o-mini pricing, USD per 1M tokens
_PRICE_IN, _PRICE_OUT = 0.15, 0.60
_USD_INR = 84.0


# ---------------------------------------------------------------- compliance
# Two-stage regulated-intent detector feeding ONE deterministic middleware:
#   1. fast path — multilingual keyword patterns (native scripts + romanized),
#      zero latency, zero cost;
#   2. backstop — an LLM intent classifier for anything the patterns miss
#      (paraphrase, code-mixing, "that LIC plan my uncle suggested").
# The enforcement (directive injection + deterministic lead fallback) is
# unchanged — only detection is upgraded.
REGULATED_PATTERNS = re.compile(
    # English
    r"insurance|insur|ulip|term plan|health cover|mediclaim|\blic\b|pms|portfolio management"
    r"|aif|alternative investment|structured product|which stock|stock tip"
    r"|share market tip|demat|derivative|f&o|futures|options trading"
    # Romanized Indian-language terms
    r"|\bbima\b|\bbeema\b|\bvima\b|\bvimo\b|\bkappidu\b|\bkaappeedu\b|polic[iy]"
    # Hindi / Marathi (Devanagari)
    r"|बीमा|विमा|इंश्योरेंस|इन्शुरन्स|यूलिप|पॉलिसी|शेयर|स्टॉक|डीमैट"
    # Tamil
    r"|காப்பீடு|இன்சூரன்ஸ்|பங்கு|டீமேட்"
    # Telugu
    r"|బీమా|ఇన్సూరెన్స్|షేర్|స్టాక్|డీమ్యాట్"
    # Kannada
    r"|ವಿಮೆ|ಇನ್ಶೂರೆನ್ಸ್|ಷೇರು|ಸ್ಟಾಕ್"
    # Bengali
    r"|বিমা|বীমা|ইন্স্যুরেন্স|শেয়ার|স্টক",
    re.IGNORECASE,
)

# Vanilla allow-list: unambiguous permitted-product terms (multilingual). A hit
# here short-circuits to "not regulated" WITHOUT an LLM call — but only AFTER the
# regulated fast-path has run, so a message naming a regulated product (which
# always trips REGULATED_PATTERNS) can never be waved through. Deliberately
# excludes broad words that can front a regulated ask ("invest", "market",
# "share") — those fall through to the LLM. Net effect: the LLM only judges the
# keyword-free ambiguous middle, so common vanilla queries are deterministic.
VANILLA_PATTERNS = re.compile(
    r"\bloan\b|\bemi\b|home loan|\bmutual fund|\bmutual\b|\bsip\b|\bfd\b"
    r"|fixed deposit|recurring deposit|\bppf\b|\bnps\b|\bssy\b|sukanya"
    r"|retire|retirement|\bpension\b|\btax\b|\b80c\b|80ccd|emergency fund|budget"
    # loan (native scripts)
    r"|लोन|कर्ज|ऋण|கடன்|రుణ|లోన్|ಸಾಲ|ঋণ|লোন"
    # retirement (native scripts)
    r"|रिटायरमेंट|निवृत्ती|निवृत्ति|ஓய்வு|రిటైర్మెంట్|ನಿವೃತ್ತಿ|অবসর"
    # mutual fund (native scripts)
    r"|म्यूचुअल|மியூச்சுவல்|మ్యూచువల్|ಮ್ಯೂಚುವಲ್|মিউচুয়াল",
    re.IGNORECASE,
)

GATE_CLASSIFIER_PROMPT = """You are the compliance intent detector for an Indian bank's AI wealth advisor. Classify the customer's LATEST message.

REGULATED (route to a certified human): the message seeks advice, comparison, purchase help or suitability on products the AI may not advise — insurance of ANY kind (term/life/health/ULIP/endowment/money-back plans), PMS, AIF, structured products, direct stocks/shares/demat/derivatives/F&O, or a specific insurer's plan (e.g. "LIC Jeevan Anand").

VANILLA (the AI handles it): the customer's own portfolio and its performance, mutual funds/SIPs, FDs/RDs, PPF/NPS/SSY, budgeting, spending, goals, retirement planning, taxes, loans/EMIs, market levels and news, greetings — in ANY language.

Use the prior turns ONLY to resolve an ambiguous latest message: a bare follow-up like "which one is best for me?" or "should I go for it?" inherits the topic of the conversation — REGULATED if that topic was insurance/stocks/etc., VANILLA if it was mutual funds/deposits/goals. Judge INTENT, not language. When still uncertain, answer VANILLA — a separate keyword layer already catches explicit regulated-product mentions.

Examples:
"என் முதலீடுகள் எப்படி போகின்றன?" → VANILLA (own investments)
"मेरे लिए कौन सा म्यूचुअल फंड सही रहेगा?" → VANILLA (mutual funds are permitted)
"I need something to cover hospital bills if I fall sick" → REGULATED (health insurance intent)
[prior turn was about ULIPs] "which of those suits me?" → REGULATED (follow-up inherits the ULIP topic)
[prior turn listed the customer's mutual funds] "which one is best for me?" → VANILLA

Conversation so far (prior turns, oldest first):
{context}

Latest customer message: {msg}

Reply with exactly one word: REGULATED or VANILLA."""

_gate_model = None
_gate_cache: dict[str, bool] = {}


def _msg_text(m) -> str:
    """Plain text of a message whose content may be a string or content blocks."""
    c = getattr(m, "content", m)
    if isinstance(c, list):
        return "".join(b.get("text", "") for b in c if isinstance(b, dict))
    return str(c)


def _classify_regulated(text: str, context: str = "") -> tuple[bool, str]:
    """LLM backstop for the compliance gate. Sees the latest message plus a
    short transcript of prior turns, so ambiguous follow-ups ('which one is
    best for me?') inherit the conversation's topic. Cached per (context+text)
    — the middleware wraps every model call in a multi-tool turn.

    FAILS CLOSED: if the classifier itself errors (API degradation), the
    ambiguous query is treated as regulated and routed to a human RM. A bank
    would rather over-route to a person than silently drop protection.
    Degraded verdicts are not cached, so recovery is immediate."""
    global _gate_model
    key = (context[-500:] + "||" + text).strip().lower()[:800]
    if key in _gate_cache:
        return _gate_cache[key], "llm"
    try:
        if _gate_model is None:
            _gate_model = _get_llm(temperature=0.0).with_config(
                {"tags": ["compliance_gate"]}
            )
        out = _gate_model.invoke(GATE_CLASSIFIER_PROMPT.format(
            context=context or "(no prior turns)", msg=text[:600]))
        flag = str(out.content).strip().upper().startswith("REGULATED")
    except Exception:
        return True, "llm_failsafe"
    if len(_gate_cache) > 2000:
        _gate_cache.clear()
    _gate_cache[key] = flag
    return flag, "llm"


def detect_regulated(text: str, context: str = ""):
    """Returns the detector that fired ('pattern' | 'llm' | 'llm_failsafe') or
    None. Three layers: (1) regulated keyword fast-path (latest message only —
    a topic mentioned turns ago shouldn't re-trigger); (2) vanilla allow-list
    short-circuit, so common permitted queries never touch the LLM; (3) LLM
    backstop for the keyword-free ambiguous middle, given `context` to resolve
    follow-ups — failing closed to the RM if the classifier is unavailable."""
    if REGULATED_PATTERNS.search(text):
        return "pattern"
    if VANILLA_PATTERNS.search(text):
        return None
    flag, detector = _classify_regulated(text, context)
    return detector if flag else None

GATE_DIRECTIVE = (
    "\n\n## COMPLIANCE GATE — TRIGGERED FOR THIS TURN (overrides everything else)\n"
    "The customer's request concerns a REGULATED product (SEBI/IRDAI domain). "
    "You are NOT certified to advise on it. FORBIDDEN this turn: recommending, "
    "comparing, or assessing suitability of any insurance/ULIP/PMS/AIF/stock "
    "product — including 'X is suitable if...' framings. REQUIRED this turn: "
    "(1) at most one neutral sentence defining the product category, "
    "(2) call create_rm_lead EXACTLY ONCE covering the whole enquiry, "
    "(3) tell the customer their enquiry has been passed to a certified IDBI "
    "Relationship Manager who will reach out to them shortly — frame it as "
    "premium service, not refusal. NEVER promise a specific response time or "
    "SLA on the RM's behalf; the RM team confirms scheduling."
)


class ComplianceGateMiddleware(AgentMiddleware):
    """Framework-level guardrail: regulated-product intents cannot reach the
    model without the handoff directive attached to the system message."""

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        last_user = next(
            (m for m in reversed(request.messages) if m.type == "human"), None
        )
        detector = None
        if last_user:
            # Short transcript of the turns before the latest human message, so
            # the LLM backstop can resolve ambiguous follow-ups by topic.
            idx = next(i for i, m in enumerate(request.messages) if m is last_user)
            prior = [m for m in request.messages[:idx] if m.type in ("human", "ai")][-4:]
            context = "\n".join(
                f"{'Customer' if m.type == 'human' else 'Saarthi'}: {_msg_text(m)[:200]}"
                for m in prior if _msg_text(m).strip()
            )
            detector = detect_regulated(_msg_text(last_user), context)
        if detector:
            try:
                evs = _events.get()
                if not any(e["tool"] == "compliance_gate" for e in evs):
                    evs.append({"tool": "compliance_gate",
                                "args": {"status": "TRIGGERED", "detector": detector}})
            except LookupError:
                pass
            new_system = SystemMessage(
                content=(request.system_message.content if request.system_message else "")
                + GATE_DIRECTIVE
            )
            request = request.override(system_message=new_system)
        return handler(request)


# ---------------------------------------------------------------- tools
def _build_tools(cid: str, household_mode: bool):
    """Specialist capabilities as LangChain tools, bound to one customer."""

    @tool
    def get_portfolio() -> dict:
        """Full 360° portfolio for the customer: net worth, asset allocation, MF
        holdings with returns, FDs, EPF/NPS, loans, goals, monthly SIP, average
        expenses and spend by category. If the customer has linked other banks
        via the Account Aggregator, `external` lists those holdings too —
        include them when discussing the overall picture."""
        return data.portfolio_summary(cid)

    @tool
    def get_household_view() -> dict:
        """Combined household (joint) view for the customer and their linked
        partner: combined net worth, income, expenses, SIPs, allocation and joint
        goals. Only works if the customer has a linked partner."""
        return data.household_summary(cid) or {"error": "No linked partner for this customer."}

    @tool
    def simulate_loan_affordability(
        loan_amount: float,
        tenure_years: float,
        loan_type: str = "home",
        household: bool = household_mode,
    ) -> dict:
        """Scenario simulation: EMI and FOIR-based affordability check for a
        proposed loan (loan_type: home|auto|personal|education|mortgage),
        individually or jointly (household=True). Use for any 'can I/we afford
        X loan' question."""
        return data.loan_affordability(cid, loan_amount, tenure_years, loan_type, household)

    @tool
    def plan_goal(goal_name: str, household: bool = household_mode) -> dict:
        """Deterministic goal-planning math for one of the customer's saved
        goals: months remaining, required monthly saving, and (for joint goals
        in household mode) fair split options — 50-50 vs income-proportional.
        ALWAYS use this instead of computing goal math yourself."""
        return data.plan_goal(cid, goal_name, household)

    @tool
    def plan_sip_target(target_amount: float, years: float, expected_return_pct: float = 12.0) -> dict:
        """Inverse SIP calculator: the monthly SIP needed to reach a target
        corpus in a given number of years, and whether it fits the customer's
        current surplus. Use for 'how much should I invest monthly to get ₹X
        by year Y' questions. ALWAYS use this instead of doing the math yourself."""
        return data.sip_target(cid, target_amount, years, expected_return_pct)

    @tool
    def project_retirement(retirement_age: int = 60, household: bool = household_mode) -> dict:
        """Retirement readiness projection: projected corpus from current assets
        and SIPs vs the inflation-adjusted corpus needed (4% rule), plus the
        extra monthly SIP to close any gap. Use for any retirement question.
        ALWAYS use this instead of computing projections yourself."""
        return data.retirement_projection(cid, retirement_age, household)

    @tool
    def get_tax_summary() -> dict:
        """Tax-saving lens: Section 80C and 80CCD(1B) NPS utilization computed
        from the customer's actual ELSS SIPs and payroll, remaining headroom,
        and the potential annual tax saving. Use for 'how can I save tax'
        questions."""
        return data.tax_summary(cid)

    @tool
    def get_market_pulse() -> dict:
        """Today's market snapshot (NIFTY, SENSEX, midcaps, G-Sec yield, gold)
        AND its estimated impact on this customer's own holdings. Use for any
        'how are markets', 'why did my portfolio move', or market-linked
        product update question. Remind the customer that daily moves don't
        change long-term goals."""
        return data.market_pulse(cid)

    @tool
    def get_financial_health() -> dict:
        """Financial Health Score (0-100) with four scored pillars: emergency
        buffer, diversification, debt headroom and goal funding. Use when the
        customer asks how healthy their finances are or for an overall review."""
        return data.financial_health(cid)

    @tool
    def check_suitability(product_name: str = "") -> dict:
        """MANDATORY before recommending ANY investment product. Deterministic
        suitability engine: pass a product name to assess it, or leave empty
        for the top-5 ranked products for this customer. Returns verdict
        (SUITABLE / SUITABLE_WITH_CAUTION / NOT_SUITABLE) with explicit
        reasons; every check is recorded in the bank's advice audit trail.
        NEVER recommend against its verdict."""
        return suitability.assess(cid, product_name or None)

    @tool
    def get_behavioral_profile() -> dict:
        """Behavioural profile derived from the customer's raw bank
        transactions (12 months, narration-classified): income stability,
        savings rate, SIP discipline, discretionary spend ratio and a
        behavioural segment. Use it to ground advice in observed behaviour
        (variable income → liquidity caution, strong SIP discipline →
        SIP-friendly, high discretionary share → budgeting angle)."""
        return data.behavior_summary(cid)

    @tool
    def get_product_catalog() -> dict:
        """IDBI product catalog: 'vanilla' products the AI may directly recommend
        (FD, RD, MF SIP, PPF, NPS, SSY) with current rates, the distributed MF
        shelf (LIC MF regular plans — IDBI is an AMFI-registered distributor),
        and 'regulated' products that REQUIRE routing to a human RM."""
        return {"catalog": data.PRODUCT_CATALOG, "mf_schemes": data.MF_SCHEMES,
                "loan_rates_pct": data.LOAN_RATES}

    @tool
    def create_rm_lead(product: str, context: str) -> dict:
        """COMPLIANCE GATE handoff: create a qualified lead for a human
        Relationship Manager. MUST be used instead of giving direct advice for
        regulated products (insurance, ULIP, health cover, PMS, AIF, direct
        stocks) or when the customer asks for a human."""
        lead = data.create_lead(cid, product, context, household_mode)
        try:  # attribute the lead to THIS request (concurrency-safe)
            _events.get().append({"tool": "_lead_created", "args": lead})
        except LookupError:
            pass
        return {"lead_created": lead}

    return [get_portfolio, get_household_view, simulate_loan_affordability,
            plan_goal, plan_sip_target, project_retirement, get_tax_summary,
            get_market_pulse, get_financial_health, check_suitability,
            get_behavioral_profile, get_product_catalog, create_rm_lead]


# ---------------------------------------------------------------- prompt
# Segment playbooks — the SAME brain treats a Mass customer, an HNI and an NRI
# differently, per the bank's segmentation ask. Injected per customer.
SEGMENT_PLAYBOOK = {
    "Mass": (
        "Mass segment. Priorities in order: emergency buffer, insurance-of-basics awareness "
        "(educate only — product advice goes to the RM), small-ticket SIPs (₹500–5,000), RD/FD. "
        "Keep advice simple and jargon-free; one clear next step per reply. Avoid products with "
        "long lock-ins unless the goal clearly matches. Never push a product where a savings "
        "habit is the real fix."
    ),
    "Mass Affluent": (
        "Mass Affluent segment. Focus on goal-based planning: step-up SIPs, tax efficiency "
        "(80C/NPS headroom), home-loan planning with FOIR discipline, and closing "
        "under-allocation to equity for long horizons. Introduce the idea of a periodic "
        "portfolio review."
    ),
    "HNI": (
        "HNI segment — priority service tone. Watch for concentration risk, laddering of large "
        "FDs, liquidity for business needs, and estate/succession questions. For "
        "estate planning, business succession, bulk/negotiated FD pricing, or portfolio-scale "
        "mandates (PMS/AIF territory), proactively offer the dedicated IDBI Wealth RM via "
        "create_rm_lead — a seasoned human handles those, with priority routing. Frame the RM "
        "as their dedicated wealth desk, not a call-centre."
    ),
    "NRI": (
        "NRI segment. Always be NRE/NRO-aware: NRE FD interest is tax-free in India and freely "
        "repatriable; NRO income is taxable in India. NRIs CANNOT open new PPF or SSY accounts "
        "(the suitability engine enforces this — relay its reasons). Mutual funds and NPS are "
        "open to NRIs. For cross-border taxation, DTAA relief, FEMA/repatriation structuring or "
        "property-linked planning, route to the NRI desk RM via create_rm_lead — that is "
        "specialist human territory. Priority routing applies."
    ),
}

SYSTEM_TEMPLATE = """You are Saarthi, IDBI Bank's avatar-based AI wealth companion, embedded in the IDBI mobile banking app.

## Current customer
{profile}
{household_note}

## Segment playbook — {segment}
{segment_playbook}

## Language (absolute rule)
Detect the language of the customer's most recent message and write your ENTIRE reply in that language:
- English message → English reply. Plain English is NOT romanized Hindi.
- Native Indian script (Devanagari/Tamil/Telugu/Kannada/Bengali) → reply in that same language and script. A Kannada question gets a Kannada answer, a Telugu question a Telugu answer.
- Indian language typed in Latin letters (e.g., "mujhe retirement ke liye kitna chahiye") → reply in that language's native script.
Tool outputs arrive as English JSON — that NEVER changes your reply language; translate the findings. Product names and ₹ amounts stay as-is (lakh/crore conventions everywhere).

## Advisory rules
1. You MAY directly analyse, educate and recommend VANILLA products: FDs, RDs, mutual fund SIPs (suitability-based, at asset-class AND specific scheme level from the distributed catalog — regular plans, IDBI is an AMFI-registered distributor), PPF, NPS, SSY, budgeting and goal planning.
2. Every recommendation must be SUITABILITY-BASED: ALWAYS call check_suitability before recommending any specific investment product. It returns a deterministic verdict with reasons and records the assessment in the bank's advice audit trail. Never recommend against its verdict; briefly relay its reasons to the customer.
2b. Ground advice in OBSERVED behaviour, not just the profile form: use get_behavioral_profile for income stability, SIP discipline and spending patterns when relevant (e.g., variable income → larger emergency buffer before lock-ins).
3. Regulated products (insurance, ULIP, PMS, AIF, direct stocks, complex tax structuring) are handled by certified human RMs — use create_rm_lead for those. ALSO use create_rm_lead for complex unregulated cases where a seasoned human adds real value (estate/succession planning, large idle sums, cross-border needs, goals that clearly can't be funded) — Saarthi hands over generously, it never gatekeeps the human.
4. Never fabricate holdings or numbers — always fetch via tools. Use ₹ and Indian number formatting (e.g., ₹12.5 lakh, ₹1.2 crore). If the portfolio includes holdings at other institutions (via Account Aggregator), include them in the 360° picture and say where they're held.
5. Include a one-line disclaimer when recommending market-linked products: "Mutual fund investments are subject to market risks."
6. When an RM handoff happens, never promise a specific callback time — the RM team confirms scheduling.

## Household mode
{household_mode_note}
{sugam_note}
## Style
Warm, concise, confident — like a trusted personal banker. Use short paragraphs and markdown bullets/tables where helpful. Numbers first, then interpretation. For scenario simulations, show the key numbers (EMI, FOIR, surplus) and a clear verdict. Keep answers under ~250 words unless deep analysis is asked for.
"""

# Accessibility overlay — injected when the customer switches on Sugam mode
# (larger text + simple language for elderly, low-literacy and first-time
# investors). Overrides the Style section where they conflict.
SUGAM_NOTE = """
## Sugam mode (accessibility — ACTIVE, overrides Style where they conflict)
The customer has asked for simple, easy language. In every reply:
- Use everyday words a 10-year-old would follow; sentences under 15 words.
- No jargon. If a term is unavoidable (SIP, FD, EMI, FOIR), explain it in one plain phrase the first time, e.g. "EMI (the fixed amount you pay every month)".
- Keep replies under ~120 words. Prefer 2-4 short bullets over tables.
- End with one clear next step the customer can take.
- All other rules (language, suitability, compliance) still apply fully.
"""


def _system_prompt(customer, household_mode, sugam_mode=False):
    p = data.portfolio_summary(customer["id"])
    profile = (
        f"- {customer['name']}, {customer['age']}, {customer['occupation']}\n"
        f"- Segment: {customer['segment']} | Risk profile: {customer['risk_profile']}\n"
        f"- Monthly income: ₹{customer['monthly_income']:,} | Avg monthly expenses: ₹{p['avg_monthly_expenses']:,}\n"
        f"- Net worth: ₹{p['net_worth']:,} | Monthly SIP: ₹{p['monthly_sip']:,}"
    )
    household_note = ""
    if customer.get("partner_id"):
        partner = data.get_customer(customer["partner_id"])
        household_note = f"Linked joint account with {partner['name']} (consent on file for household view)."
    hm = (
        "ACTIVE — the couple is using Saarthi together. Analyse and plan at the HOUSEHOLD level (use get_household_view). "
        "When partners have different instincts (e.g., spend vs save, risk appetite), act as an impartial, data-driven mediator: "
        "present fair options (e.g., income-proportional contributions to joint goals) without taking sides."
        if household_mode else
        "Not active. Advise the individual customer. If a question inherently concerns their partner/household finances and they have a linked partner, you may suggest switching to Household mode."
    )
    return SYSTEM_TEMPLATE.format(
        profile=profile, household_note=household_note, household_mode_note=hm,
        segment=customer["segment"],
        segment_playbook=SEGMENT_PLAYBOOK.get(customer["segment"], SEGMENT_PLAYBOOK["Mass"]),
        sugam_note=SUGAM_NOTE if sugam_mode else "",
    )


# ---------------------------------------------------------------- agents
def get_agent(cid: str, household_mode: bool, sugam_mode: bool = False):
    """Built fresh per turn: the system prompt embeds live portfolio figures
    (net worth, SIP, expenses), so a cached agent would serve stale numbers
    the moment a transaction lands — and an unbounded cache doesn't scale
    with customers anyway. Graph construction is a few ms."""
    customer = data.get_customer(cid)
    return create_agent(
        model=_get_llm(temperature=0.7),
        tools=_build_tools(cid, household_mode),
        system_prompt=_system_prompt(customer, household_mode, sugam_mode),
        middleware=[ComplianceGateMiddleware()],
    )


def _finalize_turn(result_messages, events, cid, message, household_mode, latency_ms):
    """Shared post-processing for chat and chat_stream: lead attribution,
    deterministic gate enforcement, telemetry. Returns the API payload."""
    for m in result_messages:
        if isinstance(m, AIMessage) and m.tool_calls:
            events.extend({"tool": tc["name"], "args": tc["args"]} for tc in m.tool_calls)

    # Lead attribution via the request-scoped event log — never by inspecting
    # the shared queue, which misattributes under concurrent requests.
    lead = next((e["args"] for e in events if e["tool"] == "_lead_created"), None)
    events = [e for e in events if e["tool"] != "_lead_created"]
    reply = result_messages[-1].content if result_messages else ""
    if isinstance(reply, list):  # content blocks -> plain text
        reply = "".join(b.get("text", "") for b in reply if isinstance(b, dict))

    # Deterministic gate enforcement: if the gate fired but the model skipped
    # the handoff, the handoff happens anyway — compliance can't depend on the
    # model feeling like it.
    gate_event = next((e for e in events if e["tool"] == "compliance_gate"), None)
    gate_fired = gate_event is not None
    if gate_fired and lead is None:
        lead = data.create_lead(
            cid, "Regulated product enquiry",
            f"Auto-routed by compliance gate. Customer asked: {message[:200]}",
            household_mode,
        )
        events.append({"tool": "create_rm_lead", "args": {"auto": True}})
        reply += (
            "\n\nSince this involves a regulated product, I've shared your "
            "enquiry with a certified IDBI Relationship Manager, who will "
            "reach out to you shortly to guide you personally."
        )

    in_tok = out_tok = 0
    for m in result_messages:
        usage = getattr(m, "usage_metadata", None)
        if usage:
            in_tok += usage.get("input_tokens", 0)
            out_tok += usage.get("output_tokens", 0)
    cost_usd = (in_tok * _PRICE_IN + out_tok * _PRICE_OUT) / 1e6
    METRICS.append({
        "ts": time.time(), "customer_id": cid, "latency_ms": latency_ms,
        "input_tokens": in_tok, "output_tokens": out_tok,
        "cost_usd": round(cost_usd, 6), "cost_inr": round(cost_usd * _USD_INR, 4),
        "llm_calls": sum(1 for m in result_messages if isinstance(m, AIMessage)),
        "tools_used": [e["tool"] for e in events if e["tool"] != "compliance_gate"],
        "gate_fired": gate_fired,
        "gate_detector": gate_event["args"].get("detector") if gate_event else None,
        "lead_created": lead is not None,
        "household": household_mode,
    })
    return {"reply": reply, "events": events, "lead": lead}


def _turn_messages(history, message):
    messages = [{"role": h["role"], "content": h["content"]} for h in history[-12:]]
    messages.append({"role": "user", "content": message})
    return messages


def chat(cid, message, history, household_mode=False, sugam_mode=False):
    """Run one agent turn. Returns reply text + events (tools used, lead)."""
    customer = data.get_customer(cid)
    if not customer:
        return {"reply": "Unknown customer.", "events": []}

    agent = get_agent(cid, household_mode, sugam_mode)
    token = _events.set([])
    t0 = time.perf_counter()
    try:
        result = agent.invoke({"messages": _turn_messages(history, message)})
        events = _events.get()
    finally:
        _events.reset(token)
    latency_ms = round((time.perf_counter() - t0) * 1000)
    return _finalize_turn(result["messages"], events, cid, message, household_mode, latency_ms)


def chat_stream(cid, message, history, household_mode=False, sugam_mode=False):
    """Streaming variant of `chat` for the UI. Yields dict events:
    {"type": "status", "tool": ...}   as each specialist tool is invoked,
    {"type": "token", "text": ...}    as the reply generates,
    {"type": "done", reply/events/lead}  — the authoritative final payload
    (identical to chat()'s, including the deterministic gate fallback), which
    the client should treat as the source of truth over streamed tokens."""
    customer = data.get_customer(cid)
    if not customer:
        yield {"type": "done", "reply": "Unknown customer.", "events": [], "lead": None}
        return

    agent = get_agent(cid, household_mode, sugam_mode)
    t0 = time.perf_counter()
    result_messages: list = []

    # The ASGI server pulls sync generators through a threadpool, giving each
    # resume a FRESH copy of the request context — a contextvar set here would
    # not survive across yields. So the agent stream runs in one dedicated
    # thread that owns the _events context for its whole life, and hands
    # tokens/statuses to this generator through a queue.
    q: queue.Queue = queue.Queue()
    captured: dict = {"events": [], "error": None}

    def _run():
        token = _events.set([])
        try:
            for mode, chunk in agent.stream(
                {"messages": _turn_messages(history, message)},
                stream_mode=["updates", "messages"],
            ):
                if mode == "messages":
                    msg_chunk, meta = chunk
                    # Don't leak the compliance classifier's REGULATED/VANILLA verdict.
                    if "compliance_gate" in (meta.get("tags") or ()):
                        continue
                    if not isinstance(msg_chunk, AIMessageChunk) or msg_chunk.tool_call_chunks:
                        continue
                    text = _msg_text(msg_chunk)
                    if text:
                        q.put({"type": "token", "text": text})
                else:  # updates — full node outputs; also drives tool-status pings
                    for update in (chunk or {}).values():
                        for m in (update or {}).get("messages", []):
                            result_messages.append(m)
                            if isinstance(m, AIMessage) and m.tool_calls:
                                for tc in m.tool_calls:
                                    q.put({"type": "status", "tool": tc["name"]})
            captured["events"] = _events.get()
        except Exception as e:  # surfaced to the client by the generator below
            captured["error"] = e
        finally:
            _events.reset(token)
            q.put(None)  # end-of-stream sentinel

    threading.Thread(target=_run, daemon=True).start()
    while (item := q.get()) is not None:
        yield item
    if captured["error"]:
        raise captured["error"]

    latency_ms = round((time.perf_counter() - t0) * 1000)
    payload = _finalize_turn(result_messages, captured["events"], cid, message,
                             household_mode, latency_ms)
    payload["type"] = "done"
    yield payload


def metrics_summary():
    """Aggregates for the performance report — computed from real turns."""
    if not METRICS:
        return {"chats": 0}
    lat = sorted(m["latency_ms"] for m in METRICS)
    n = len(lat)
    tool_counts: dict[str, int] = {}
    for m in METRICS:
        for t_ in m["tools_used"]:
            tool_counts[t_] = tool_counts.get(t_, 0) + 1
    total_cost_usd = sum(m["cost_usd"] for m in METRICS)
    return {
        "chats": n,
        "latency_ms": {"avg": round(sum(lat) / n), "p50": lat[n // 2],
                        "p95": lat[min(n - 1, int(n * 0.95))], "max": lat[-1]},
        "tokens_per_chat": {"input": round(sum(m["input_tokens"] for m in METRICS) / n),
                             "output": round(sum(m["output_tokens"] for m in METRICS) / n)},
        "cost_per_chat": {"usd": round(total_cost_usd / n, 5),
                           "inr": round(total_cost_usd * _USD_INR / n, 3)},
        "projected_cost_inr_per_1000_chats": round(total_cost_usd * _USD_INR / n * 1000),
        "tool_call_rate_pct": round(sum(1 for m in METRICS if m["tools_used"]) / n * 100),
        "tool_usage": dict(sorted(tool_counts.items(), key=lambda kv: -kv[1])),
        "compliance_gate_triggers": sum(1 for m in METRICS if m["gate_fired"]),
        "gate_detectors": {
            "pattern": sum(1 for m in METRICS if m.get("gate_detector") == "pattern"),
            "llm_backstop": sum(1 for m in METRICS if m.get("gate_detector") == "llm"),
            "llm_failsafe": sum(1 for m in METRICS if m.get("gate_detector") == "llm_failsafe"),
        },
        "rm_leads_created": sum(1 for m in METRICS if m["lead_created"]),
        "gate_to_lead_conversion_pct": (
            round(sum(1 for m in METRICS if m["gate_fired"] and m["lead_created"])
                  / max(1, sum(1 for m in METRICS if m["gate_fired"])) * 100)),
        "model": MODEL,
    }


def nudges(cid):
    """Proactive insights computed from data (no LLM call — instant)."""
    p = data.portfolio_summary(cid)
    c = data.get_customer(cid)
    out = []
    mp = data.market_pulse(cid)
    pi = mp.get("portfolio_impact")
    if pi and abs(pi["day_change_pct"]) >= 0.3:
        up = pi["day_change_inr"] >= 0
        out.append({"icon": "📈" if up else "📉",
                    "title": f"Markets today: your funds {'+' if up else '−'}₹{abs(pi['day_change_inr']):,}",
                    "body": f"{mp['headline']}. That's {pi['day_change_pct']:+}% on your MF holdings — daily moves don't change your goals, your SIPs buy {'fewer' if up else 'more'} units."})
    aa = data.aa_status(cid)
    if aa and aa["available"] and not aa["linked"]:
        banks = ", ".join(aa["discovered"][:2])
        out.append({"icon": "🔗", "title": "Complete your 360° view",
                    "body": f"You hold accounts at other institutions ({banks}…). Link them via the RBI's Account Aggregator — consent-based and revocable — so Saarthi can advise on your full picture."})
    eq = sum(h["current"] for h in p["holdings"] if "Equity" in h["asset_class"] or "Hybrid" in h["asset_class"])
    eq += p["external_market_linked"]
    eq_pct = round(eq / p["total_assets"] * 100) if p["total_assets"] else 0
    ideal = max(20, min(70, 100 - c["age"]))
    if eq_pct < ideal - 15:
        out.append({"icon": "📈", "title": "Equity allocation looks low",
                    "body": f"Only {eq_pct}% of your assets are market-linked vs ~{ideal}% suggested for your age and {c['risk_profile'].lower()} profile. A step-up SIP could close the gap."})
    if eq_pct > ideal + 15:
        out.append({"icon": "🛡️", "title": "Consider de-risking",
                    "body": f"{eq_pct}% of assets are market-linked — higher than the ~{ideal}% typical for your profile. Consider moving gains to debt funds or FDs."})
    surplus = c["monthly_income"] - p["avg_monthly_expenses"] - p["monthly_sip"]
    if surplus > 0.2 * c["monthly_income"]:
        out.append({"icon": "💰", "title": f"₹{surplus:,.0f}/month is idling",
                    "body": "Your average surplus after expenses and SIPs is sitting in savings at 3%. An IDBI Liquid Fund or 444-day FD at 7.35% would work harder."})
    for g in p["goals"]:
        pct = round(g["saved"] / g["target"] * 100)
        if pct < 50:
            out.append({"icon": "🎯", "title": f"{g['name']}: {pct}% funded",
                        "body": f"Target ₹{g['target']:,} by {g['by']}. Ask me to simulate the SIP needed to get there on time."})
    emergency = c["savings_balance"] / max(p["avg_monthly_expenses"], 1)
    if emergency < 4:
        out.append({"icon": "⚠️", "title": "Thin emergency buffer",
                    "body": f"Savings cover ~{emergency:.1f} months of expenses; 6 months is the safe floor — especially with variable income."})
    tax = data.tax_summary(cid)
    if tax["potential_annual_tax_saving"] > 0:
        out.append({"icon": "🧾", "title": f"₹{tax['potential_annual_tax_saving']:,} in tax savings unclaimed",
                    "body": "You have unused 80C/NPS headroom. Ask me how to use it before March."})
    return out[:4]


# ---------------------------------------------------------------- reports
REPORT_PROMPT = """You are Saarthi, IDBI Bank's AI wealth companion. Write the couple's Monthly Household Review as clean markdown.

Rules:
- Use ONLY the numbers in the data below — never invent or recompute figures.
- ₹ and Indian formatting (lakh/crore). Warm, plain-English, impartial between partners.
- Structure: ## 🏠 Monthly Household Review — {month}
  then short sections: **The headline** (net worth + one-line verdict), **Cash flow**, **Financial health** (both partners' scores), **Joint goals** (on/off track, required monthly saving, fair split), **Retirement check**, **Three actions for this month** (numbered, specific, from the data).
- Under 350 words. No disclaimers except one final line: "_Mutual fund investments are subject to market risks._"

DATA:
{payload}
"""


def _inr(n: int) -> str:
    """Indian digit grouping: 25815660 -> ₹2,58,15,660."""
    sign, n = ("-" if n < 0 else ""), abs(int(n))
    s = str(n)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        s = ",".join(([head] if head else []) + parts + [tail])
    return f"{sign}₹{s}"


def _fmt_money(obj):
    """Pre-format rupee amounts so the LLM copies them verbatim instead of
    re-grouping digits (where it makes lakh/crore comma mistakes)."""
    if isinstance(obj, dict):
        return {k: _fmt_money(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_fmt_money(v) for v in obj]
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, (int, float)) and abs(obj) >= 1000:
        return _inr(obj)
    return obj


def household_report(cid: str) -> dict:
    """Generate the Monthly Household Review: deterministic facts assembled
    in code, narrated once by the LLM."""
    h = data.household_summary(cid)
    if not h:
        return {"error": "No linked partner for this customer."}
    payload = {
        "month": data.TODAY.strftime("%B %Y"),
        "household": {k: h[k] for k in ("net_worth", "total_assets", "total_liabilities",
                                          "combined_income", "combined_expenses", "combined_sip")},
        "members": [
            {"name": m["name"], "income": m["monthly_income"],
             "health": data.financial_health(m["id"])}
            for m in h["members"]
        ],
        "joint_goals": [data.plan_goal(cid, g["name"], household=True) for g in h["joint_goals"]],
        "retirement": data.retirement_projection(cid, household=True),
    }
    model = _get_llm(temperature=0.7)
    reply = model.invoke(REPORT_PROMPT.format(
        month=payload["month"],
        payload=json.dumps(_fmt_money(payload), default=str, ensure_ascii=False),
    ))
    return {"report": reply.content, "generated": str(data.TODAY), "data": payload}


# ---------------------------------------------------------------- RM copilot
RM_BRIEF_PROMPT = """You are Saarthi, IDBI Bank's AI wealth companion, preparing a human Relationship Manager for a customer conversation. Leads reach the RM two ways (the lead's "kind" field says which): "compliance" — the enquiry involved a regulated product, so the compliance gate routed it to a certified human instead of giving AI advice; "opportunity" — Saarthi proactively spotted a complex or high-value case (idle funds, an underfunded goal) that deserves a seasoned human. Either way the RM approves and acts; the AI only stages.

Return STRICT JSON (no code fences) with exactly two keys:
- "brief": a markdown pre-meeting brief for the RM. Sections: **Who** (one line: name, age, occupation, segment, risk profile), **The ask** (what triggered this lead and why it reached a human), **Financial snapshot** (4-6 bullets with the key ₹ numbers), **Suitability signals** (what fits their profile, what to watch), **Talking points** (3 numbered, specific). Under 220 words. Use ONLY the numbers in the data — never invent figures.
- "draft_message": a warm 2-3 sentence message to the customer (SMS/WhatsApp tone, from their IDBI Relationship Manager). Reference the topic. NO numbers, NO product advice, NO promised response time or SLA — just confirmation that a certified RM is personally on it.

DATA:
{payload}
"""


def lead_brief(lead_id: str) -> dict:
    """Pre-meeting brief + drafted customer message for an RM lead.
    Deterministic facts assembled in code, narrated once by the LLM; cached
    on the lead so the console can re-open it instantly."""
    lead = data.get_lead(lead_id)
    if not lead:
        return {"error": "lead not found"}
    if lead.get("brief"):
        return {"lead_id": lead_id, "brief": lead["brief"], "draft_message": lead["draft_message"]}

    cid = lead["customer_id"]
    c = data.get_customer(cid)
    p = data.portfolio_summary(cid)
    payload = {
        "lead": {k: lead[k] for k in ("product", "context", "kind", "priority", "household", "created")},
        "customer": {k: c[k] for k in ("name", "age", "occupation", "segment", "risk_profile", "monthly_income")},
        "net_worth": p["net_worth"],
        "allocation": p["allocation"],
        "monthly_sip": p["monthly_sip"],
        "avg_monthly_expenses": p["avg_monthly_expenses"],
        "monthly_surplus": c["monthly_income"] - p["avg_monthly_expenses"] - p["monthly_sip"],
        "loans": p["loans"], "goals": p["goals"],
        "financial_health": data.financial_health(cid),
    }
    model = _get_llm(temperature=0.7)
    reply = model.invoke(RM_BRIEF_PROMPT.format(
        payload=json.dumps(_fmt_money(payload), default=str, ensure_ascii=False)))
    text = reply.content if isinstance(reply.content, str) else str(reply.content)
    try:
        parsed = json.loads(re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip())
        brief, draft = parsed["brief"], parsed["draft_message"]
    except Exception:  # model ignored JSON instructions — degrade gracefully
        brief, draft = text, (
            f"Hello {c['name'].split(' ')[0]}, this is your IDBI Relationship Manager. "
            f"I've received your enquiry about {lead['product'].lower()} and will reach out "
            "shortly to guide you personally. Looking forward to speaking with you!"
        )
    lead["brief"], lead["draft_message"] = brief, draft
    return {"lead_id": lead_id, "brief": brief, "draft_message": draft}
