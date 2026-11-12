"""A deterministic stand-in for the LLM, used when no API key is configured and in tests.

It calls the same chess tools a real model would and assembles a template answer from them, so
the whole pipeline (tools -> claims -> /v1/verify -> annotations) runs end to end for free.
It is clearly labelled in its answer; it does not try to reason.
"""
from __future__ import annotations

import re
from typing import Any

from ..prompts import CLAIM_VALUE_FIELDS
from .base import LLMResult, LLMUsage, ToolExecutor

LAST_MOVE_WORDS = re.compile(r"\b(last|previous|mistake|blunder|wrong|bad|why did|was it)\b", re.I)
PIN = re.compile(r"^PIN: (white|black) \w+ on ([a-h][1-8]) is pinned.*?- (absolute|relative)")
HANGING = re.compile(r"^HANGING: (white|black) \w+ on ([a-h][1-8])")
CHECK = re.compile(r"^CHECK: .* gives check to the (white|black) king")
STATUS = re.compile(r"^Status: (.*)$", re.M)


def _blank_claim(text: str, type_: str, **fields: Any) -> dict[str, Any]:
    return {**{k: None for k in CLAIM_VALUE_FIELDS}, "text": text, "type": type_, **fields}


class ScriptedAdapter:
    name = "scripted"

    async def run(
        self,
        *,
        model: str,
        effort: str,
        system: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        execute: ToolExecutor,
        output_schema: dict[str, Any],
        max_tool_rounds: int,
        state: Any = None,
    ) -> LLMResult:
        usage = LLMUsage(calls=1)
        if state is not None:  # revision: drop the claims the verifier objected to
            feedback = messages[-1]["content"]
            prev = state["output"]
            kept = [c for c in prev["claims"] if c["text"] not in feedback]
            out = {**prev, "claims": kept}
            return LLMResult(output=out, model="scripted", usage=usage, state={"output": out})

        context = messages[-1]["content"]
        question = context.rsplit("Question:", 1)[-1]
        fact_lines = [ln[2:] for ln in context.splitlines() if ln.startswith("- ")]
        sentences: list[str] = []
        claims: list[dict[str, Any]] = []
        arrows: list[dict[str, Any]] = []
        highlights: list[dict[str, Any]] = []

        analysis = await execute("analyze_position", {"multipv": 3})
        status = STATUS.search(context)
        if analysis.get("game_over"):
            sentences.append(f"The game is over: {status.group(1) if status else 'no legal moves'}.")
        elif analysis.get("engine_note"):
            sentences.append("Real engine analysis isn't connected yet (the chess API is the mock server), so here is only what the rules engine confirms.")
        elif analysis.get("lines"):
            best = analysis["lines"][0]
            sentences.append(f"Stockfish's top choice is {best['move']} ({best['score']}); the main line runs {best['line']}.")
            claims.append(_blank_claim(f"Stockfish's top choice is {best['move']}", "best_move", move=best["move"]))
            arrows.append({"move": best["move"], "from": None, "to": None, "color": "green"})
            if len(analysis["lines"]) > 1:
                alt = analysis["lines"][1]
                sentences.append(f"The next best is {alt['move']} ({alt['score']}).")
                arrows.append({"move": alt["move"], "from": None, "to": None, "color": "yellow"})

        if LAST_MOVE_WORDS.search(question):
            review = await execute("review_last_move", {})
            if review.get("available") and not analysis.get("engine_note"):
                sentences.append(
                    f"The last move, {review['played']}, was {review['verdict']}: it gave up about "
                    f"{review['loss_cp'] / 100:.1f} pawns compared with {review['engine_best']}."
                )

        for line in fact_lines[:3]:
            body = line.split(": ", 1)[-1]
            sentence = body[:1].upper() + body[1:] + "."
            if m := PIN.match(line):
                sentences.append(sentence)
                claims.append(_blank_claim(line, "pinned", square=m.group(2), absolute=m.group(3) == "absolute"))
                highlights.append({"square": m.group(2), "color": "yellow"})
            elif m := HANGING.match(line):
                sentences.append(sentence)
                claims.append(_blank_claim(line, "hanging", square=m.group(2)))
                highlights.append({"square": m.group(2), "color": "red"})
            elif m := CHECK.match(line):
                sentences.append(sentence)
                claims.append(_blank_claim(line, "in_check", color=m.group(1)))
            elif line.split(":")[0].isupper():
                sentences.append(sentence)
        if not fact_lines and not analysis.get("game_over"):
            sentences.append("There are no checks, pins, hanging pieces or open files right now.")

        sentences.append("(Template answer: no language model is configured, so this only restates the chess service's data.)")
        out = {"answer": " ".join(sentences), "claims": claims, "arrows": arrows, "highlights": highlights}
        return LLMResult(output=out, model="scripted", usage=usage, state={"output": out})
