"""Saarthi agent orchestration.

A central Orchestrator (LLM with tool use) commands specialist capabilities:
portfolio, spending, scenario simulation, household view, product catalog and
the Compliance & Suitability Gate that routes regulated products to an RM lead.

The prototype calls the OpenAI API; the production architecture targets
Amazon Bedrock — the orchestration layer is provider-agnostic.
"""

import json
import os

from openai import OpenAI

from . import data

MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")

_client = None


def client():
    global _client
    if _client is None:
        _client = OpenAI()  # needs OPENAI_API_KEY
    return _client


TOOLS = [
    {"type": "function", "function": {
        "name": "get_portfolio",
        "description": "Full 360° portfolio for the current customer: net worth, asset allocation, MF holdings with returns, FDs, EPF/NPS, loans, goals, monthly SIP, average expenses and spend by category.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "get_household_view",
        "description": "Combined household (joint) view for the customer and their linked partner: combined net worth, income, expenses, SIPs, allocation and joint goals. Only works if the customer has a linked partner.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "simulate_loan_affordability",
        "description": "Scenario simulation: EMI and FOIR-based affordability check for a proposed loan, individually or for the household. Use for any 'can I/we afford X loan' question.",
        "parameters": {"type": "object", "properties": {
            "loan_amount": {"type": "number", "description": "Loan principal in INR"},
            "tenure_years": {"type": "number"},
            "loan_type": {"type": "string", "enum": ["home", "auto", "personal", "education", "mortgage"]},
            "household": {"type": "boolean", "description": "true to assess jointly with partner"},
        }, "required": ["loan_amount", "tenure_years", "loan_type"]},
    }},
    {"type": "function", "function": {
        "name": "get_product_catalog",
        "description": "IDBI product catalog: 'vanilla' products the AI may directly recommend (FD, RD, MF SIP, PPF, NPS, SSY) with current rates, available MF schemes, and 'regulated' products that REQUIRE routing to a human RM (insurance, ULIP, PMS, AIF, direct equity advisory).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "create_rm_lead",
        "description": "COMPLIANCE GATE: create a qualified lead for a human Relationship Manager. MUST be used instead of giving direct advice whenever the customer asks about regulated products (insurance, ULIP, health cover, PMS, AIF, direct stocks, complex tax structuring) or explicitly asks to speak to a human.",
        "parameters": {"type": "object", "properties": {
            "product": {"type": "string", "description": "Product/need, e.g. 'Term Insurance'"},
            "context": {"type": "string", "description": "1-2 line summary of the customer's need and financial context so the RM can prepare"},
        }, "required": ["product", "context"]},
    }},
]

SYSTEM_TEMPLATE = """You are Saarthi, IDBI Bank's avatar-based AI wealth companion, embedded in the IDBI mobile banking app.

## Current customer
{profile}
{household_note}

## Language
Reply in the language the customer writes/speaks in. If they write in Hindi (Devanagari or romanized), reply in Hindi. Default: English with Indian conventions (lakh/crore, ₹).

## Advisory rules (Compliance & Suitability Gate — non-negotiable)
1. You MAY directly analyse, educate and recommend VANILLA products: FDs, RDs, mutual fund SIPs (suitability-based, at asset-class AND specific IDBI scheme level from the catalog), PPF, NPS, SSY, budgeting and goal planning.
2. Every recommendation must be SUITABILITY-BASED: consider age, risk profile, income, existing allocation, goals and time horizon. Briefly state why it suits them.
3. You MUST NOT give direct advice on regulated products: any insurance (term/health/ULIP), PMS, AIF, structured products, direct stock tips, or complex tax structuring. For these, call create_rm_lead and tell the customer a certified IDBI Relationship Manager will call them — position it as a premium service, not a refusal. You may explain generic concepts (e.g., what term insurance is) before handing off.
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


def _run_tool(name, args, cid, household_mode):
    if name == "get_portfolio":
        return data.portfolio_summary(cid)
    if name == "get_household_view":
        return data.household_summary(cid) or {"error": "No linked partner for this customer."}
    if name == "simulate_loan_affordability":
        return data.loan_affordability(
            cid, args["loan_amount"], args["tenure_years"],
            args.get("loan_type", "home"), args.get("household", household_mode),
        )
    if name == "get_product_catalog":
        return {"catalog": data.PRODUCT_CATALOG, "mf_schemes": data.MF_SCHEMES, "loan_rates_pct": data.LOAN_RATES}
    if name == "create_rm_lead":
        return {"lead_created": data.create_lead(cid, args["product"], args["context"], household_mode)}
    return {"error": f"unknown tool {name}"}


def chat(cid, message, history, household_mode=False):
    """Run one orchestrated turn. Returns reply text + events (tools used, lead)."""
    customer = data.get_customer(cid)
    if not customer:
        return {"reply": "Unknown customer.", "events": []}

    messages = [{"role": "system", "content": _system_prompt(customer, household_mode)}]
    for h in history[-12:]:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": message})

    events, lead = [], None
    for _ in range(6):  # tool loop
        resp = client().chat.completions.create(
            model=MODEL, messages=messages, tools=TOOLS, temperature=0.4,
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return {"reply": msg.content or "", "events": events, "lead": lead}
        messages.append(msg)
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            result = _run_tool(tc.function.name, args, cid, household_mode)
            events.append({"tool": tc.function.name, "args": args})
            if isinstance(result, dict) and "lead_created" in result:
                lead = result["lead_created"]
            messages.append({
                "role": "tool", "tool_call_id": tc.id,
                "content": json.dumps(result, default=str),
            })
    return {"reply": "I gathered the data but ran out of steps — please ask again.", "events": events, "lead": lead}


def nudges(cid):
    """Proactive insights computed from data (no LLM call — instant)."""
    p = data.portfolio_summary(cid)
    c = data.get_customer(cid)
    out = []
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
    return out[:4]
