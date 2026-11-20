"""Turn chess-API data into text an LLM reads reliably.

Presentation only: nothing here decides what is legal or true. Models misread raw FEN, so the
coach also gives an explicit piece list, facts as sentences and scores spelled out per side.
"""
from __future__ import annotations

from typing import Any

ORDER = "KQRBNP"
NAMES = {"K": "king", "Q": "queen", "R": "rook", "B": "bishop", "N": "knight", "P": "pawn"}


def pieces_from_fen(fen: str) -> dict[str, list[str]]:
    """{"white": ["Ke1", "Qd1", ..., "Pe4"], "black": [...]}, kings first, pawns last."""
    out: dict[str, list[str]] = {"white": [], "black": []}
    rows = fen.split()[0].split("/")
    for r, row in enumerate(rows):
        f = 0
        for ch in row:
            if ch.isdigit():
                f += int(ch)
                continue
            square = "abcdefgh"[f] + str(8 - r)
            out["white" if ch.isupper() else "black"].append(ch.upper() + square)
            f += 1
    for side in out:
        out[side].sort(key=lambda p: (ORDER.index(p[0]), p[1:]))
    return out


def piece_list_text(fen: str) -> str:
    p = pieces_from_fen(fen)
    fmt = lambda xs: ", ".join(x[1:] if x[0] == "P" else x for x in xs) or "-"  # pawns as bare squares
    return f"White: {fmt(p['white'])}\nBlack: {fmt(p['black'])}"


def piece(p: dict[str, Any]) -> str:
    return f"{p['color']} {p['type']} on {p['square']}"


def describe_fact(f: dict[str, Any]) -> str | None:
    k = f.get("kind")
    if k == "check":
        return f"CHECK: {piece(f['checker'])} gives check to the {f['king']['color']} king on {f['king']['square']}"
    if k == "pin":
        kind = "absolute pin (moving it off the line is illegal)" if f["absolute"] else "relative pin (moving it loses material on the line)"
        return f"PIN: {piece(f['pinned'])} is pinned to the {f['shielded']['type']} on {f['shielded']['square']} by the {f['pinner']['type']} on {f['pinner']['square']} - {kind}"
    if k == "xray":
        return f"X-RAY: {piece(f['attacker'])} would hit the {f['target']['color']} {f['target']['type']} on {f['target']['square']} if its {f['blocker']['type']} on {f['blocker']['square']} moved"
    if k == "hanging":
        att = ", ".join(f"{a['type']} {a['square']}" for a in f["attackers"])
        return f"HANGING: {piece(f['piece'])} is attacked (by {att}) and not defended"
    if k == "open_file":
        return f"OPEN FILE: the {f['file']}-file"
    if k == "semi_open_file":
        return f"SEMI-OPEN FILE: the {f['file']}-file for {f['open_for']}"
    return None  # contract: ignore unknown fact kinds


def fmt_score(score: dict[str, Any]) -> str:
    """Contract scores are White's point of view."""
    v = score["value"]
    if score["type"] == "mate":
        return f"mate in {abs(v)} for {'White' if v > 0 else 'Black'}" if v else "checkmate on the board"
    pawns = v / 100
    if abs(pawns) < 0.25:
        lean = "roughly equal"
    else:
        lean = f"{'White' if pawns > 0 else 'Black'} better by about {abs(pawns):.1f} pawns"
    return f"{pawns:+.2f} ({lean})"


def side_to_move(fen: str) -> str:
    return "black" if fen.split()[1] == "b" else "white"


def status_text(status: dict[str, Any]) -> str:
    state = status["state"]
    if state == "checkmate":
        return f"checkmate - {status['winner']} has won"
    if state != "ongoing":
        return f"game over: {state.replace('_', ' ')}"
    parts = ["in check" if status["in_check"] else "not in check"]
    if status["claimable_draws"]:
        parts.append("draw claimable: " + ", ".join(status["claimable_draws"]))
    return "ongoing, side to move is " + "; ".join(parts)


def position_brief(pos: dict[str, Any], last_move_san: str | None) -> str:
    """The ground-truth summary put in front of every question."""
    p = pos["position"]
    stm = p["side_to_move"]
    lines = [
        f"FEN: {p['fen']}",
        f"Side to move: {stm} (move {p['fullmove_number']})",
        f"Last move: {last_move_san} by {'black' if stm == 'white' else 'white'}" if last_move_san else "Last move: none (start of the game or a set-up position)",
        "Pieces:",
        piece_list_text(p["fen"]),
        f"Status: {status_text(pos['status'])}",
        f"Material balance: {pos['material']['balance_cp'] / 100:+.0f} pawns (White minus Black)",
        f"Legal moves ({len(pos['legal_moves'])}): " + ", ".join(m["san"] for m in pos["legal_moves"][:60]),
    ]
    facts = [d for d in (describe_fact(f) for f in pos["facts"]) if d]
    lines.append("Facts from the rules engine:" if facts else "Facts from the rules engine: none (no checks, pins, x-rays, hanging pieces or open files)")
    lines += [f"- {d}" for d in facts]
    return "\n".join(lines)
