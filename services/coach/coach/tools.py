"""The chess tools the coach's LLM can call.

Definitions are provider-neutral JSON Schema (strict: every property required, no extras), so the
same set works with any LLM adapter. Every tool is a thin wrapper over the chess truth API; results
are compact JSON with SAN moves and spelled-out scores.
"""
from __future__ import annotations

import json
from typing import Any

from .board_text import describe_fact, fmt_score, position_brief
from .chess_client import ChessApiError, ChessClient

SAN_LIST = {"type": "array", "items": {"type": "string"}}

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "analyze_position",
        "description": (
            "Run Stockfish on the CURRENT position. Returns the engine's best candidate moves (SAN), each with a "
            "score from White's point of view and its principal variation. Use it for 'best move', 'who is better' "
            "and 'what is the plan' questions."
        ),
        "parameters": {
            "type": "object",
            "properties": {"multipv": {"type": "integer", "description": "Number of candidate lines, 1-5."}},
            "required": ["multipv"],
            "additionalProperties": False,
        },
    },
    {
        "name": "compare_moves",
        "description": (
            "Compare specific moves in the CURRENT position against the engine's best move. Returns, per move, how "
            "many centipawns it loses and structured differences (material won or lost, pins or checks created or "
            "removed, mates). Use it for 'why is X better than Y' or 'what about X?'."
        ),
        "parameters": {
            "type": "object",
            "properties": {"moves": {**SAN_LIST, "description": "1-5 moves in SAN, e.g. [\"Nf3\", \"Bxf7+\"]."}},
            "required": ["moves"],
            "additionalProperties": False,
        },
    },
    {
        "name": "explore_line",
        "description": (
            "Play a sequence of moves (SAN, alternating sides, starting with the side to move) from the CURRENT "
            "position and describe the resulting position: legality, check/mate/draw, rules-engine facts and the "
            "engine's view. Use it for 'what if' questions and to check a plan before you describe it."
        ),
        "parameters": {
            "type": "object",
            "properties": {"moves": {**SAN_LIST, "description": "1-10 moves in SAN."}},
            "required": ["moves"],
            "additionalProperties": False,
        },
    },
    {
        "name": "review_last_move",
        "description": (
            "Judge the move that led to the CURRENT position: centipawn loss versus the engine's best move in the "
            "previous position, the better alternative and what changed. Use it for 'was that a mistake?' or 'why "
            "was my last move bad?'."
        ),
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
]


def classify_loss(loss_cp: int) -> str:
    if loss_cp <= 20:
        return "best or near-best"
    if loss_cp <= 50:
        return "good"
    if loss_cp <= 100:
        return "inaccuracy"
    if loss_cp <= 300:
        return "mistake"
    return "blunder"


def numbered(sans: list[str], fullmove: int, white_to_move: bool) -> str:
    out, n, white = [], fullmove, white_to_move
    for i, s in enumerate(sans):
        if white:
            out.append(f"{n}. {s}")
        else:
            out.append(f"{n}... {s}" if i == 0 else s)
            n += 1
        white = not white
    return " ".join(out)


def describe_difference(d: dict[str, Any]) -> str:
    k = d.get("kind")
    if k == "material":
        return f"material balance goes from {d['balance_cp_before'] / 100:+.0f} to {d['balance_cp_after'] / 100:+.0f} pawns (White minus Black) after {d['after_plies']} plies"
    if k == "mate":
        return f"forced mate in {d['in_moves']} for {d['winner']}"
    if k in ("fact_created", "fact_removed"):
        text = describe_fact(d["fact"]) or d["fact"].get("kind", "fact")
        return f"after {d['at_ply']} plies {'appears' if k == 'fact_created' else 'disappears'}: {text}"
    return json.dumps(d)


class ChessTools:
    """Executes tool calls for one coach request, against one position."""

    def __init__(self, client: ChessClient, position: dict[str, Any], fen: str, limits: dict[str, Any]):
        self.client = client
        self.position = position
        self.fen = fen
        self.limits = limits
        self.used: list[str] = []  # chess API endpoints called, shown in the UI
        self.engine_is_mock = False

    def _note(self, endpoint: str) -> None:
        if endpoint not in self.used:
            self.used.append(endpoint)

    @property
    def _fullmove(self) -> int:
        return int(self.fen.split()[5])

    @property
    def _white_to_move(self) -> bool:
        return self.fen.split()[1] == "w"

    async def run(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return {"error": f"unknown tool {name}"}
        try:
            return await handler(**args)
        except ChessApiError as exc:
            return {"error": f"chess API: {exc}"}
        except TypeError as exc:  # wrong arguments from the model
            return {"error": f"bad arguments for {name}: {exc}"}

    # ---------------------------------------------------------------- tools

    async def _tool_analyze_position(self, multipv: int = 3) -> dict[str, Any]:
        multipv = max(1, min(5, int(multipv)))
        self._note("analyze")
        data = await self.client.analyze(self.position, {**self.limits, "multipv": multipv})
        a = data["analysis"]
        self.engine_is_mock |= a["engine"]["name"] == "mock"
        return {
            "engine": a["engine"]["name"],
            "engine_note": _mock_note(a["engine"]["name"]),
            "depth": a["depth"],
            "lines": [
                {
                    "rank": c["rank"],
                    "move": c["move"]["san"],
                    "score": fmt_score(c["score"]),
                    "line": numbered([m["san"] for m in c["pv"][:10]], self._fullmove, self._white_to_move),
                }
                for c in a["candidates"]
            ],
            "game_over": not a["candidates"],
        }

    async def _tool_compare_moves(self, moves: list[str]) -> dict[str, Any]:
        moves = list(moves)[:5]
        self._note("move")
        ucis, illegal = [], []
        for san in moves:
            uci, reason = await self.client.to_uci(self.position, san)
            (ucis.append(uci) if uci else illegal.append({"move": san, "reason": reason}))
        result: dict[str, Any] = {"illegal": illegal}
        if not ucis:
            return result
        self._note("compare")
        data = await self.client.compare(self.position, ucis, self.limits)
        best = data["best"]
        result["best"] = {
            "move": best["move"]["san"],
            "score": fmt_score(best["score"]),
            "line": numbered([m["san"] for m in best["pv"][:10]], self._fullmove, self._white_to_move),
        }
        result["lines"] = [
            {
                "move": ln["move"]["san"],
                "score": fmt_score(ln["score"]),
                "loss_cp": ln["loss_cp"],
                "verdict": "best" if ln["is_best"] else classify_loss(ln["loss_cp"]),
                "line": numbered([m["san"] for m in ln["pv"][:10]], self._fullmove, self._white_to_move),
                "differences": [describe_difference(d) for d in ln["differences"]],
            }
            for ln in data["lines"]
        ]
        return result

    async def _tool_explore_line(self, moves: list[str]) -> dict[str, Any]:
        self._note("move")
        pos = {**self.position, "moves": list(self.position["moves"])}
        played: list[str] = []
        for san in list(moves)[:10]:
            data = await self.client.move(pos, san, "san")
            if not data["legal"]:
                return {
                    "legal": False,
                    "played": numbered(played, self._fullmove, self._white_to_move),
                    "illegal_move": san,
                    "reason": (data.get("reason") or {}).get("message", "illegal"),
                }
            played.append(data["move"]["san"])
            pos = data["next"]
        self._note("position")
        after = await self.client.position(pos)
        result: dict[str, Any] = {
            "legal": True,
            "line": numbered(played, self._fullmove, self._white_to_move),
            "resulting_position": position_brief(after, played[-1] if played else None),
        }
        if not after["status"]["is_game_over"]:
            self._note("analyze")
            limits = {**self.limits, "multipv": 2, "depth": min(self.limits.get("depth", 16), 14)}
            a = (await self.client.analyze(pos, limits))["analysis"]
            self.engine_is_mock |= a["engine"]["name"] == "mock"
            stm_white = after["position"]["side_to_move"] == "white"
            result["engine_after"] = {
                "engine_note": _mock_note(a["engine"]["name"]),
                "lines": [
                    {"move": c["move"]["san"], "score": fmt_score(c["score"]),
                     "line": numbered([m["san"] for m in c["pv"][:8]], after["position"]["fullmove_number"], stm_white)}
                    for c in a["candidates"]
                ],
            }
        return result

    async def _tool_review_last_move(self) -> dict[str, Any]:
        moves = self.position["moves"]
        if not moves:
            return {"available": False, "reason": "No move has been played from the start position."}
        parent = {**self.position, "moves": moves[:-1]}
        self._note("compare")
        data = await self.client.compare(parent, [moves[-1]], self.limits)
        line, best = data["lines"][0], data["best"]
        parent_fen = data["position"]["fen"]
        full, white = int(parent_fen.split()[5]), parent_fen.split()[1] == "w"
        return {
            "available": True,
            "played": line["move"]["san"],
            "played_by": "white" if white else "black",
            "loss_cp": line["loss_cp"],
            "verdict": "best" if line["is_best"] else classify_loss(line["loss_cp"]),
            "score_after_played": fmt_score(line["score"]),
            "engine_best": best["move"]["san"],
            "engine_best_score": fmt_score(best["score"]),
            "engine_best_line": numbered([m["san"] for m in best["pv"][:10]], full, white),
            "played_line": numbered([m["san"] for m in line["pv"][:10]], full, white),
            "differences": [describe_difference(d) for d in line["differences"]],
        }


def _mock_note(engine_name: str) -> str | None:
    if engine_name == "mock":
        return "MOCK ENGINE: these scores and moves are placeholders, not real analysis. Do not present them as engine evaluations or best moves."
    return None
