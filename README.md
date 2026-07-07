# Saarthi — AI Wealth Companion for IDBI Bank

**IDBI Innovate 2026 · Track 1: AI-Powered Digital Wealth Management · Team FinFusion.AI**

Saarthi is an avatar-based, multilingual AI wealth advisor designed to embed inside IDBI Bank's mobile app. It gives every retail liability customer a 360° financial view and goal-based, suitability-aware advisory — and introduces **Humsafar mode**, India's first household-level advisory experience: joint net worth, joint goals, joint affordability simulations and an impartial AI mediator for shared money decisions.

## Key capabilities

| Capability | What it does |
|---|---|
| 🎙️ Realtime voice avatar | Live spoken conversation (Google ADK + Gemini Live, barge-in supported) with an expressive animated advisor — blinks, lip-sync, thinking/listening states |
| 🌏 7 languages | English, Hindi, Tamil, Telugu, Kannada, Bengali, Marathi — localized UI, agent replies in the customer's language & script, voice follows |
| 📈 Market pulse | Daily index snapshot translated into personal impact: "Your funds today: +₹2,508" — with a stay-invested nudge |
| 📊 360° portfolio | Savings, FDs, MFs, NPS, EPF, categorized spends, goals — one dashboard |
| 🎯 Suitability engine | Deterministic product scoring (risk band, horizon, surplus, emergency buffer, behaviour signals) with per-recommendation reasons — every assessment written to a SEBI-style **advice audit trail** (`GET /api/suitability/{cid}`) |
| 🧠 Behavioural analytics | Spend categories and behaviour signals (income stability, savings rate, SIP discipline, discretionary share, behavioural segment) **derived from raw transaction narrations** — no pre-labeled data — feeding suitability and advice |
| 🧮 Scenario simulation | "Can I afford a ₹50L home loan?" → EMI, FOIR, surplus math with a clear verdict |
| 🧭 Retirement readiness | Projected corpus vs inflation-adjusted need (4% rule) and the exact extra monthly SIP to close the gap — individually or as a couple |
| 🧾 Tax-saving lens | 80C / 80CCD(1B) utilization computed from actual ELSS SIPs and payroll, with rupee headroom and suggested actions |
| 📈 Target-SIP planner | "How much monthly to reach ₹50L in 10 years?" → inverse SIP math, checked against the customer's real surplus |
| ❤️ Financial Health Score | 0–100 score across four pillars (emergency buffer, diversification, debt headroom, goal funding) — gauge on the dashboard, tool for the agent |
| 🛡️ Compliance & Suitability Gate | Three-layer regulated-intent detector in **all 7 languages** (regulated keyword fast-path → vanilla allow-list short-circuit → context-aware LLM backstop for paraphrase & multi-turn evasions), auto-routing to a human RM as a **qualified lead** — benchmarked at 100% catch (incl. 5/5 multi-turn) / 0% false positives across a 27-attack battery |
| 👫 Humsafar mode | Linked partners get combined analysis, joint goal planning and a data-driven mediator |
| 🔐 Consent-first data sharing | Household mode activates only on **mutual, revocable, audit-logged consent** (DPDP-aligned); enforced in the data layer, not the UI |
| 📏 Evaluation & telemetry | Scripted **93-query benchmark** across 7 languages (incl. multi-turn gate attacks) with a programmatic pass/fail rubric (`scripts/benchmark.py`) + live telemetry at `GET /api/metrics` — see [docs/performance-report.md](docs/performance-report.md) |
| 📜 State of our Union | One-tap monthly household report: headline, cash flow, both partners' health scores, joint goals with fair splits, retirement check and three actions — deterministic numbers, AI narration |
| 🫀 Proactive heartbeat | A background pulse (LLM-free, deterministic) rescans every customer's portfolio against today's market and **reaches out first** — 🔔 notifications arrive unprompted: market impact on your funds, allocation gaps, idle surplus, thin emergency buffers, off-track goals, unclaimed tax savings |
| 📋 RM copilot | For every gated lead, Saarthi preps the RM with an AI pre-meeting brief (profile, ₹ snapshot, suitability signals, talking points) and a drafted customer reply — the **RM approves, the AI produces**; approved messages land in the customer's notification feed |

## Architecture

```
Browser (React phone shell, avatar, AudioWorklets)
   │ REST /api/chat (text)          │ WS /ws/voice/{cid} (16kHz PCM up / 24kHz down)
   ▼                                ▼
FastAPI ──────────────────► ADK live session (Gemini Live, barge-in, transcripts)
   │                                │ ask_saarthi(question)   ← thin voice layer
   ▼                                ▼
LangChain create_agent  ◄───────────┘   ← one brain for both channels
   ├── @tools: portfolio · household view · loan simulation (EMI/FOIR)
   │           goal planner · target-SIP · retirement projection · tax lens
   │           financial health score · suitability check (audited) ·
   │           behavioural profile · product catalog · RM lead
   ├── ComplianceGateMiddleware (wrap_model_call): 3-layer detector —
   │   regulated keyword fast-path → vanilla allow-list → context-aware
   │   LLM backstop → hard handoff directive + deterministic lead fallback
   ├── Suitability engine (suitability.py): deterministic scoring with
   │   reasons; every assessment → advice audit trail
   ├── Behavioural analytics (analytics.py): raw narrations → categories +
   │   behaviour signals (income stability, SIP discipline, …)
   ├── Proactive heartbeat (background task): rescans portfolios vs today's
   │   market on a pulse, pushes notifications — no LLM, pure data math
   └── Synthetic bank data (round-1 scope) + RM lead queue + notification feed
```

- **Brain**: LangChain `create_agent` (v1) — model set by `LLM_MODEL` (OpenAI in the prototype; provider-agnostic via `init_chat_model` strings, so the same agent runs on **Amazon Bedrock** models inside IDBI's AWS landing zone in production).
- **Voice**: Google ADK drives a bidirectional **Gemini Live** session per connection; the voice agent is deliberately thin and delegates every substantive question to the same LangChain brain — so text and voice share tools, compliance and customer scoping.
- **Compliance as middleware, not prompts**: the gate inspects each turn before the model sees it; if the model still skips the RM handoff, the lead is created deterministically.

> Round-1 note: per the hackathon instructions, all data is **synthetic and self-generated** (4 personas across Mass / Mass Affluent / HNI segments with 12 months of categorized transactions, holdings and joint-account links). No real customer data anywhere.

## Run locally

```bash
# backend (uv-managed)
cd backend
uv sync
cp .env.example .env   # add OPENAI_API_KEY + GOOGLE_API_KEY
uv run uvicorn app.main:app --port 8000

# frontend (second terminal)
cd frontend
npm install
npm run dev        # http://localhost:5173 (proxies /api and /ws to :8000)
```

## Tests & benchmark

```bash
cd backend
uv run pytest tests/                     # 30 LLM-free tests: gate patterns,
                                         # classifier, suitability, loan math
uv run python scripts/benchmark.py       # 93-query scripted eval (7 languages,
                                         # 27 gate attacks incl. multi-turn)
```

Latest results: 100% gate catch (incl. 5/5 multi-turn), 0% false positives,
100% language fidelity, 100% intent-tool match —
[docs/performance-report.md](docs/performance-report.md).
Bank-stack integration path (IDBI GO embed, auth, Account Aggregator, Bedrock/
Nova Sonic): [docs/integration-architecture.md](docs/integration-architecture.md).

## Deploy

- **Backend → Railway**: point a service at `backend/` (railway.toml included), set `OPENAI_API_KEY` and `GOOGLE_API_KEY`.
- **Frontend → Vercel**: point a project at `frontend/`, set `VITE_API_URL=https://<railway-app>.up.railway.app`.

## Demo script (3 minutes)

1. Sign in as **Rohan** → avatar greets you; ask *"How are my investments doing?"*
2. Switch language to **हिन्दी**, ask by voice — replies in Hindi, spoken aloud.
3. Ask *"Can I afford a ₹50 lakh home loan for 20 years?"* → EMI/FOIR simulation; then *"Am I on track for retirement?"* → corpus projection + the exact extra SIP needed.
4. Ask about **term insurance** → Compliance Gate declines direct advice, books an RM callback → watch it land in the **RM Console** tab. Tap **✨ Prepare with Saarthi** → pre-meeting brief + drafted reply appear; hit **Approve & Send** → the message pops up in the customer's 🔔 feed.
4a. **Try to break the gate**: ask *"मुझे टर्म इंश्योरेंस के बारे में बताओ"* in Hindi, or *"my uncle's agent suggested a money-back plan, should I take it?"* — both get caught (pattern fast-path and LLM backstop respectively) and routed to the RM. Even a **multi-turn** dodge fails: ask about ULIPs, then a bare *"which of those suits me?"* — the context-aware backstop still gates it. Then ask *"Recommend a mutual fund"* → the reply cites the suitability engine's reasons, and the assessment appears in the Portfolio tab's **Advice Audit Trail**.
4b. While you talk, the **proactive heartbeat** fires — a 🔔 toast slides in unprompted ("Markets today: your funds +₹2,508").
5. Tap **Plan together** (Humsafar mode) → *"Can WE afford an ₹80 lakh home loan?"* → joint assessment on combined income; *"How should we split savings for our home goal?"* → impartial mediator plan.
6. In the **Humsafar** tab, tap **Generate this month's report** → the "State of our Union" household report writes itself.
7. Show the **Portfolio** tab: Financial Health Score gauge, allocation, holdings, goals, Saarthi Insights nudges.
