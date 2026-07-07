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

from . import data

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
REGULATED_PATTERNS = re.compile(
    r"insurance|ulip|term plan|health cover|mediclaim|pms|portfolio management"
    r"|aif|alternative investment|structured product|which stock|stock tip"
    r"|share market tip|demat|derivative|f&o|futures|options trading",
    re.IGNORECASE,
)

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
        if last_user and REGULATED_PATTERNS.search(str(last_user.content)):
            try:
                evs = _events.get()
                if not any(e["tool"] == "compliance_gate" for e in evs):
                    evs.append({"tool": "compliance_gate", "args": {"status": "TRIGGERED"}})
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
        return {"lead_created": data.create_lead(cid, product, context, household_mode)}

    return [get_portfolio, get_household_view, simulate_loan_affordability,
            plan_goal, plan_sip_target, project_retirement, get_tax_summary,
            get_market_pulse, get_financial_health, get_product_catalog,
            create_rm_lead]


# ---------------------------------------------------------------- prompt
SYSTEM_TEMPLATE = """You are Saarthi, IDBI Bank's avatar-based AI wealth companion, embedded in the IDBI mobile banking app.

## Current customer
{profile}
{household_note}

## Language
ALWAYS reply in the language the customer writes/speaks in — Hindi, Tamil, Telugu, Kannada, Bengali, Marathi, or any other Indian language, in its native script (romanized input still gets native-script replies). Keep ₹ amounts and Indian conventions (lakh/crore) in every language. Default: English.

## Advisory rules
1. You MAY directly analyse, educate and recommend VANILLA products: FDs, RDs, mutual fund SIPs (suitability-based, at asset-class AND specific IDBI scheme level from the catalog), PPF, NPS, SSY, budgeting and goal planning.
2. Every recommendation must be SUITABILITY-BASED: consider age, risk profile, income, existing allocation, goals and time horizon. Briefly state why it suits them.
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
_agents = {}


def get_agent(cid: str, household_mode: bool):
    key = (cid, household_mode)
    if key not in _agents:
        customer = data.get_customer(cid)
        _agents[key] = create_agent(
            model=MODEL,
            tools=_build_tools(cid, household_mode),
            system_prompt=_system_prompt(customer, household_mode),
            middleware=[ComplianceGateMiddleware()],
        )
    return _agents[key]


def chat(cid, message, history, household_mode=False):
    """Run one agent turn. Returns reply text + events (tools used, lead)."""
    customer = data.get_customer(cid)
    if not customer:
        return {"reply": "Unknown customer.", "events": []}

    agent = get_agent(cid, household_mode)
    messages = [{"role": h["role"], "content": h["content"]} for h in history[-12:]]
    messages.append({"role": "user", "content": message})

    token = _events.set([])
    leads_before = len(data.LEADS)
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

    lead = data.LEADS[-1] if len(data.LEADS) > leads_before else None
    reply = result["messages"][-1].content
    if isinstance(reply, list):  # content blocks -> plain text
        reply = "".join(b.get("text", "") for b in reply if isinstance(b, dict))

    # Deterministic gate enforcement: if the gate fired but the model skipped
    # the handoff, the handoff happens anyway — compliance can't depend on the
    # model feeling like it.
    gate_fired = any(e["tool"] == "compliance_gate" for e in events)
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
        "gate_fired": gate_fired, "lead_created": lead is not None,
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
