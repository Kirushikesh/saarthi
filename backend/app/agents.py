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
import re
import time
from contextvars import ContextVar
from typing import Callable

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.tools import tool
from langchain_core.messages import AIMessage, SystemMessage

from . import data, suitability

_raw_model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
MODEL = _raw_model if ":" in _raw_model else f"openai:{_raw_model}"

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

GATE_CLASSIFIER_PROMPT = """You are the compliance intent detector for an Indian bank's AI wealth advisor.

REGULATED (route to a certified human): the message seeks advice, comparison, purchase help or suitability on products the AI may not advise — insurance of ANY kind (term/life/health/ULIP/endowment/money-back plans), PMS, AIF, structured products, direct stocks/shares/demat/derivatives/F&O, or a specific insurer's plan (e.g. "LIC Jeevan Anand").

VANILLA (the AI handles it): the customer's own portfolio and its performance, mutual funds/SIPs, FDs/RDs, PPF/NPS/SSY, budgeting, spending, goals, retirement planning, taxes, loans/EMIs, market levels and news, greetings — in ANY language.

The message may be in any Indian language/script, romanized, or code-mixed. Judge the INTENT, not the language. When uncertain, answer VANILLA — a separate keyword layer already catches explicit regulated-product mentions.

Examples:
"என் முதலீடுகள் எப்படி போகின்றன?" → VANILLA (own investments)
"मेरे लिए कौन सा म्यूचुअल फंड सही रहेगा?" → VANILLA (mutual funds are permitted)
"I need something to cover hospital bills if I fall sick" → REGULATED (health insurance intent)
"कौन सा शेयर खरीदूं?" → REGULATED (direct stocks)

Reply with exactly one word: REGULATED or VANILLA.

Message: {msg}"""

_gate_model = None
_gate_cache: dict[str, bool] = {}


def _classify_regulated(text: str) -> bool:
    """LLM backstop for the compliance gate. Cached per message (the
    middleware wraps every model call in a multi-tool turn). Fails open —
    the keyword fast-path and the deterministic lead fallback still stand."""
    global _gate_model
    key = text.strip().lower()[:300]
    if key in _gate_cache:
        return _gate_cache[key]
    try:
        if _gate_model is None:
            _gate_model = init_chat_model(MODEL, temperature=0)
        out = _gate_model.invoke(GATE_CLASSIFIER_PROMPT.format(msg=text[:600]))
        flag = str(out.content).strip().upper().startswith("REGULATED")
    except Exception:
        flag = False
    if len(_gate_cache) > 2000:
        _gate_cache.clear()
    _gate_cache[key] = flag
    return flag


def detect_regulated(text: str):
    """Returns the detector that fired ('pattern' | 'llm') or None."""
    if REGULATED_PATTERNS.search(text):
        return "pattern"
    if _classify_regulated(text):
        return "llm"
    return None

GATE_DIRECTIVE = (
    "\n\n## COMPLIANCE GATE — TRIGGERED FOR THIS TURN (overrides everything else)\n"
    "The customer's request concerns a REGULATED product (SEBI/IRDAI domain). "
    "You are NOT certified to advise on it. FORBIDDEN this turn: recommending, "
    "comparing, or assessing suitability of any insurance/ULIP/PMS/AIF/stock "
    "product — including 'X is suitable if...' framings. REQUIRED this turn: "
    "(1) at most one neutral sentence defining the product category, "
    "(2) call create_rm_lead EXACTLY ONCE covering the whole enquiry, "
    "(3) tell the customer a certified IDBI Relationship Manager will call them "
    "within 24 hours — frame it as premium service, not refusal."
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
        detector = detect_regulated(str(last_user.content)) if last_user else None
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
        expenses and spend by category."""
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
        (FD, RD, MF SIP, PPF, NPS, SSY) with current rates, available MF schemes,
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
SYSTEM_TEMPLATE = """You are Saarthi, IDBI Bank's avatar-based AI wealth companion, embedded in the IDBI mobile banking app.

## Current customer
{profile}
{household_note}

## Language (absolute rule)
Detect the language of the customer's most recent message and write your ENTIRE reply in that language:
- English message → English reply. Plain English is NOT romanized Hindi.
- Native Indian script (Devanagari/Tamil/Telugu/Kannada/Bengali) → reply in that same language and script. A Kannada question gets a Kannada answer, a Telugu question a Telugu answer.
- Indian language typed in Latin letters (e.g., "mujhe retirement ke liye kitna chahiye") → reply in that language's native script.
Tool outputs arrive as English JSON — that NEVER changes your reply language; translate the findings. Product names and ₹ amounts stay as-is (lakh/crore conventions everywhere).

## Advisory rules
1. You MAY directly analyse, educate and recommend VANILLA products: FDs, RDs, mutual fund SIPs (suitability-based, at asset-class AND specific IDBI scheme level from the catalog), PPF, NPS, SSY, budgeting and goal planning.
2. Every recommendation must be SUITABILITY-BASED: ALWAYS call check_suitability before recommending any specific investment product. It returns a deterministic verdict with reasons and records the assessment in the bank's advice audit trail. Never recommend against its verdict; briefly relay its reasons to the customer.
2b. Ground advice in OBSERVED behaviour, not just the profile form: use get_behavioral_profile for income stability, SIP discipline and spending patterns when relevant (e.g., variable income → larger emergency buffer before lock-ins).
3. Regulated products (insurance, ULIP, PMS, AIF, direct stocks, complex tax structuring) are handled by certified human RMs — use create_rm_lead for those.
4. Never fabricate holdings or numbers — always fetch via tools. Use ₹ and Indian number formatting (e.g., ₹12.5 lakh, ₹1.2 crore).
5. Include a one-line disclaimer when recommending market-linked products: "Mutual fund investments are subject to market risks."

## Household (Humsafar) mode
{household_mode_note}

## Style
Warm, concise, confident — like a trusted personal banker. Use short paragraphs and markdown bullets/tables where helpful. Numbers first, then interpretation. For scenario simulations, show the key numbers (EMI, FOIR, surplus) and a clear verdict. Keep answers under ~250 words unless deep analysis is asked for.
"""


def _system_prompt(customer, household_mode):
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
        "Not active. Advise the individual customer. If a question inherently concerns their partner/household finances and they have a linked partner, you may suggest switching to Humsafar mode."
    )
    return SYSTEM_TEMPLATE.format(profile=profile, household_note=household_note, household_mode_note=hm)


# ---------------------------------------------------------------- agents
def get_agent(cid: str, household_mode: bool):
    """Built fresh per turn: the system prompt embeds live portfolio figures
    (net worth, SIP, expenses), so a cached agent would serve stale numbers
    the moment a transaction lands — and an unbounded cache doesn't scale
    with customers anyway. Graph construction is a few ms."""
    customer = data.get_customer(cid)
    return create_agent(
        model=MODEL,
        tools=_build_tools(cid, household_mode),
        system_prompt=_system_prompt(customer, household_mode),
        middleware=[ComplianceGateMiddleware()],
    )


def chat(cid, message, history, household_mode=False):
    """Run one agent turn. Returns reply text + events (tools used, lead)."""
    customer = data.get_customer(cid)
    if not customer:
        return {"reply": "Unknown customer.", "events": []}

    agent = get_agent(cid, household_mode)
    messages = [{"role": h["role"], "content": h["content"]} for h in history[-12:]]
    messages.append({"role": "user", "content": message})

    token = _events.set([])
    t0 = time.perf_counter()
    try:
        result = agent.invoke({"messages": messages})
        events = _events.get()
    finally:
        _events.reset(token)
    latency_ms = round((time.perf_counter() - t0) * 1000)

    for m in result["messages"]:
        if isinstance(m, AIMessage) and m.tool_calls:
            events.extend({"tool": tc["name"], "args": tc["args"]} for tc in m.tool_calls)

    # Lead attribution via the request-scoped event log — never by inspecting
    # the shared queue, which misattributes under concurrent requests.
    lead = next((e["args"] for e in events if e["tool"] == "_lead_created"), None)
    events = [e for e in events if e["tool"] != "_lead_created"]
    reply = result["messages"][-1].content
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
            "\n\nSince this involves a regulated product, I've arranged for a "
            "certified IDBI Relationship Manager to call you within 24 hours "
            "to guide you personally."
        )

    in_tok = out_tok = 0
    for m in result["messages"]:
        usage = getattr(m, "usage_metadata", None)
        if usage:
            in_tok += usage.get("input_tokens", 0)
            out_tok += usage.get("output_tokens", 0)
    cost_usd = (in_tok * _PRICE_IN + out_tok * _PRICE_OUT) / 1e6
    METRICS.append({
        "ts": time.time(), "customer_id": cid, "latency_ms": latency_ms,
        "input_tokens": in_tok, "output_tokens": out_tok,
        "cost_usd": round(cost_usd, 6), "cost_inr": round(cost_usd * _USD_INR, 4),
        "llm_calls": sum(1 for m in result["messages"] if isinstance(m, AIMessage)),
        "tools_used": [e["tool"] for e in events if e["tool"] != "compliance_gate"],
        "gate_fired": gate_fired,
        "gate_detector": gate_event["args"].get("detector") if gate_event else None,
        "lead_created": lead is not None,
        "household": household_mode,
    })
    return {"reply": reply, "events": events, "lead": lead}


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
    eq = sum(h["current"] for h in p["holdings"] if "Equity" in h["asset_class"] or "Hybrid" in h["asset_class"])
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
REPORT_PROMPT = """You are Saarthi, IDBI Bank's AI wealth companion. Write the couple's monthly "State of our Union" household financial report as clean markdown.

Rules:
- Use ONLY the numbers in the data below — never invent or recompute figures.
- ₹ and Indian formatting (lakh/crore). Warm, plain-English, impartial between partners.
- Structure: ## 👫 State of our Union — {month}
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
    """Generate the 'State of our Union' household report: deterministic
    facts assembled in code, narrated once by the LLM."""
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
    model = init_chat_model(MODEL)
    reply = model.invoke(REPORT_PROMPT.format(
        month=payload["month"],
        payload=json.dumps(_fmt_money(payload), default=str, ensure_ascii=False),
    ))
    return {"report": reply.content, "generated": str(data.TODAY), "data": payload}


# ---------------------------------------------------------------- RM copilot
RM_BRIEF_PROMPT = """You are Saarthi, IDBI Bank's AI wealth companion, preparing a human Relationship Manager for a callback. The customer's enquiry involved a regulated product, so the compliance gate routed it here instead of giving AI advice — the RM approves and acts, the AI only stages.

Return STRICT JSON (no code fences) with exactly two keys:
- "brief": a markdown pre-meeting brief for the RM. Sections: **Who** (one line: name, age, occupation, segment, risk profile), **The ask** (what they asked and why it was gated), **Financial snapshot** (4-6 bullets with the key ₹ numbers), **Suitability signals** (what fits their profile, what to watch), **Talking points** (3 numbered, specific). Under 220 words. Use ONLY the numbers in the data — never invent figures.
- "draft_message": a warm 2-3 sentence callback confirmation to the customer (SMS/WhatsApp tone, from their IDBI Relationship Manager). Reference their enquiry topic. NO numbers, NO product advice — just confirmation and reassurance.

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
        "lead": {k: lead[k] for k in ("product", "context", "priority", "household", "created")},
        "customer": {k: c[k] for k in ("name", "age", "occupation", "segment", "risk_profile", "monthly_income")},
        "net_worth": p["net_worth"],
        "allocation": p["allocation"],
        "monthly_sip": p["monthly_sip"],
        "avg_monthly_expenses": p["avg_monthly_expenses"],
        "monthly_surplus": c["monthly_income"] - p["avg_monthly_expenses"] - p["monthly_sip"],
        "loans": p["loans"], "goals": p["goals"],
        "financial_health": data.financial_health(cid),
    }
    model = init_chat_model(MODEL)
    reply = model.invoke(RM_BRIEF_PROMPT.format(
        payload=json.dumps(_fmt_money(payload), default=str, ensure_ascii=False)))
    text = reply.content if isinstance(reply.content, str) else str(reply.content)
    try:
        parsed = json.loads(re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip())
        brief, draft = parsed["brief"], parsed["draft_message"]
    except Exception:  # model ignored JSON instructions — degrade gracefully
        brief, draft = text, (
            f"Hello {c['name'].split(' ')[0]}, this is your IDBI Relationship Manager. "
            f"I've received your enquiry about {lead['product'].lower()} and will call you "
            "within 24 hours to guide you personally. Looking forward to speaking with you!"
        )
    lead["brief"], lead["draft_message"] = brief, draft
    return {"lead_id": lead_id, "brief": brief, "draft_message": draft}
