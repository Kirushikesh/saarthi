# Saarthi × IDBI — Integration Architecture (target state)

How the round-1 prototype maps onto IDBI Bank's actual stack. The prototype
deliberately isolates every bank-touching concern behind a thin layer so each
one swaps for the bank-grade equivalent without touching the advisory brain.

## 1. Embedding in the IDBI mobile app

```
IDBI GO (native app)
 ├── Saarthi module  ← WebView/mini-app shell (phase 1) or native SDK (phase 2)
 │     • rendered by the same React bundle as the prototype
 │     • receives a short-lived session JWT from the host app (no separate login)
 │     • voice: mic/audio session brokered by the host app's permissions
 └── Push notifications ← heartbeat alerts delivered via the app's existing
       push channel (FCM/APNs), deep-linking into the Saarthi module
```

- **Phase 1 (fastest to pilot):** WebView mini-app inside IDBI GO — zero app-release
  coupling, feature-flagged rollout by customer segment.
- **Phase 2:** native SDK for the avatar/voice surface once the pilot proves engagement.
- The prototype's phone-shell + REST/WS API is already shaped like this: the
  frontend talks only to `/api/*` and `/ws/voice/*`, so the embed swap is a
  packaging change, not a rewrite.

## 2. Identity & authorization

| Prototype (demo scope) | Target state |
|---|---|
| Persona picker, open CORS | Host app injects a **short-lived JWT** minted by IDBI's identity provider on module launch |
| `customer_id` path params | Customer identity comes **only from the token claims** — the API never trusts a client-supplied id |
| — | API Gateway (AWS) enforces authN, rate limits, WAF; mTLS to backend services |

The prototype already enforces customer scoping in one place (tools are
closures bound to a single customer), so wiring the id to a token claim is a
one-line change at the API boundary.

## 3. Data plane — where the 360° view really comes from

```
                       ┌────────────────────────────────────────────┐
                       │  Saarthi data layer (today: synthetic dict) │
                       └───────┬────────────────────────────────────┘
   swaps for →                 │
 ┌───────────────┬─────────────┼──────────────────┬──────────────────┐
 │ CBS (Finacle) │ MF RTA feeds │ NPS/EPF via CRAs │ Account Aggregator│
 │ balances, FDs │ (CAMS/KFin)  │                  │ (Sahamati/AA)     │
 │ transactions  │ holdings,SIPs│                  │ external holdings │
 └───────────────┴──────────────┴──────────────────┴──────────────────┘
```

- **Internal holdings:** core banking (balances, FDs, transactions), MF RTA
  feeds (CAMS/KFintech) for scheme holdings and SIP mandates, CRA feeds for NPS/EPF.
- **External holdings — the AMA's explicit ask** ("investments through other
  institutions"): the **Account Aggregator framework**. Saarthi's Humsafar
  consent flow is deliberately modeled on AA consent semantics — purpose-bound,
  revocable, audit-logged — so extending consent UX from "share with partner"
  to "fetch via AA" reuses the same pattern the DPDP/AA ecosystem requires.
- **Behavioural analytics:** the narration classifier + behaviour signals
  (`analytics.py`) run today on raw statement lines — exactly the shape AA
  FI data arrives in.

## 4. AI plane — inside the AWS landing zone

| Prototype | Target (IDBI sandbox is AWS) |
|---|---|
| `init_chat_model("openai:gpt-4o-mini")` | Same LangChain string → **Amazon Bedrock** (`bedrock_converse:...`) — the brain is provider-agnostic by construction |
| Gemini Live voice session | **Amazon Nova Sonic** speech-to-speech; the voice layer is a thin adapter that delegates every substantive turn to the brain via one tool (`ask_saarthi`), so the swap does not touch tools, compliance, or scoping |
| Gate LLM backstop on gpt-4o-mini | Small Bedrock model (Haiku-class) — latency-critical, cost-trivial |
| In-memory stores (leads, notifications, audit trail, consent log) | RDS/PostgreSQL (leads, consent, **advice audit trail** — a compliance record wants a relational, queryable store); DynamoDB for notification feeds |
| Heartbeat: in-process loop over all customers | EventBridge-scheduled batch over customer **segments** (mass daily, affluent/HNI intraday on market triggers) fanning out to SQS workers |

## 5. Compliance & audit posture

- The gate is **middleware, not prompt text**: detection (multilingual
  patterns + LLM backstop) and enforcement (directive injection + deterministic
  lead fallback) both run outside the model. Benchmarked at 100% catch / 0%
  false-positive across 7 languages (see performance report).
- Every suitability assessment writes a structured audit record — the artifact
  a SEBI/internal-audit review asks for ("why was this product recommended to
  this customer on this date").
- DPDP alignment: household data sharing is consent-gated in the **data layer**;
  every grant/revoke is timestamped and audit-logged; revocation cuts access
  instantly.

## 6. What stays exactly as-is

The advisory brain (LangChain `create_agent` + tools + middleware), the
deterministic calculators, the suitability engine, the behavioural analytics,
and the React surface — the pieces that carry the product value — run
unchanged in the landing zone. Everything bank-specific was kept at the edges
by design.
