"""
server.py - FastAPI REST server for SRE OpenEnv
Exposes /reset, /step, /state endpoints per OpenEnv spec.
Also serves the Gradio UI.
"""
from __future__ import annotations

import os
import uuid
from typing import Any, Dict, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from env import SREEnvironment, SREAction, ResetResult, StepResult

app = FastAPI(
    title="SRE OpenEnv",
    description="AI agent environment simulating real-world SRE incident response",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Session management ────────────────────────────────────────────────────────
# In-memory sessions (fine for demo / HF Space)
_sessions: Dict[str, SREEnvironment] = {}


def _get_env(session_id: str) -> SREEnvironment:
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found. Call /reset first.")
    return _sessions[session_id]


# ── Request/Response models ───────────────────────────────────────────────────

class ResetRequest(BaseModel):
    task_id: str = "easy"
    session_id: Optional[str] = None


class StepRequest(BaseModel):
    action: str
    session_id: str


class StateRequest(BaseModel):
    session_id: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

# Root moved to main.py for Gradio redirect


@app.get("/health")
async def health():
    return {"status": "ok", "sessions": len(_sessions)}


@app.post("/reset")
async def reset(req: Optional[ResetRequest] = None) -> Dict[str, Any]:
    """Initialize or reset an environment session."""
    if req is None:
        req = ResetRequest()
    
    session_id = req.session_id or str(uuid.uuid4())

    env = SREEnvironment(task_id=req.task_id)
    try:
        result = env.reset()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    _sessions[session_id] = env

    return {
        "session_id": session_id,
        "task_id": result.task_id,
        "task_description": result.task_description,
        "max_steps": result.max_steps,
        "observation": result.observation.model_dump(),
    }


@app.post("/step")
async def step(req: StepRequest) -> Dict[str, Any]:
    """Execute one action and return observation, reward, done, info."""
    env = _get_env(req.session_id)
    action = SREAction(raw=req.action)
    result: StepResult = env.step(action)

    return {
        "observation": result.observation.model_dump(),
        "reward": result.reward.model_dump(),
        "done": result.done,
        "info": result.info,
    }


@app.get("/state")
async def state(session_id: str) -> Dict[str, Any]:
    """Return full internal state (for evaluation/debugging)."""
    env = _get_env(session_id)
    return {"session_id": session_id, "state": env.state(), "score": env.get_task_score()}


@app.get("/score")
async def score(session_id: str) -> Dict[str, Any]:
    """Get current task score."""
    env = _get_env(session_id)
    return {"session_id": session_id, "score": env.get_task_score()}


@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Clean up a session."""
    _sessions.pop(session_id, None)
    return {"deleted": session_id}


@app.get("/tasks")
async def list_tasks():
    """List available tasks."""
    from tasks import TASK_REGISTRY
    return {
        "tasks": [
            {
                "id": k,
                "name": v["name"],
                "difficulty": v["difficulty"],
                "description": v["description"],
                "max_steps": v["max_steps"],
            }
            for k, v in TASK_REGISTRY.items()
        ]
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
