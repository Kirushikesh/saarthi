"""Saarthi API — FastAPI service exposing the agent orchestrator and bank data."""

import asyncio
import base64
import json
import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

from . import agents, data, heartbeat, suitability, voice

logger = logging.getLogger("saarthi.api")

app = FastAPI(title="Saarthi API", version="0.1.0")
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "static"


@app.on_event("startup")
async def _start_heartbeat():
    asyncio.create_task(heartbeat.run())

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
    sugam_mode: bool = False  # accessibility: simple language, short replies


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
        s = data.consent_status(cid)
        if s and not s["active"]:
            raise HTTPException(403, "consent required")
        raise HTTPException(404, "no linked partner")
    return h


class ConsentRequest(BaseModel):
    grant: bool


@app.get("/api/consent/{cid}")
def consent(cid: str):
    s = data.consent_status(cid)
    if not s:
        raise HTTPException(404, "no linked partner")
    return s


@app.post("/api/consent/{cid}")
def update_consent(cid: str, req: ConsentRequest):
    s = data.set_consent(cid, req.grant)
    if not s:
        raise HTTPException(404, "no linked partner")
    return s


class AARequest(BaseModel):
    link: bool


@app.get("/api/aa/{cid}")
def aa_status(cid: str):
    """Account Aggregator status: discovered institutions pre-consent,
    full external holdings once linked (mocked Sahamati AA rail)."""
    s = data.aa_status(cid)
    if not s:
        raise HTTPException(404, "customer not found")
    return s


@app.post("/api/aa/{cid}")
def aa_link(cid: str, req: AARequest):
    """Grant or revoke AA consent — external holdings appear in / vanish from
    the 360° portfolio instantly; every action is audit-logged."""
    s = data.aa_set(cid, req.link)
    if not s:
        raise HTTPException(404, "customer not found")
    return s


@app.get("/api/nudges/{cid}")
def nudges(cid: str):
    if not data.get_customer(cid):
        raise HTTPException(404, "customer not found")
    return agents.nudges(cid)


@app.get("/api/market/{cid}")
def market(cid: str):
    if not data.get_customer(cid):
        raise HTTPException(404, "customer not found")
    return data.market_pulse(cid)


@app.get("/api/behavior/{cid}")
def behavior(cid: str):
    """Behavioural profile derived from raw transactions (no pre-labels)."""
    b = data.behavior_summary(cid)
    if not b:
        raise HTTPException(404, "customer not found")
    return b


@app.get("/api/suitability/{cid}")
def suitability_audit(cid: str):
    """Advice audit trail: every suitability assessment recorded for this
    customer — the SEBI-style 'why was this recommended' record."""
    if not data.get_customer(cid):
        raise HTTPException(404, "customer not found")
    return {"audit_trail": suitability.audit_trail(cid)}


@app.get("/api/health-score/{cid}")
def health_score(cid: str):
    if not data.get_customer(cid):
        raise HTTPException(404, "customer not found")
    return data.financial_health(cid)


@app.get("/api/report/{cid}")
def report(cid: str):
    """Monthly Household Review (deterministic data + LLM narration)."""
    if not data.get_customer(cid):
        raise HTTPException(404, "customer not found")
    try:
        out = agents.household_report(cid)
    except Exception as e:
        raise HTTPException(502, f"Report generation failed: {e}")
    if "error" in out:
        raise HTTPException(404, out["error"])
    return out


@app.get("/api/metrics")
def metrics():
    """Live performance telemetry: latency, tokens, cost, tool usage, compliance."""
    out = agents.metrics_summary()
    out["voice_sessions"] = VOICE_SESSIONS["count"]
    out["heartbeat"] = {"beats": heartbeat.BEATS["count"],
                        "notifications_pushed": heartbeat.BEATS["pushed"],
                        "interval_seconds": heartbeat.INTERVAL_SECONDS}
    return out


VOICE_SESSIONS = {"count": 0}


@app.get("/api/notifications/{cid}")
def notifications(cid: str):
    """Customer's proactive-heartbeat notification feed."""
    if not data.get_customer(cid):
        raise HTTPException(404, "customer not found")
    return data.list_notifications(cid)


@app.post("/api/notifications/{cid}/read")
def read_notifications(cid: str):
    if not data.get_customer(cid):
        raise HTTPException(404, "customer not found")
    return data.mark_notifications_read(cid)


@app.get("/api/leads")
def leads():
    return list(reversed(data.LEADS))


@app.get("/api/leads/{lead_id}/brief")
def lead_brief(lead_id: str):
    """RM copilot: pre-meeting brief + drafted customer message for a lead."""
    if not data.get_lead(lead_id):
        raise HTTPException(404, "lead not found")
    try:
        return agents.lead_brief(lead_id)
    except Exception as e:
        raise HTTPException(502, f"Brief generation failed: {e}")


class ApproveRequest(BaseModel):
    message: str


@app.post("/api/leads/{lead_id}/approve")
def approve_lead(lead_id: str, req: ApproveRequest):
    """RM approves the drafted message — 'adviser approves, AI produces'.
    The message lands in the customer's notification feed."""
    lead = data.get_lead(lead_id)
    if not lead:
        raise HTTPException(404, "lead not found")
    lead["status"] = "RM MESSAGE SENT"
    lead["sent_message"] = req.message
    data.add_notification(
        lead["customer_id"], "📞",
        f"Your RM is on your {lead['product']} enquiry",
        req.message, source="rm",
    )
    return lead


@app.post("/api/chat")
def chat(req: ChatRequest):
    if not data.get_customer(req.customer_id):
        raise HTTPException(404, "customer not found")
    try:
        return agents.chat(req.customer_id, req.message, req.history, req.household_mode, req.sugam_mode)
    except Exception as e:  # surface LLM/config errors readably in the demo UI
        raise HTTPException(502, f"Advisor temporarily unavailable: {e}")


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest):
    """SSE variant of /api/chat: tool-status pings and reply tokens stream as
    they happen, then a final `done` payload identical to /api/chat's."""
    if not data.get_customer(req.customer_id):
        raise HTTPException(404, "customer not found")

    def gen():
        try:
            for ev in agents.chat_stream(req.customer_id, req.message, req.history,
                                         req.household_mode, req.sugam_mode):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'Advisor temporarily unavailable: {e}'})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


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
    VOICE_SESSIONS["count"] += 1
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


if FRONTEND_DIR.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIR / "assets"),
        name="frontend-assets",
    )


@app.get("/{full_path:path}", include_in_schema=False)
def serve_frontend(full_path: str):
    """Serve the bundled Vite app when backend and frontend share one container."""
    if not FRONTEND_DIR.exists():
        raise HTTPException(404, "frontend build not found")
    if full_path.startswith(("api/", "ws/")):
        raise HTTPException(404, "not found")

    requested = FRONTEND_DIR / full_path
    if requested.is_file():
        return FileResponse(requested)
    return FileResponse(FRONTEND_DIR / "index.html")
