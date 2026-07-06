"""Saarthi API — FastAPI service exposing the agent orchestrator and bank data."""

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

from . import agents, data

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
