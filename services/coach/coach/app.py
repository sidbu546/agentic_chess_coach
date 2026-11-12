"""HTTP API of the coach service.

    POST /v1/coach/ask   CoachRequest -> CoachResponse (see coach/schemas.py)
    GET  /v1/health      which LLM and models are in use, and whether the chess API answers

Run:  uvicorn coach.app:app --port 8065      (from services/coach)
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .agent import CoachAgent
from .chess_client import ChessApiError, ChessClient
from .config import Settings
from .llm.base import LLMAdapter, LLMError
from .llm.scripted import ScriptedAdapter
from .schemas import CoachRequest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("coach")


def make_llm(settings: Settings) -> LLMAdapter:
    kind = settings.resolved_llm()
    if kind == "openai":
        from .llm.openai_adapter import OpenAIAdapter

        return OpenAIAdapter()
    if kind == "scripted":
        return ScriptedAdapter()
    raise ValueError(f"Unknown COACH_LLM {kind!r}")


def create_app(settings: Settings | None = None, chess: ChessClient | None = None, llm: LLMAdapter | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        client = chess or ChessClient(settings.chess_api_url)
        adapter = llm or make_llm(settings)
        app.state.chess = client
        app.state.agent = CoachAgent(settings, client, adapter)
        app.state.llm_name = adapter.name
        log.info("coach ready: llm=%s fast=%s deep=%s chess=%s", adapter.name, settings.fast, settings.deep, settings.chess_api_url)
        yield
        if chess is None:
            await client.aclose()

    app = FastAPI(title="Think64 coach", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    def error(status: int, code: str, message: str) -> JSONResponse:
        return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})

    @app.post("/v1/coach/ask")
    async def ask(req: CoachRequest) -> Any:
        try:
            response = await app.state.agent.ask(req)
        except ChessApiError as exc:
            if exc.code == "network":
                return error(503, "chess_api_unavailable", "The chess service isn't reachable.")
            if exc.status == 422:
                return error(422, exc.code, str(exc))
            return error(502, "chess_api_error", str(exc))
        except LLMError as exc:
            return error(503, "llm_unavailable", str(exc))
        return response.to_json()

    @app.get("/v1/health")
    async def health() -> Any:
        try:
            chess_health = await app.state.chess.health()
        except Exception:  # health must answer even when the chess API is down
            chess_health = None
        return {
            "status": "ok" if chess_health else "degraded",
            "llm": app.state.llm_name,
            "models": {"fast": settings.fast.model, "deep": settings.deep.model},
            "chess_api": {"url": settings.chess_api_url, "engine": (chess_health or {}).get("engine")},
        }

    return app


app = create_app()
