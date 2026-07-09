"""Saarthi's proactive heartbeat — the advisor that reaches out first.

A background task wakes on a fixed pulse, re-reads every customer's portfolio
against today's market, and pushes newly relevant insights (market impact on
their funds, allocation drift, idle surplus, off-track goals, thin emergency
buffer, unused tax headroom) to their notification feed.

At most ONE new notification per customer per beat, deduped by title, so
alerts arrive as a steady pulse rather than a dump — the customer sees
Saarthi noticing things over time, unprompted.

Deterministic and LLM-free: each beat is pure data math (see agents.nudges),
so it costs nothing to run continuously. In production this maps to a
scheduled job over the bank's CBS/analytics store with push notifications
through the IDBI mobile app.
"""

import asyncio
import logging
import os

from . import agents, data

logger = logging.getLogger("saarthi.heartbeat")

INTERVAL_SECONDS = int(os.environ.get("HEARTBEAT_SECONDS", "40"))

# (customer_id, nudge title) pairs already delivered — a nudge is re-delivered
# only if its content (and hence title) changes, e.g. a new day's market move.
_delivered: set = set()

BEATS = {"count": 0, "pushed": 0, "opportunity_leads": 0}


def beat_once():
    """One pulse: scan every customer, push at most one fresh insight each.
    Also runs the opportunity-lead scan — complex/high-value cases (idle
    funds, underfunded goals) become RM leads even though no regulated
    product was ever mentioned, per the bank's broad lead-generation ask."""
    for lead in data.scan_opportunity_leads():
        BEATS["opportunity_leads"] += 1
        data.add_notification(
            lead["customer_id"], "🤝",
            f"Flagged for your RM: {lead['product']}",
            "Saarthi spotted this in your finances and set up a review with a "
            "Relationship Manager — they'll reach out; no action needed.",
        )
    pushed = []
    for cid in data.CUSTOMERS:
        for n in agents.nudges(cid):
            key = (cid, n["title"])
            if key in _delivered:
                continue
            _delivered.add(key)
            pushed.append(data.add_notification(cid, n["icon"], n["title"], n["body"]))
            break  # one per customer per beat — keep the pulse steady
    BEATS["count"] += 1
    BEATS["pushed"] += len(pushed)
    return pushed


async def run():
    """Background loop; started from the FastAPI startup hook."""
    logger.info("Heartbeat started (every %ss)", INTERVAL_SECONDS)
    while True:
        try:
            pushed = beat_once()
            if pushed:
                logger.info("Heartbeat pushed %d notification(s)", len(pushed))
        except Exception:
            logger.exception("Heartbeat beat failed")
        await asyncio.sleep(INTERVAL_SECONDS)
