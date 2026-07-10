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
  institutions"): the **Account Aggregator framework**. This is *demonstrated
  in the prototype*, not just described — `data.aa_*` mocks the Sahamati AA
  rail: pre-consent only institution names are discoverable, and a
  purpose-bound, revocable, audit-logged consent grant makes external savings,
  FDs, other-AMC mutual funds and demat equity flow into the same
  `portfolio_summary` that feeds net worth, the health score, suitability and
  idle-cash lead detection. The FI-data shape (`fip`, account type, value)
  mirrors what a live FIU integration delivers, so the swap from mock to real
  AA is a data-source change behind an unchanged interface. The Household
  consent flow shares the identical semantics (purpose-bound, revocable,
  logged).
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

## 5. Segmentation, lead generation & the RM

- **Segment-differentiated advisory** (the bank's headline ask) is a per-segment
  playbook injected into the same brain: Mass / Mass Affluent / HNI / NRI get
  different product emphasis, thresholds, tone and RM-routing. The suitability
  engine additionally enforces hard eligibility (e.g. NRIs cannot open PPF/SSY)
  deterministically, so segment is not merely a label in a prompt.
- **Lead generation is broad, not just compliance exhaust**: alongside the gate
  (regulated intent → RM), a proactive opportunity scan (in the heartbeat)
  turns idle funds and unfundable goals into RM leads — the "complex cases →
  seasoned RM" function the AMA emphasized, triggered even when no regulated
  product is mentioned. Leads carry a `kind` (`compliance` | `opportunity`) and
  segment-scaled priority (HNI/NRI → HIGH). In production this scan is an
  EventBridge batch over CBS/analytics; leads land in the bank's CRM/LMS.

## 6. Compliance & audit posture

- The gate is **middleware, not prompt text**: detection (multilingual
  patterns + LLM backstop) and enforcement (directive injection + deterministic
  lead fallback) both run outside the model. It **fails closed** — if the LLM
  classifier errors, the ambiguous query routes to a human rather than dropping
  protection. See the performance report for held-out vs. development numbers
  (reported separately; the held-out set is the honest generalization estimate).
- Every suitability assessment writes a structured audit record — the artifact
  a SEBI/internal-audit review asks for ("why was this product recommended to
  this customer on this date").
- DPDP alignment: household data sharing is consent-gated in the **data layer**;
  every grant/revoke is timestamped and audit-logged; revocation cuts access
  instantly.

## 7. What stays exactly as-is

The advisory brain (LangChain `create_agent` + tools + middleware), the
deterministic calculators, the suitability engine, the behavioural analytics,
and the React surface — the pieces that carry the product value — run
unchanged in the landing zone. Everything bank-specific was kept at the edges
by design.
