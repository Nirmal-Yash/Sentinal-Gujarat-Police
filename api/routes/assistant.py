"""Optional Groq-backed operations assistant; the API keeps credentials server-side."""
from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import require_authenticated

router = APIRouter(prefix="/assistant", tags=["assistant"], dependencies=[Depends(require_authenticated)])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    context: dict = Field(default_factory=dict)
    model: str | None = Field(default=None, max_length=100)


def _complete(payload: dict, api_key: str) -> dict:
    url = os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions")
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise HTTPException(502, "Groq authentication failed") from exc
        raise HTTPException(502, "Groq request failed") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HTTPException(502, "Groq service is unavailable") from exc


@router.post("/chat")
async def chat(body: ChatRequest):
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(503, "Groq integration is not configured")
    context = json.dumps(body.context, ensure_ascii=False)[:6000] if body.context else "{}"
    payload = {
        "model": body.model or os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
        "temperature": 0.2,
        "max_tokens": 800,
        "messages": [
            {"role": "system", "content": "You are the Sentinel Gujarat Police operations assistant. Give concise, evidence-based guidance from supplied context. Do not invent camera, plate, or alert data."},
            {"role": "user", "content": f"Context:\n{context}\n\nRequest:\n{body.message}"},
        ],
    }
    result = await asyncio.to_thread(_complete, payload, api_key)
    try:
        answer = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise HTTPException(502, "Groq returned an invalid response") from exc
    return {"answer": answer, "model": result.get("model", payload["model"]), "usage": result.get("usage")}


@router.get("/status")
async def status():
    return {"configured": bool(os.getenv("GROQ_API_KEY", "").strip()), "model": os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")}
