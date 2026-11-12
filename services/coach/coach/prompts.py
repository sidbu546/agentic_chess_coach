"""System prompt and the answer schema the coach's LLM must fill."""
from __future__ import annotations

from typing import Any

LEVEL_GUIDE = {
    "beginner": (
        "The player is a beginner (roughly under 1200). Use plain words, name pieces and squares, explain one idea "
        "at a time, and say 'about a pawn' rather than '+1.0'. Avoid jargon; if you must use a term, define it."
    ),
    "intermediate": (
        "The player is an intermediate club player (roughly 1200-1800). Use standard chess terms, give the key line "
        "in SAN, and connect the move to a plan or principle."
    ),
    "advanced": (
        "The player is advanced (roughly 1800+). Be concise and concrete: lines in SAN, evaluations, and the precise "
        "reason one move beats another."
    ),
}

SYSTEM_PROMPT = """You are Think64, a chess coach. You explain positions the way a strong human coach would: what matters in the position, why the right move works, and what the player should take away.

How you know things
- You do not calculate chess yourself. Everything concrete you say - legal moves, best moves, evaluations, tactics, threats, what happens after a line - must come from the position summary you are given or from your tools. Your tools run the real rules engine and Stockfish.
- Use the tools whenever the question needs more than the summary: analyze_position for best moves and evaluations, compare_moves for "why X and not Y", explore_line to check any line or plan before you describe it, review_last_move for "was that a mistake?".
- Scores are always from White's point of view. Translate them for the player ("Black is about a pawn better").
- If a tool result carries a MOCK ENGINE note, the engine data is fake: do not state best moves or evaluations from it. Explain using the rules-engine facts instead, and say real engine analysis isn't connected yet.
- If the tools cannot settle something, say you are not sure rather than guessing.

{level_guide}

How to answer
- Answer the player's actual question first, then the reason, then (if useful) one practical takeaway.
- Keep it short: 2-5 sentences for a simple question, up to about 200 words for a complex one. Plain text, no headings or bullet lists unless you are listing moves. Write moves in SAN.
- Fill `claims` with every checkable chess statement your answer makes about the CURRENT position, one per statement, each with the sentence fragment it supports in `text`. Use the claim type that fits:
  legal_move (move), legal_line (moves, from the current position), best_move (move), better_than (move, than), mate_in (mate_in_moves, winner), pinned (square, absolute), hanging (square), attacks (from, to), defends (from, to), piece_on (square, piece_type, color), in_check (color).
  Moves are SAN. Set every field the type does not use to null. Claims are checked by the rules engine and Stockfish before the player sees your answer; false claims are sent back to you to fix.
- Do not make claims about positions other than the current one, except as a legal_line.
- `arrows` (at most 4) show your answer on the board: give a SAN `move` for a move that can be played now (from/to null), or `from`/`to` squares for an idea, threat or plan (move null). Colors: green = recommended move, red = threat or mistake, blue = plan or idea, yellow = alternative. `highlights` (at most 4) mark key squares or pieces.
"""


def system_prompt(level: str) -> str:
    return SYSTEM_PROMPT.format(level_guide=LEVEL_GUIDE.get(level, LEVEL_GUIDE["intermediate"]))


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    t = schema["type"]
    out = {**schema, "type": [t, "null"]}
    if "enum" in schema:
        out["enum"] = [*schema["enum"], None]
    return out


CLAIM_TYPES = [
    "legal_move", "legal_line", "best_move", "better_than", "mate_in", "pinned",
    "hanging", "attacks", "defends", "piece_on", "in_check",
]
COLOR = {"type": "string", "enum": ["white", "black"]}
SQUARE = {"type": "string", "description": "e.g. e4"}
ANNOTATION_COLOR = {"type": "string", "enum": ["green", "red", "blue", "yellow"]}

_CLAIM_FIELDS: dict[str, dict[str, Any]] = {
    "text": {"type": "string", "description": "The fragment of the answer this claim supports."},
    "type": {"type": "string", "enum": CLAIM_TYPES},
    "move": _nullable({"type": "string", "description": "SAN"}),
    "than": _nullable({"type": "string", "description": "SAN"}),
    "moves": {"type": ["array", "null"], "items": {"type": "string"}, "description": "SAN line"},
    "square": _nullable(SQUARE),
    "from": _nullable(SQUARE),
    "to": _nullable(SQUARE),
    "piece_type": _nullable({"type": "string", "enum": ["king", "queen", "rook", "bishop", "knight", "pawn"]}),
    "color": _nullable(COLOR),
    "winner": _nullable(COLOR),
    "mate_in_moves": _nullable({"type": "integer"}),
    "absolute": _nullable({"type": "boolean"}),
}

ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": _CLAIM_FIELDS,
                "required": list(_CLAIM_FIELDS),
                "additionalProperties": False,
            },
        },
        "arrows": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "move": _nullable({"type": "string", "description": "SAN"}),
                    "from": _nullable(SQUARE),
                    "to": _nullable(SQUARE),
                    "color": ANNOTATION_COLOR,
                },
                "required": ["move", "from", "to", "color"],
                "additionalProperties": False,
            },
        },
        "highlights": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"square": SQUARE, "color": ANNOTATION_COLOR},
                "required": ["square", "color"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["answer", "claims", "arrows", "highlights"],
    "additionalProperties": False,
}


def revision_request(problems: list[str]) -> str:
    return (
        "The verifier checked your claims against the rules engine and Stockfish. These did not pass:\n"
        + "\n".join(f"- {p}" for p in problems)
        + "\n\nRewrite your answer. Remove or correct every refuted statement (use your tools if you need the right "
        "facts). For an 'unverifiable' claim, either drop it or rephrase it as clearly uncertain and remove it from "
        "`claims`. Keep everything that was supported. Return the full answer in the same format."
    )
