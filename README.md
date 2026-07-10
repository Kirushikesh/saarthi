# Saarthi — AI Wealth Companion for IDBI Bank

**IDBI Innovate 2026 · Track 1: AI-Powered Digital Wealth Management · Team FinFusion.AI**

Every Track 1 entry will demo a multilingual chatbot with an avatar. Saarthi's argument to a bank is different: **it is built so the AI physically cannot do the things a bank must never let an AI do** — and everything it does do is deterministic, auditable and segment-aware.

1. **A regulated intent cannot reach the model un-gated.** The Compliance & Suitability Gate is *middleware, not prompt text* — a 3-layer detector (multilingual keyword fast-path → vanilla allow-list → context-aware LLM backstop that **fails closed to a human**) inspects every turn before the model sees it. If the model still skips the handoff, the RM lead is created deterministically.
2. **Every recommendation has an auditable "why".** A deterministic suitability engine scores each product against risk band, horizon, surplus, buffer, observed behaviour — plus hard regulatory eligibility (an NRI cannot be sold PPF/SSY; the engine, not the prompt, enforces it). Every assessment lands in a SEBI-style advice audit trail.
3. **No financial number is hallucinated.** EMI/FOIR, goal math, retirement corpus, tax headroom, SIP targets, fair splits — all computed in code. The LLM narrates; it never computes.

## Built to the bank's brief

What IDBI asked for explicitly (problem statement + AMA), and where Saarthi answers it:

| The bank's ask | Saarthi's answer |
|---|---|
| **Customer segmentation** (Mass / Mass Affluent / HNI / NRI) | Five personas across all four segments. The same brain runs a **different playbook per segment**: Mass gets buffer-first simplicity, HNI gets concentration/estate awareness with priority Wealth-RM routing, NRI gets NRE/NRO- and FEMA-aware advice with hard eligibility rules |
| **Holdings at other institutions** | A mocked **Account Aggregator** rail (Sahamati-style): consent-based, purpose-bound, revocable linking pulls other-bank savings, FDs, external MFs and demat equity into the 360° view — live in the demo, one click to link/revoke |
| **Lead generation for complex cases** | Two engines: the compliance gate converts regulated intents into qualified leads, and a **proactive opportunity scan** flags idle funds and unfundable goals to RMs — a customer with lakhs idle becomes a lead *without ever asking about insurance* |
| **Mobile-app integration** | React phone-shell speaking only `/api/*` + `/ws/*` — shaped for a WebView mini-app embed in IDBI GO ([integration path](docs/integration-architecture.md)) |
| **Frequent market-linked updates** | Daily market pulse translated into personal impact ("your funds today: +₹2,508") + a proactive heartbeat that notifies customers unprompted |
| **Avatar-based, multilingual** | Animated advisor with **real audio-driven lip-sync** (mouth follows the actual voice amplitude), realtime voice (Gemini Live, barge-in), 7 languages across text and speech |

## Everything in the box

| Capability | What it does |
|---|---|
| 🛡️ Compliance gate + deterministic handoff | 3-layer regulated-intent detection in 7 languages; fails closed; lead creation guaranteed by middleware, not model goodwill |
| 🎯 Suitability engine + audit trail | Deterministic verdicts (SUITABLE / WITH_CAUTION / NOT_SUITABLE) with reasons + eligibility rules; every assessment recorded (`GET /api/suitability/{cid}`) |
| 👥 Segment playbooks | Mass / Mass Affluent / HNI / NRI advisory treatment diverges: products, thresholds, tone, RM routing |
| 🔗 Account Aggregator 360° | External holdings under revocable AA consent; they feed net worth, health score, suitability and idle-cash detection |
| 🤝 Opportunity leads | Heartbeat scans convert idle funds / unfundable goals into RM leads with priority by segment |
| 📋 RM copilot | Every lead gets an AI pre-meeting brief + drafted customer reply — the **RM approves, the AI produces** |
| 🧮 Scenario simulation | "Can I afford a ₹50L home loan?" → EMI, FOIR, surplus math with a verdict |
| 🧭 Retirement / 🧾 tax / 📈 target-SIP | Corpus projection (4% rule), 80C/80CCD(1B) headroom from actual SIPs & payroll, inverse SIP math — all code-computed |
| 🧠 Behavioural analytics | Income stability, SIP discipline, discretionary share **derived from raw transaction narrations** — feeds suitability |
| ❤️ Financial Health Score | 0–100 across four measurable pillars, on the dashboard and as an agent tool |
| 🫀 Proactive heartbeat | LLM-free background pulse; notifications arrive unprompted (market impact, drift, idle surplus, off-track goals, tax headroom) |
| 🎙️ Realtime voice avatar | Gemini Live bidirectional audio with barge-in; the animated advisor lip-syncs to playback amplitude from the audio worklet |
| 🌏 7 languages | English, Hindi, Tamil, Telugu, Kannada, Bengali, Marathi — UI, agent replies, and voice |
| 🏠 Household mode | Couples plan jointly under **mutual, revocable, audit-logged consent** (DPDP-aligned, enforced in the data layer); impartial mediator for split decisions; one-tap Monthly Household Review |
| ♿ Sugam mode | Accessibility mode (RPwD Act / WCAG-aligned): larger text/targets, contrast, spoken alerts, simple-language replies |
| 📏 Evaluation & telemetry | Scripted multilingual benchmark **plus a held-out attack set we did not tune against** (`scripts/benchmark.py --holdout`) + live telemetry at `GET /api/metrics` |

## Architecture

```
Browser (React phone shell, animated avatar w/ amplitude lip-sync, AudioWorklets)
   │ /api/chat + /api/chat/stream (SSE)   │ WS /ws/voice/{cid} (16kHz up / 24kHz down)
   ▼                                      ▼
FastAPI ──────────────────────► ADK live session (Gemini Live, barge-in)
   │                                      │ ask_saarthi(question)  ← thin voice layer
   ▼                                      ▼
LangChain create_agent  ◄─────────────────┘   ← one brain for both channels
   ├── @tools: portfolio (incl. AA externals) · household view · loan sim
   │           goal/SIP/retirement/tax math · health score · market pulse ·
   │           suitability check (audited) · behavioural profile · RM lead
   ├── ComplianceGateMiddleware (wrap_model_call): 3-layer detector,
   │   fails closed → hard directive + deterministic lead fallback
   ├── Segment playbooks: Mass / Mass Affluent / HNI / NRI treatment
   ├── Suitability engine: deterministic scoring + eligibility rules → audit trail
   ├── Account Aggregator mock: consent-gated external holdings
   ├── Behavioural analytics: raw narrations → behaviour signals
   ├── Proactive heartbeat: market rescan + opportunity-lead scan (no LLM)
   └── Synthetic bank data (round-1 scope) + RM lead queue + notifications
```

- **Brain**: LangChain `create_agent` — provider-agnostic via `init_chat_model`, so the same agent runs on **Amazon Bedrock** inside IDBI's AWS landing zone (prototype uses `LLM_MODEL`).
- **Streaming UX**: `/api/chat/stream` streams tool-status pings and reply tokens (SSE), so the customer watches Saarthi work instead of staring at a spinner.
- **Voice**: Google ADK drives Gemini Live; the voice agent delegates every substantive question to the same brain — shared tools, compliance, scoping.

> Round-1 note: all data is **synthetic and self-generated** (5 personas across Mass / Mass Affluent / HNI / NRI segments with 12 months of raw transactions, holdings, external AA accounts and joint links). No real customer data anywhere. Product shelf reflects the post-2023 reality: IDBI MF schemes transferred to **LIC MF**, distributed by the bank as an AMFI-registered distributor (regular plans).

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
uv run pytest tests/                       # 45 LLM-free tests: gate layers (incl.
                                           # fail-closed), suitability + eligibility,
                                           # AA consent, opportunity leads, loan math
uv run python scripts/benchmark.py         # scripted multilingual eval (7 languages,
                                           # incl. multi-turn gate attacks)
uv run python scripts/benchmark.py --holdout   # held-out attacks we did NOT tune against
```

Results — the development battery and the held-out set are reported separately
and honestly (the held-out number is the one to trust):
[docs/performance-report.md](docs/performance-report.md).
Bank-stack integration path (IDBI GO embed, auth, Account Aggregator, Bedrock/
Nova Sonic): [docs/integration-architecture.md](docs/integration-architecture.md).

## Deploy

The app is deployed to an **AWS EC2** instance running Docker. The deployment process builds the full-stack Docker image, pushes it to ECR, and deploys it to the EC2 instance using a PowerShell script.

### 1. Local Deployment (via Makefile)
You can deploy directly from your local terminal using the Makefile targets:
```powershell
# Fresh deployment (builds, tags, pushes, and launches on EC2)
make ec2-deploy ENV_FILE=backend/.env REGION=us-west-2

# In-place update to a running EC2 instance
make ec2-update ENV_FILE=backend/.env REGION=us-west-2
```

### 2. CI/CD Deployment (via GitHub Actions)
A GitHub Actions workflow is configured in [.github/workflows/deploy.yml](.github/workflows/deploy.yml). Any push to the `master` branch will trigger a deployment.

### Required Secrets / Environment Variables
To deploy and run the Bedrock-only advisor:
* `AWS_ACCESS_KEY_ID` & `AWS_SECRET_ACCESS_KEY`: Deployment credentials (requires permissions for ECR, SSM, EC2).
* `AWS_REGION`: The region containing your ECR repository and Bedrock models (defaults to `us-west-2`).
* `EC2_INSTANCE_ID`: The target AWS EC2 instance ID.
* `GOOGLE_API_KEY`: Required for the Gemini Live voice companion.
* `LLM_MODEL`: Bedrock model ID/inference profile ARN (defaults to `arn:aws:bedrock:us-west-2:329597158967:inference-profile/us.anthropic.claude-sonnet-4-6`).


## Demo script (3 minutes)

1. Sign in as **Rohan** → the animated advisor greets you; ask *"How are my investments doing?"* — the reply **streams live** with tool-status updates.
2. Portfolio tab → **"Complete your 360°"** → link HDFC + SBI MF via **Account Aggregator** → net worth and health score update instantly; revoke to show consent teeth.
3. Switch to **हिन्दी**, ask by voice — the avatar **lip-syncs** to her own speech.
4. Ask *"Can I afford a ₹50 lakh home loan for 20 years?"* → EMI/FOIR simulation; *"Am I on track for retirement?"* → corpus projection + exact extra SIP.
5. Ask about **term insurance** → the Compliance Gate declines direct advice and routes to an RM → watch the lead land in the **RM Console** (🛡️ Compliance badge) beside 💡 **Opportunity** leads the heartbeat generated on its own (Anil's idle ₹32L). Tap **✨ Prepare with Saarthi** → pre-meeting brief + drafted reply → **Approve & Send** → lands in the customer's 🔔 feed.
6. Sign in as **Vikram (NRI)** → ask *"Should I open a PPF account?"* → hard eligibility refusal with the regulatory reason; ask about **cross-border tax** → routed to the NRI desk. Same brain, different segment, different treatment.
7. Close with **Household mode**: Rohan + Priya plan jointly under mutual DPDP consent — *"Can WE afford an ₹80 lakh home loan?"*, fair-split mediation, and the one-tap **Monthly Household Review**.
