"""Kun backend — FastAPI app entrypoint (`app`).

JSONL event log + in-memory state builder. NO SQLite, NO database (CONTRACT §7).
Run: `uvicorn app.main:app --port 8000` (from repo root or from backend/).
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router
from app.events import ensure_sample_bundled

app = FastAPI(title="Kun backend", version="0.1.0")

# CORS open to the Vite dev origin (and localhost variants) for the cockpit (W2).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
def _on_startup() -> None:
    # Bundle the reference replay so GET /missions/mission_fashion_sample/* works OOTB
    # (does not overwrite an existing log).
    ensure_sample_bundled()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
