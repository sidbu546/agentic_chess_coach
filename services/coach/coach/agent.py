"""The coach agent: question -> chess tools -> LLM -> /v1/verify -> grounded answer.

1. Ask the chess API for the position (status, material, facts) and build the context.
2. Route the question to the fast or deep tier.
3. Let the LLM call chess tools and return an answer with structured claims.
4. Convert the claims to the contract's Claim format (SAN -> UCI by the chess API) and send them
   to /v1/verify. Refuted or unverifiable claims go back to the LLM for one revision.
5. If a refuted claim survives, the player gets a safe answer built only from verified data.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

from .board_text import describe_fact, position_brief
from .chess_client import ChessClient
from .config import Settings, TierConfig
from .llm.base import LLMAdapter, LLMResult, LLMUsage
from .pricing import cost_usd
from .prompts import ANSWER_SCHEMA, revision_request, system_prompt
from .schemas import BoardAnnotations, BoardArrow, BoardHighlight, CheckedClaim, CoachRequest, CoachResponse, Usage
from .tools import TOOL_DEFINITIONS, ChessTools
from .verification import ClaimChecker

log = logging.getLogger("coach.agent")

# Engine limits per player level (contract decision 7: the caller picks depth and MultiPV).
LEVEL_LIMITS = {
    "beginner": {"depth": 12, "multipv": 2},
    "intermediate": {"depth": 16, "multipv": 3},
    "advanced": {"depth": 20, "multipv": 3},
}
DEFAULT_LEVEL = "intermediate"  # until player memory supplies the real level

DEEP_WORDS = re.compile(
    r"\b(why|how|plan|plans|strategy|strategic|explain|compare|versus|vs|better|worse|instead|idea|ideas|"
    r"structure|long[- ]term|evaluate|evaluation|what if|review|understand|difference|sacrifice|endgame|"
    r"middlegame|imbalance|weakness|weaknesses)\b",
    re.I,
)
SAN_TOKEN = re.compile(r"\b(?:[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8]|[a-h][1-8](?:=[QRBN])?|O-O(?:-O)?)[+#]?(?![\w])")
SQUARE = re.compile(r"^[a-h][1-8]$")


def route(req: CoachRequest) -> str:
    """'deep' for questions that need real reasoning, 'fast' for quick lookups."""
    if req.depth != "auto":
        return req.depth
    q = req.question
    if len(q) > 180 or DEEP_WORDS.search(q) or len(SAN_TOKEN.findall(q)) >= 2:
        return "deep"
    return "fast"


class CoachAgent:
    def __init__(self, settings: Settings, chess: ChessClient, llm: LLMAdapter):
        self.settings = settings
        self.chess = chess
        self.llm = llm

    async def ask(self, req: CoachRequest) -> CoachResponse:
        started = time.monotonic()
        position = req.position.model_dump()
        pos = await self.chess.position(position)  # also validates the position (422 on bad FEN/history)
        fen = pos["position"]["fen"]

        tier = route(req)
        tier_cfg: TierConfig = self.settings.deep if tier == "deep" else self.settings.fast
        level = DEFAULT_LEVEL
        limits = {"depth": LEVEL_LIMITS[level]["depth"]}
        tools = ChessTools(self.chess, position, fen, limits)
        tools.used.append("position")

        messages = [{"role": "user" if t.role == "user" else "assistant", "content": t.content} for t in req.history[-6:]]
        messages.append({"role": "user", "content": self._context(pos, req)})
        common = dict(
            model=tier_cfg.model,
            effort=tier_cfg.effort,
            system=system_prompt(level),
            tools=TOOL_DEFINITIONS,
            execute=tools.run,
            output_schema=ANSWER_SCHEMA,
            max_tool_rounds=self.settings.max_tool_rounds,
        )

        usage = LLMUsage()
        result: LLMResult = await self.llm.run(messages=messages, **common)
        usage.add(result.usage)
        checked = await self._verify(result.output.get("claims", []), position, limits, tools)

        for _ in range(self.settings.max_revisions):
            problems = [
                f"\"{c.text}\" (checked: {c.checked}): {c.result['verdict']} - {c.result['reason']}"
                for c in checked
                if c.result["verdict"] != "supported"
            ]
            if not problems:
                break
            result = await self.llm.run(messages=[{"role": "user", "content": revision_request(problems)}], state=result.state, **common)
            usage.add(result.usage)
            checked = await self._verify(result.output.get("claims", []), position, limits, tools)

        refuted = [c for c in checked if c.result["verdict"] == "refuted"]
        model_name = result.model
        if refuted:
            log.warning("falling back: %d refuted claim(s) after revision: %s", len(refuted), [c.text for c in refuted])
            response = self._fallback(pos, tools, model_name)
        else:
            response = CoachResponse(
                answer=result.output.get("answer", "").strip(),
                annotations=await self._annotations(result.output, position),
                claims=checked,
                tools_used=tools.used,
                model=model_name,
                tier=tier,
            )
        response.usage = Usage(
            input_tokens=usage.input_tokens,
            cached_tokens=usage.cached_tokens,
            output_tokens=usage.output_tokens,
            reasoning_tokens=usage.reasoning_tokens,
            llm_calls=usage.calls,
            cost_usd=cost_usd(tier_cfg.model, usage),
        )
        verdicts = [c.result["verdict"] for c in response.claims]
        log.info(
            "answer tier=%s model=%s calls=%d in=%d cached=%d out=%d reasoning=%d cost=$%.4f claims=%s tools=%s %.1fs",
            response.tier, response.model, usage.calls, usage.input_tokens, usage.cached_tokens, usage.output_tokens,
            usage.reasoning_tokens, response.usage.cost_usd, verdicts, tools.used, time.monotonic() - started,
        )
        return response

    # ---------------------------------------------------------------- context

    @staticmethod
    def _context(pos: dict[str, Any], req: CoachRequest) -> str:
        last = req.last_move.san if req.last_move else None
        return (
            "Current position (ground truth from the rules engine):\n"
            f"{position_brief(pos, last)}\n"
            f"Moves played from the start position: {len(req.position.moves)}\n\n"
            f"Question: {req.question.strip()}"
        )

    # ---------------------------------------------------------------- verification

    async def _verify(
        self, raw_claims: list[dict[str, Any]], position: dict[str, Any], limits: dict[str, Any], tools: ChessTools
    ) -> list[CheckedClaim]:
        if raw_claims and "verify" not in tools.used:
            tools.used.append("verify")
        return await ClaimChecker(self.chess, position, limits).check(raw_claims)

    # ---------------------------------------------------------------- annotations

    async def _annotations(self, output: dict[str, Any], position: dict[str, Any]) -> BoardAnnotations:
        arrows: list[BoardArrow] = []
        for a in output.get("arrows", [])[:4]:
            frm, to = a.get("from"), a.get("to")
            if a.get("move"):  # squares come from the chess API, not from the model
                u, _ = await self.chess.to_uci(position, a["move"])
                if not u:
                    continue
                frm, to = u[:2], u[2:4]
            if frm and to and SQUARE.match(frm) and SQUARE.match(to) and frm != to:
                arrows.append(BoardArrow(**{"from": frm, "to": to, "color": a.get("color", "blue")}))
        highlights = [
            BoardHighlight(square=h["square"], color=h.get("color", "yellow"))
            for h in output.get("highlights", [])[:4]
            if SQUARE.match(h.get("square") or "")
        ]
        return BoardAnnotations(arrows=arrows, highlights=highlights)

    # ---------------------------------------------------------------- fallback

    def _fallback(self, pos: dict[str, Any], tools: ChessTools, model: str) -> CoachResponse:
        facts = [d for d in (describe_fact(f) for f in pos["facts"]) if d]
        text = "I couldn't put together an explanation that passed verification, so here is only what the chess service confirms. "
        text += (" ".join(f"{d}." for d in facts[:4])) if facts else "There are no checks, pins, hanging pieces or open files in this position."
        text += " Try asking a narrower question, for example about one move."
        return CoachResponse(answer=text, annotations=BoardAnnotations(), claims=[], tools_used=tools.used, model=model, tier="fallback")
