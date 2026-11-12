"""Test fixtures: the real analysis-schema mock in a background thread, and a programmable fake LLM."""
from __future__ import annotations

import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "packages" / "analysis-schema" / "mock"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server as mock_server  # noqa: E402  (packages/analysis-schema/mock/server.py)

from coach.llm.base import LLMError, LLMResult, LLMUsage  # noqa: E402

# 1. d4 Nf6 2. c4 e6 3. Nc3 Bb4 - the knight on c3 is absolutely pinned (contract examples 06 and 19).
NIMZO = {"moves": ["d2d4", "g8f6", "c2c4", "e7e6", "b1c3", "f8b4"]}


@pytest.fixture(scope="session")
def chess_api_url():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), mock_server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def claim(text: str, type_: str, **fields: Any) -> dict[str, Any]:
    base = {k: None for k in ("move", "than", "moves", "square", "from", "to", "piece_type", "color", "winner", "mate_in_moves", "absolute")}
    return {**base, "text": text, "type": type_, **fields}


def answer(text: str, claims: list[dict[str, Any]] | None = None, arrows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"answer": text, "claims": claims or [], "arrows": arrows or [], "highlights": []}


class QueueLLM:
    """Returns pre-programmed outputs in order; optionally calls tools first. Records every call."""

    name = "queue"

    def __init__(self, outputs: list[dict[str, Any] | Exception], tool_calls: list[tuple[str, dict[str, Any]]] | None = None):
        self.outputs = list(outputs)
        self.tool_calls = tool_calls or []
        self.calls: list[dict[str, Any]] = []
        self.tool_results: list[dict[str, Any]] = []

    async def run(self, *, model, effort, system, messages, tools, execute, output_schema, max_tool_rounds, state=None):
        self.calls.append({"model": model, "effort": effort, "messages": messages, "system": system, "state": state})
        if state is None:
            for name, args in self.tool_calls:
                self.tool_results.append(await execute(name, args))
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return LLMResult(output=out, model=model, usage=LLMUsage(input_tokens=1000, cached_tokens=200, output_tokens=300, calls=1), state=["s"])


__all__ = ["NIMZO", "QueueLLM", "answer", "claim", "LLMError"]
