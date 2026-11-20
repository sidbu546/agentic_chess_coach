"""The game on the board, replayed through the chess API (SAN for every move).

The contract has no endpoint that returns a game's moves in SAN, so the coach plays them one by one
with /v1/move. Results are cached by move prefix, so the next question in the same game only
converts the new moves.
"""
from __future__ import annotations

from typing import Any

from .chess_client import ChessClient

MAX_CACHE = 20_000


class GameReplay:
    def __init__(self, chess: ChessClient):
        self.chess = chess
        self._san: dict[str, str] = {}

    async def sans(self, position: dict[str, Any]) -> list[str]:
        start, moves = position["start_fen"], position["moves"]
        if len(self._san) > MAX_CACHE:
            self._san.clear()
        out: list[str] = []
        for i, uci in enumerate(moves):
            key = f"{start}|{' '.join(moves[: i + 1])}"
            if key not in self._san:
                data = await self.chess.move({"start_fen": start, "moves": moves[:i]}, uci, "uci")
                self._san[key] = data["move"]["san"]
            out.append(self._san[key])
        return out


def numbered_game(sans: list[str], start_fen: str, last: int = 60) -> str:
    """'1. e4 e5 2. Nf3 ...' for the last `last` plies (earlier ones elided)."""
    full, white = int(start_fen.split()[5]), start_fen.split()[1] == "w"
    parts: list[str] = []
    for i, san in enumerate(sans):
        if i >= len(sans) - last:
            if white:
                parts.append(f"{full}. {san}")
            else:
                parts.append(f"{full}... {san}" if not parts else san)
        if not white:
            full += 1
        white = not white
    return ("... " if len(sans) > last else "") + " ".join(parts)
