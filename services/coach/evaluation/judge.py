"""Optional LLM judge for what the deterministic checks can't see: does the answer explain *why*,
does it fit the player's level, is it clear?

The judge never decides chess truth: it is given the verifier's verdicts and told to rely on them.
It costs money, so it only runs with --judge MODEL.
"""
from __future__ import annotations

import json
from typing import Any

from coach.llm.base import LLMAdapter, LLMUsage
from coach.schemas import CoachResponse

JUDGE_SYSTEM = """You grade answers from a chess coach for a player of a given level.
Chess truth is settled already: the "verified claims" list says what the chess engine confirmed (supported),
contradicted (refuted) or could not check (unverifiable). Do not re-judge chess facts yourself; rely on that list.

Score each from 1 (poor) to 5 (excellent):
- explains_why: does it give the reason behind its moves or advice, not just the moves?
- level_fit: is the wording and depth right for the player's level and preferred explanation length?
  (beginner: plain words, moves explained; advanced: concise and concrete)
- clarity: is it easy to follow and does it answer the question that was asked?
Give one short sentence of notes."""

JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "explains_why": {"type": "integer"},
        "level_fit": {"type": "integer"},
        "clarity": {"type": "integer"},
        "notes": {"type": "string"},
    },
    "required": ["explains_why", "level_fit", "clarity", "notes"],
    "additionalProperties": False,
}


async def judge(llm: LLMAdapter, model: str, case: dict[str, Any], fen: str, r: CoachResponse) -> tuple[dict[str, Any], LLMUsage]:
    claims = [{"checked": c.checked or c.text, "verdict": c.result.get("verdict")} for c in r.claims]
    prompt = (
        f"Player level: {case.get('level', 'intermediate')}; preferred explanation length: {case.get('depth', 'normal')}\n"
        f"Position (FEN): {fen}\n"
        f"Question: {case['question']}\n\n"
        f"Coach answer:\n{r.answer}\n\n"
        f"Verified claims: {json.dumps(claims)}"
    )

    async def no_tools(name: str, args: dict[str, Any]) -> dict[str, Any]:
        return {"error": "no tools"}

    res = await llm.run(
        model=model, effort="low", system=JUDGE_SYSTEM, messages=[{"role": "user", "content": prompt}],
        tools=[], execute=no_tools, output_schema=JUDGE_SCHEMA, max_tool_rounds=1,
    )
    scores = {k: max(1, min(5, int(res.output.get(k, 1)))) for k in ("explains_why", "level_fit", "clarity")}
    return {**scores, "notes": str(res.output.get("notes", ""))[:300]}, res.usage
