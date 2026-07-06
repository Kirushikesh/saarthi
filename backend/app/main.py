"""Saarthi API — FastAPI service exposing the agent orchestrator and bank data."""

import asyncio
import base64
import json
import logging

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

from . import agents, data, voice

logger = logging.getLogger("saarthi.api")

app = FastAPI(title="Saarthi API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # demo scope; locked to app domains in production
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    customer_id: str
    message: str
    history: list[dict] = []
    household_mode: bool = False


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "saarthi-api"}


@app.get("/api/customers")
def customers():
    return data.list_customers()


@app.get("/api/portfolio/{cid}")
def portfolio(cid: str):
    p = data.portfolio_summary(cid)
    if not p:
        raise HTTPException(404, "customer not found")
    return p


@app.get("/api/household/{cid}")
def household(cid: str):
    h = data.household_summary(cid)
    if not h:
        raise HTTPException(404, "no linked partner")
    return h


@app.get("/api/nudges/{cid}")
def nudges(cid: str):
    if not data.get_customer(cid):
        raise HTTPException(404, "customer not found")
    return agents.nudges(cid)


@app.get("/api/leads")
def leads():
    return list(reversed(data.LEADS))


@app.post("/api/chat")
def chat(req: ChatRequest):
    if not data.get_customer(req.customer_id):
        raise HTTPException(404, "customer not found")
    try:
        return agents.chat(req.customer_id, req.message, req.history, req.household_mode)
    except Exception as e:  # surface LLM/config errors readably in the demo UI
        raise HTTPException(502, f"Advisor temporarily unavailable: {e}")


async def _voice_to_client(ws: WebSocket, events, leads_seen: set):
    """Model → browser: audio chunks, transcripts, barge-in, RM-lead flashes."""
    async for event in events:
        if getattr(event, "interrupted", False):
            await ws.send_text(json.dumps({"type": "interrupted"}))
            continue
        if getattr(event, "turn_complete", False):
            await ws.send_text(json.dumps({"type": "turn_complete"}))
            continue

        # Consolidated (partial=False) transcripts label the conversation.
        if not getattr(event, "partial", False):
            in_tx = getattr(event, "input_transcription", None)
            if in_tx and in_tx.text:
                await ws.send_text(json.dumps({"type": "transcript", "who": "user", "text": in_tx.text}))
            out_tx = getattr(event, "output_transcription", None)
            if out_tx and out_tx.text:
                await ws.send_text(json.dumps({"type": "transcript", "who": "agent", "text": out_tx.text}))

        # Surface tool activity so the UI can show "consulting the brain…"
        for call in event.get_function_calls():
            await ws.send_text(json.dumps({"type": "thinking", "tool": call.name}))
        # New RM lead created during this voice turn? Tell the UI.
        for lead in data.LEADS:
            if lead["id"] not in leads_seen:
                leads_seen.add(lead["id"])
                await ws.send_text(json.dumps({"type": "lead", "lead": lead}))

        content = getattr(event, "content", None)
        if not content or not content.parts:
            continue
        for part in content.parts:
            inline = getattr(part, "inline_data", None)
            if inline and inline.data and inline.mime_type.startswith("audio/"):
                await ws.send_text(json.dumps({
                    "type": "audio",
                    "data": base64.b64encode(inline.data).decode(),
                }))


async def _client_to_voice(ws: WebSocket, queue):
    """Browser → model: mic PCM (and optional typed text)."""
    while True:
        message = json.loads(await ws.receive_text())
        if message.get("type") == "audio":
            queue.send_realtime(
                voice.types.Blob(
                    mime_type=f"audio/pcm;rate={voice.INPUT_SAMPLE_RATE}",
                    data=base64.b64decode(message["data"]),
                )
            )
        elif message.get("type") == "text":
            queue.send_content(
                voice.types.Content(
                    role="user",
                    parts=[voice.types.Part(text=message["data"])],
                )
            )


@app.websocket("/ws/voice/{cid}")
async def voice_ws(ws: WebSocket, cid: str, household: bool = False):
    if not data.get_customer(cid):
        await ws.close(code=4404)
        return
    await ws.accept()
    logger.info("Voice session started: %s (household=%s)", cid, household)
    events, queue = await voice.start_live_session(cid, household)
    leads_seen = {l["id"] for l in data.LEADS}
    try:
        await asyncio.gather(
            _voice_to_client(ws, events, leads_seen),
            _client_to_voice(ws, queue),
        )
    except WebSocketDisconnect:
        logger.info("Voice session ended: %s", cid)
    except Exception:
        logger.exception("Voice session error for %s", cid)
    finally:
        queue.close()
