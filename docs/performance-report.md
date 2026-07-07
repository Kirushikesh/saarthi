# Saarthi — Performance Report (Round 1 prototype)

Measured on a 12-query benchmark across all 4 personas, 3 languages (English,
Hindi, Tamil), individual + household modes, and both vanilla-advice and
regulated (compliance-gate) flows. Live numbers at `GET /api/metrics`.

| Metric | Value |
|---|---|
| Advisory turns measured | 12 (100% answered) |
| Latency — average | ~5.2 s per advisory answer |
| Latency — p95 | ~7.7 s (multi-tool turns) |
| Tool-grounding rate | **100%** — every answer fetched real data; zero free-styled numbers |
| Compliance gate → RM lead conversion | **100%** (deterministic middleware fallback guarantees it) |
| Tokens per turn (avg) | ~3,540 in / ~290 out |
| Cost per advisory turn | **₹0.06** (~$0.0007, gpt-4o-mini) |
| Projected cost per 1,000 advisory chats | **~₹59** |
| Cost per RM: a human advisory interaction* | ₹150–400 (industry estimate) |

*The pitch: Saarthi answers the ~80% of queries that are informational/vanilla
at ~1/3000th the cost of an RM minute, and converts the remaining regulated
20% into fully-contextualized, pre-qualified RM leads.

## Accuracy posture

All financial figures (EMI, FOIR, goal math, retirement corpus, tax headroom,
SIP targets, fair splits) are computed **in code**, not by the LLM — the model
narrates deterministic tool outputs. The compliance gate is middleware, not a
prompt: a regulated-product intent cannot reach the model without the handoff
directive, and if the model still skips the handoff the lead is created
deterministically.

## Realtime voice

Gemini Live bidirectional audio: first spoken response typically starts within
~1–2 s of end of speech; barge-in (interrupting the avatar mid-sentence) is
supported. Voice shares the same brain, tools and compliance path as text.
