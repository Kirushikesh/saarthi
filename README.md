# Saarthi — AI Wealth Companion for IDBI Bank

**IDBI Innovate 2026 · Track 1: AI-Powered Digital Wealth Management · Team FinFusion.AI**

Saarthi is an avatar-based, multilingual AI wealth advisor designed to embed inside IDBI Bank's mobile app. It gives every retail liability customer a 360° financial view and goal-based, suitability-aware advisory — and introduces **Humsafar mode**, India's first household-level advisory experience: joint net worth, joint goals, joint affordability simulations and an impartial AI mediator for shared money decisions.

## Key capabilities

| Capability | What it does |
|---|---|
| 🧑‍✈️ Avatar advisor | Animated avatar with voice + text in English & Hindi (Web Speech API) |
| 📊 360° portfolio | Savings, FDs, MFs, NPS, EPF, categorized spends, goals — one dashboard |
| 🎯 Suitability engine | Age, risk-profile and segment-aware recommendations, down to specific IDBI MF schemes |
| 🧮 Scenario simulation | "Can I afford a ₹50L home loan?" → EMI, FOIR, surplus math with a clear verdict |
| 🛡️ Compliance & Suitability Gate | Vanilla products (FD/RD/MF/PPF/NPS) advised directly; regulated products (insurance, ULIP, PMS, AIF) auto-route to a human RM as a **qualified lead** — the SEBI/IRDAI-compliant hybrid model IDBI asked for |
| 👫 Humsafar mode | Linked partners get combined analysis, joint goal planning and a data-driven mediator |
| 🔔 Proactive nudges | Allocation gaps, idle surplus, thin emergency funds, off-track goals |

## Architecture

```
React (mobile-app shell, avatar, voice)  →  FastAPI (Saarthi API)
                                              └── Orchestrator (LLM tool-use loop)
                                                    ├── Portfolio & Net-Worth agent
                                                    ├── Scenario Simulation agent (EMI/FOIR)
                                                    ├── Household (Humsafar) agent
                                                    ├── Product Catalog / Suitability
                                                    └── Compliance Gate → RM Lead queue
                                              └── Synthetic bank data (round-1 scope)
```

Prototype LLM: OpenAI API. Production target: the same orchestration on **Amazon Bedrock** inside IDBI's AWS landing zone (provider-agnostic tool-use layer — one-line swap), with RDS for the bank book and core-banking APIs replacing the synthetic layer.

> Round-1 note: per the hackathon instructions, all data is **synthetic and self-generated** (4 personas across Mass / Mass Affluent / HNI segments with 12 months of categorized transactions, holdings and joint-account links). No real customer data anywhere.

## Run locally

```bash
# backend
cd backend
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
export OPENAI_API_KEY=sk-...
./.venv/bin/uvicorn app.main:app --port 8000

# frontend (second terminal)
cd frontend
npm install
npm run dev        # http://localhost:5173 (proxies /api to :8000)
```

## Deploy

- **Backend → Railway**: point a service at `backend/` (railway.toml included), set `OPENAI_API_KEY`.
- **Frontend → Vercel**: point a project at `frontend/`, set `VITE_API_URL=https://<railway-app>.up.railway.app`.

## Demo script (3 minutes)

1. Sign in as **Rohan** → avatar greets you; ask *"How are my investments doing?"*
2. Switch language to **हिन्दी**, ask by voice — replies in Hindi, spoken aloud.
3. Ask *"Can I afford a ₹50 lakh home loan for 20 years?"* → EMI/FOIR simulation.
4. Ask about **term insurance** → Compliance Gate declines direct advice, books an RM callback → watch it land in the **RM Console** tab.
5. Tap **Plan together** (Humsafar mode) → *"Can WE afford an ₹80 lakh home loan?"* → joint assessment on combined income; *"How should we split savings for our home goal?"* → impartial mediator plan.
6. Show the **Portfolio** tab: allocation, holdings, goals, Saarthi Insights nudges.
