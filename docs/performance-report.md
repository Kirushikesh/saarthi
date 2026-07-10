# Saarthi — Performance & Evaluation Report (Round 1 prototype)

Two evaluations, reported separately and honestly:

1. a **development battery** (`scripts/benchmark.py`) the detector was iterated
   against — good for regression, but a number you tune toward is a number you
   should discount;
2. a **held-out set** (`scripts/benchmark.py --holdout`) authored *after* the
   gate was frozen, deliberately probing beyond it: unsupported languages
   (Gujarati, Punjabi, Odia), Devanagari terms absent from the regex
   (endowment/money-back), heavy code-mixing, and spelled-out products ("F and
   O"). **The held-out number is the one to trust.**

Every check is programmatic (pass/fail rubric), not hand-graded. Reproduce with
the backend running on :8000:

```bash
uv run python scripts/benchmark.py            # development battery
uv run python scripts/benchmark.py --holdout  # held-out (untuned) set
```

## Compliance gate — held-out set (the honest number)

12 attacks + 6 controls the gate was **never tuned against**:

| Metric | Value |
|---|---|
| Held-out attacks caught → RM lead | **12/12** |
| — by multilingual keyword fast-path | 1 |
| — by context-aware LLM backstop | **11** |
| Held-out vanilla controls wrongly gated (false positives) | **0/6** |

The signal that matters: on queries outside the development set, **the LLM
backstop carries the load, not the regex** (11 of 12) — including three
languages with *no* keyword coverage at all (Gujarati, Punjabi, Odia) and
Devanagari terms the pattern never listed. That is the design working as
intended: the keyword layer is a fast/free first pass, and the fail-closed LLM
classifier is the real net. `docs/holdout-results.json` has every query.

## Compliance gate — development battery

The gate is a three-layer detector feeding one deterministic middleware:
(1) multilingual regulated-keyword fast-path; (2) vanilla allow-list that
short-circuits common permitted queries; (3) an LLM intent-classifier backstop,
given prior turns, that adjudicates the keyword-free ambiguous middle
(paraphrase and multi-turn) — and **fails closed**: if the classifier errors,
the ambiguous query routes to a human rather than silently dropping protection.

| Metric | Value |
|---|---|
| Regulated-intent attacks (7 languages + evasions) | 27 |
| Caught → RM lead created | 27/27 |
| — incl. multi-turn (ambiguous follow-up, context-resolved) | 5/5 |
| — by keyword fast-path / LLM backstop | 18 / 9 |
| False positives (permitted queries wrongly routed) | 0/66 |

> These are strong, but they are on the set we developed against — read them as
> "no known regression," and read the held-out section above as the real
> generalization estimate.

## Advisory quality & grounding

| Metric | Value |
|---|---|
| Queries answered (dev battery) | 93/93, 0 errors |
| Tool-grounding rate (advisory queries) | 89% — the rest were educational definitions needing no data |
| Correct specialist tool for the intent | 98% (55/56 intent-tagged) |
| Language fidelity (reply script matches query) | 100% across en/hi/ta/te/kn/bn/mr |
| Suitability assessments audit-logged | every `check_suitability` call → advice audit trail |

**Not yet measured — stated plainly:** advisory *quality* (is the advice
good?). The rubric checks tool selection, grounding, language and the gate — not
whether a human advisor would endorse the recommendation. An LLM-as-judge +
human-panel evaluation of advisory quality is the round-2 plan. We would rather
name this gap than imply a 100% we didn't measure.

## Cost & latency (live from `GET /api/metrics`)

| Metric | Value |
|---|---|
| Latency p50 / p95 | ~5.8 s / ~11.1 s per advisory answer (6 concurrent) |
| Tokens per turn (avg) | ~3,670 in / ~240 out |
| Cost per advisory turn | ~₹0.06 (~$0.0007, gpt-4o-mini) |
| Projected cost per 1,000 advisory chats | ~₹58 |
| Human RM interaction (industry estimate) | ₹150–400 |

Latency is un-tuned gpt-4o-mini with sequential tool calls. Two mitigations are
already in the prototype and one is architectural: the UI now uses
**`/api/chat/stream`** (SSE) so tool-status pings and reply tokens render as
they generate — the customer watches Saarthi work instead of waiting on a
spinner; the deterministic layers (gate fast-path, all financial math) add zero
model latency; and production targets Bedrock with response streaming.

## What is deterministic vs. generated

All financial figures — EMI, FOIR, goal math, retirement corpus, tax headroom,
SIP targets, fair splits, **suitability verdicts and eligibility rules**,
behavioural signals — are computed **in code**; the LLM narrates. The compliance
gate is middleware, not a prompt: a regulated intent cannot reach the model
without the handoff directive, the gate fails closed on classifier error, and if
the model still skips the handoff the lead is created deterministically. Every
suitability assessment is written to an audit trail queryable at
`GET /api/suitability/{cid}`.

## Realtime voice

Gemini Live bidirectional audio; first spoken response typically within ~1–2 s
of end of speech; barge-in supported. The animated avatar lip-syncs to real
playback amplitude reported by the audio worklet (not a canned loop). Voice
delegates every substantive turn to the same brain — same tools, gate, audit
trail. (AWS path: Amazon Nova Sonic is the drop-in equivalent; see
[integration-architecture.md](integration-architecture.md).)

## Honest limitations (round-1 scope)

- Synthetic data, 5 personas; in-memory stores (RDS/DynamoDB in the target
  architecture).
- Account Aggregator is a faithful **mock** of the Sahamati consent/FI-data
  shape, not a live FIU integration.
- The benchmark rubric is programmatic; advisory-quality grading is round-2.
- The held-out set is 18 queries — enough to show the backstop generalizes and
  to refuse a false "100%," not enough to claim a production false-positive
  rate. A larger adversarial corpus with third-party-authored attacks is the
  round-2 plan.
