"""Realtime voice layer: Google ADK + Gemini Live, delegating to the LangChain brain.

Pattern (from langchain-ai/google-adk-realtime-deepagents-example): the voice
agent is deliberately thin — a natural, low-latency spoken interface. Anything
substantive is delegated to the same `create_agent` brain that powers text chat,
via one tool: `ask_saarthi`. So voice and text share tools, compliance gate,
and customer scoping.
"""

import asyncio
import logging
import os

from google.adk.agents import Agent
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import InMemoryRunner
from google.genai import types

from . import agents, data

logger = logging.getLogger("saarthi.voice")

LIVE_MODEL = os.environ.get("LIVE_MODEL", "gemini-3.1-flash-live-preview")
APP_NAME = "saarthi-voice"

INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000

VOICE_INSTRUCTIONS = """You are Saarthi, IDBI Bank's warm, professional voice wealth companion, in a live spoken conversation with {name} ({age}, {occupation}, {segment} segment).
{household_note}

You have one tool: `ask_saarthi`. It is the bank's advisory brain — it knows the customer's full portfolio, can simulate loans, plan goals and handle compliance. Call it for ANY question about their money, portfolio, goals, loans, products or plans. Pass the customer's question faithfully.

Rules:
- Keep spoken replies short and natural — you're heard, not read. No markdown, no bullet lists, no long numbers recited digit by digit (say "about 23 lakh rupees", not "2311589").
- When you call ask_saarthi, briefly acknowledge ("Let me check that for you...") — the answer arrives in a few seconds; then summarize it conversationally in 2-4 sentences and offer to go deeper.
- If ask_saarthi's answer mentions a Relationship Manager callback, make sure to tell the customer clearly.
- Speak the customer's language: mirror whatever Indian language they speak — Hindi, Tamil, Telugu, Kannada, Bengali, Marathi or English — and switch instantly if they do.
- For small talk, respond directly without the tool.
"""


def build_voice_agent(cid: str, household_mode: bool) -> Agent:
    """A per-connection ADK live agent, personalized and bound to one customer."""
    customer = data.get_customer(cid)
    history: list[dict] = []  # voice-turn memory for the brain, per connection

    async def ask_saarthi(question: str) -> dict:
        """Ask the bank's wealth advisory brain about the customer's finances:
        portfolio, spending, goals, loan affordability, product suitability.

        Args:
            question: The customer's question, phrased faithfully.

        Returns:
            The advisor's answer plus any RM-callback info.
        """
        result = await asyncio.to_thread(
            agents.chat, cid, question, list(history), household_mode
        )
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": result["reply"]})
        out = {"answer": result["reply"]}
        if result.get("lead"):
            out["rm_callback"] = (
                f"Booked: lead {result['lead']['id']} for {result['lead']['product']}, "
                "an IDBI Relationship Manager will call within 24 hours."
            )
        return out

    household_note = ""
    if household_mode and customer.get("partner_id"):
        partner = data.get_customer(customer["partner_id"])
        household_note = (
            f"Humsafar mode is ON: you are advising {customer['name'].split()[0]} and "
            f"{partner['name'].split()[0]} together as a household."
        )

    return Agent(
        name="saarthi_voice",
        model=LIVE_MODEL,
        description="Saarthi realtime voice wealth companion",
        instruction=VOICE_INSTRUCTIONS.format(
            name=customer["name"], age=customer["age"],
            occupation=customer["occupation"], segment=customer["segment"],
            household_note=household_note,
        ),
        tools=[ask_saarthi],
    )


async def start_live_session(cid: str, household_mode: bool):
    """Open an ADK live session for this customer. Returns (events, queue)."""
    runner = InMemoryRunner(app_name=APP_NAME, agent=build_voice_agent(cid, household_mode))
    session = await runner.session_service.create_session(app_name=APP_NAME, user_id=cid)
    queue = LiveRequestQueue()
    events = runner.run_live(
        user_id=cid,
        session_id=session.id,
        live_request_queue=queue,
        run_config=RunConfig(
            streaming_mode=StreamingMode.BIDI,
            response_modalities=["AUDIO"],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
        ),
    )
    return events, queue
