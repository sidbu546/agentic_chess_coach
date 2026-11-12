"""Async client for the chess truth API (packages/analysis-schema/openapi.yaml).

The coach never decides chess truth itself: legality, SAN, engine lines, facts and claim
verification all come from here. Switching from the mock to Person 1's service is CHESS_API_URL.
"""
from __future__ import annotations

from typing import Any

import httpx


class ChessApiError(Exception):
    def __init__(self, code: str, message: str, status: int = 0):
        super().__init__(message)
        self.code = code
        self.status = status


class ChessClient:
    def __init__(self, base_url: str, timeout: float = 60.0, transport: httpx.AsyncBaseTransport | None = None):
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            res = await self._http.post(path, json=body)
        except httpx.HTTPError as exc:
            raise ChessApiError("network", f"Chess API unreachable: {exc}") from exc
        data = res.json() if res.content else {}
        if res.status_code >= 400:
            err = data.get("error", {}) if isinstance(data, dict) else {}
            raise ChessApiError(err.get("code", "http"), err.get("message", f"HTTP {res.status_code}"), res.status_code)
        return data

    async def health(self) -> dict[str, Any]:
        res = await self._http.get("/v1/health")
        return res.json()

    async def position(self, position: dict[str, Any], pieces: bool = False) -> dict[str, Any]:
        return await self._post(
            "/v1/position",
            {"position": position, "include": {"legal_moves": True, "facts": True, "pieces": pieces}},
        )

    async def move(self, position: dict[str, Any], move: str, notation: str = "uci") -> dict[str, Any]:
        return await self._post("/v1/move", {"position": position, "move": move, "notation": notation})

    async def analyze(self, position: dict[str, Any], limits: dict[str, Any]) -> dict[str, Any]:
        return await self._post("/v1/analyze", {"position": position, "limits": limits})

    async def compare(self, position: dict[str, Any], moves: list[str], limits: dict[str, Any]) -> dict[str, Any]:
        return await self._post("/v1/compare", {"position": position, "moves": moves, "limits": limits})

    async def verify(self, position: dict[str, Any], claims: list[dict[str, Any]], limits: dict[str, Any]) -> dict[str, Any]:
        return await self._post("/v1/verify", {"position": position, "claims": claims, "limits": limits})

    async def to_uci(self, position: dict[str, Any], san: str) -> tuple[str | None, str | None]:
        """SAN (as the LLM writes it) -> UCI, decided by the chess API. Returns (uci, None) or (None, reason)."""
        san = san.strip()
        notation = "uci" if _looks_uci(san) else "san"
        data = await self.move(position, san, notation)
        if data.get("legal") and data.get("move"):
            return data["move"]["uci"], None
        reason = (data.get("reason") or {}).get("message") or f"{san} is not a legal move here"
        return None, reason


def _looks_uci(s: str) -> bool:
    return len(s) in (4, 5) and s[0] in "abcdefgh" and s[1] in "12345678" and s[2] in "abcdefgh" and s[3] in "12345678"
