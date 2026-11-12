"""Turning the LLM's claims into contract claims, checking them with /v1/verify, and describing
exactly what was checked.

- Moves the model writes in SAN are converted to UCI by the chess API (/v1/move), never here.
- A claim may be about the position after a line (`after`); it is then verified in that position.
- A claim whose type cannot test its own sentence (e.g. a legal_line attached to "White has the
  bishop pair") is not counted as verified; it goes back to the model.
- Every result carries `checked`: a plain description of what the verifier actually tested, so a
  green tick in the UI never implies more than that.
"""
from __future__ import annotations

import re
from typing import Any

from .chess_client import ChessApiError, ChessClient
from .schemas import CheckedClaim

SQUARE = re.compile(r"^[a-h][1-8]$")
FILE = re.compile(r"^[a-h]$")

# legal_move / legal_line prove only that moves can be played. Sentences about anything else
# need a claim type that tests it.
OVERREACH = re.compile(
    r"\b(material|equal|up a|down a|pawn up|piece up|exchange|file|semi-open|open|structure|doubled|isolated|"
    r"passed|bishop pair|two bishops|weak|weakness|strong|better|worse|best|advantage|winning|losing|threat|"
    r"attack|attacks|pressure|initiative|control|controls|space|safe|unsafe|mate|check)\b",
    re.I,
)


class Unresolved(Exception):
    """A claim decided without calling /v1/verify (bad fields, illegal SAN, type mismatch)."""

    def __init__(self, verdict: str, reason: str):
        super().__init__(reason)
        self.verdict = verdict
        self.reason = reason


class ClaimChecker:
    def __init__(self, chess: ChessClient, position: dict[str, Any], limits: dict[str, Any]):
        self.chess = chess
        self.position = position
        self.limits = limits
        self._after_cache: dict[tuple[str, ...], tuple[dict[str, Any], list[str]]] = {}

    async def check(self, raw_claims: list[dict[str, Any]]) -> list[CheckedClaim]:
        raw_claims = raw_claims[:20]
        out: list[CheckedClaim | None] = [None] * len(raw_claims)
        groups: dict[tuple[str, ...], list[tuple[int, dict[str, Any]]]] = {}

        for i, raw in enumerate(raw_claims):
            cid = f"c{i}"
            text = raw.get("text", "")
            try:
                pos, line = await self._position_after(raw.get("after"))
                checked = describe(raw, line)
                claim = await self._to_contract(raw, pos, cid)
                groups.setdefault(tuple(line), []).append((i, claim))
                out[i] = CheckedClaim(text=text, checked=checked, result={})
            except Unresolved as u:
                out[i] = CheckedClaim(text=text, checked=describe(raw, raw.get("after") or []), result={"id": cid, "verdict": u.verdict, "reason": u.reason})

        for line, items in groups.items():
            pos, _ = self._after_cache[line]
            results = await self._verify(pos, [c for _, c in items])
            for (i, _), res in zip(items, results):
                out[i] = out[i].model_copy(update={"result": res})
        return [c for c in out if c is not None]

    # ------------------------------------------------------------------ helpers

    async def _position_after(self, after: list[str] | None) -> tuple[dict[str, Any], list[str]]:
        key = tuple(after or [])
        if key in self._after_cache:
            return self._after_cache[key]
        pos = {**self.position, "moves": list(self.position["moves"])}
        sans: list[str] = []
        for san in key[:12]:
            data = await self.chess.move(pos, san, "san")
            if not data["legal"]:
                raise Unresolved("refuted", f"the line is illegal at {san}: {(data.get('reason') or {}).get('message', 'illegal')}")
            sans.append(data["move"]["san"])
            pos = data["next"]
        self._after_cache[key] = (pos, sans)
        return pos, sans

    async def _verify(self, pos: dict[str, Any], claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
        try:
            return (await self.chess.verify(pos, claims, self.limits))["results"]
        except ChessApiError as exc:
            if exc.status != 422:
                raise
        # One claim the service can't take (e.g. an older contract version) must not sink the rest.
        results = []
        for c in claims:
            try:
                results.append((await self.chess.verify(pos, [c], self.limits))["results"][0])
            except ChessApiError as exc:
                if exc.status != 422:
                    raise
                results.append({"id": c["id"], "verdict": "unverifiable", "reason": f"the chess service can't check {c['type']} claims"})
        return results

    async def _uci(self, pos: dict[str, Any], san: str) -> str:
        uci, reason = await self.chess.to_uci(pos, san)
        if not uci:
            raise Unresolved("refuted", reason or f"{san} is not a legal move")
        return uci

    async def _to_contract(self, raw: dict[str, Any], pos: dict[str, Any], cid: str) -> dict[str, Any]:
        t = raw.get("type")

        def need(*fields: str) -> None:
            gone = [f for f in fields if raw.get(f) in (None, "", [])]
            if gone:
                raise Unresolved("unverifiable", f"claim is missing {', '.join(gone)}")

        def square(field: str) -> str:
            need(field)
            if not SQUARE.match(str(raw[field])):
                raise Unresolved("unverifiable", f"{raw[field]!r} is not a square")
            return raw[field]

        if t in ("legal_move", "legal_line") and OVERREACH.search(raw.get("text", "")):
            raise Unresolved(
                "unverifiable",
                f"a {t} claim only checks that moves can be played, not this statement; use a claim type that tests it, or drop it",
            )
        if t in ("legal_move", "best_move"):
            need("move")
            return {"id": cid, "type": t, "move": await self._uci(pos, raw["move"])}
        if t == "better_than":
            need("move", "than")
            return {"id": cid, "type": t, "move": await self._uci(pos, raw["move"]), "than": await self._uci(pos, raw["than"])}
        if t == "legal_line":
            need("moves")
            p, ucis = {**pos, "moves": list(pos["moves"])}, []
            for san in raw["moves"][:20]:
                data = await self.chess.move(p, san, "san")
                if not data["legal"]:
                    raise Unresolved("refuted", f"{san} is not legal at that point in the line")
                ucis.append(data["move"]["uci"])
                p = data["next"]
            return {"id": cid, "type": t, "moves": ucis}
        if t == "mate_in":
            need("mate_in_moves", "winner")
            return {"id": cid, "type": t, "moves": max(1, min(20, int(raw["mate_in_moves"]))), "winner": raw["winner"]}
        if t in ("pinned", "hanging", "isolated_pawn", "passed_pawn"):
            claim = {"id": cid, "type": t, "square": square("square")}
            if t == "pinned" and raw.get("absolute") is not None:
                claim["absolute"] = bool(raw["absolute"])
            return claim
        if t in ("attacks", "defends"):
            return {"id": cid, "type": t, "from": square("from"), "to": square("to")}
        if t == "piece_on":
            need("piece_type", "color")
            return {"id": cid, "type": t, "square": square("square"), "piece_type": raw["piece_type"], "color": raw["color"]}
        if t in ("in_check", "bishop_pair"):
            need("color")
            return {"id": cid, "type": t, "color": raw["color"]}
        if t == "material_balance":
            need("balance_cp")
            return {"id": cid, "type": t, "balance_cp": int(raw["balance_cp"])}
        if t in ("open_file", "doubled_pawns"):
            need("file")
            if not FILE.match(str(raw["file"])):
                raise Unresolved("unverifiable", f"{raw['file']!r} is not a file")
            if t == "open_file":
                return {"id": cid, "type": t, "file": raw["file"], "open_for": raw.get("open_for")}
            need("color")
            return {"id": cid, "type": t, "color": raw["color"], "file": raw["file"]}
        raise Unresolved("unverifiable", f"unknown claim type {t!r}")


def describe(raw: dict[str, Any], line: list[str]) -> str:
    """What the verifier tests for this claim, in plain words (independent of the model's text)."""
    t, g = raw.get("type"), raw.get
    what = {
        "legal_move": lambda: f"{g('move')} can be played",
        "legal_line": lambda: f"the moves {' '.join(g('moves') or [])} can be played",
        "best_move": lambda: f"{g('move')} is within 0.3 pawns of the engine's best move",
        "better_than": lambda: f"{g('move')} scores better than {g('than')} for the side to move",
        "mate_in": lambda: f"{g('winner')} can force mate in {g('mate_in_moves')} or fewer",
        "pinned": lambda: f"the piece on {g('square')} is {'absolutely ' if g('absolute') else ''}pinned",
        "hanging": lambda: f"the piece on {g('square')} is attacked and undefended",
        "attacks": lambda: f"the piece on {g('from')} attacks {g('to')}",
        "defends": lambda: f"the piece on {g('from')} defends {g('to')}",
        "piece_on": lambda: f"a {g('color')} {g('piece_type')} is on {g('square')}",
        "in_check": lambda: f"{g('color')} is in check",
        "material_balance": lambda: _material_words(g("balance_cp")),
        "open_file": lambda: f"the {g('file')}-file is " + ("open" if g("open_for") is None else f"semi-open for {g('open_for')}"),
        "bishop_pair": lambda: f"{g('color')} has the bishop pair",
        "doubled_pawns": lambda: f"{g('color')} has doubled {g('file')}-pawns",
        "isolated_pawn": lambda: f"the pawn on {g('square')} is isolated",
        "passed_pawn": lambda: f"the pawn on {g('square')} is passed",
    }.get(t)
    text = what() if what else f"{t} claim"
    return f"after {' '.join(line)}: {text}" if line else text


def _material_words(cp: Any) -> str:
    if cp is None:
        return "material balance"
    if int(cp) == 0:
        return "material is equal"
    return f"{'White' if int(cp) > 0 else 'Black'} is {abs(int(cp)) / 100:g} pawns up in material"
