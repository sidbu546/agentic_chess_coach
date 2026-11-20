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
from dataclasses import dataclass
from typing import Any

from .board_text import describe_fact, position_brief
from .chess_client import ChessClient
from .config import Settings, TierConfig
from .llm.base import LLMAdapter, LLMResult, LLMUsage
from .game import GameReplay, numbered_game
from .memory import ANONYMOUS, DEFAULT_DEPTH, DEFAULT_LEVEL, PlayerMemory
from .pricing import cost_usd
from .prompts import ANSWER_SCHEMA, revision_request, system_prompt
from .schemas import BoardAnnotations, BoardArrow, BoardHighlight, CheckedClaim, CoachLine, CoachRequest, CoachResponse, Usage
from .tools import TOOL_DEFINITIONS, ChessTools
from .verification import ClaimChecker

log = logging.getLogger("coach.agent")

# Engine limits per player level (contract decision 7: the caller picks depth and MultiPV).
LEVEL_LIMITS = {
    "beginner": {"depth": 12, "multipv": 2},
    "intermediate": {"depth": 16, "multipv": 3},
    "advanced": {"depth": 20, "multipv": 3},
}

DEEP_WORDS = re.compile(
    r"\b(why|how|plan|plans|strategy|strategic|explain|compare|versus|vs|better|worse|instead|idea|ideas|"
    r"structure|long[- ]term|evaluate|evaluation|what if|review|understand|difference|sacrifice|endgame|"
    r"middlegame|imbalance|weakness|weaknesses|mistakes|habits|repeat|improve)\b",
    re.I,
)
SAN_TOKEN = re.compile(r"\b(?:[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8]|[a-h][1-8](?:=[QRBN])?|O-O(?:-O)?)[+#]?(?![\w])")
SQUARE = re.compile(r"^[a-h][1-8]$")
# "checkmate in 4-5 moves", "win within 3 moves", "mate in 11 moves" - the count must follow "in"/"within".
MATE_REQUEST = re.compile(
    r"\b(?:check\s?mate|mate|win)\w*\b(?:\s+\w+){0,3}?\s+(?:in|within)\s+(\d{1,2})(?:\s*(?:-|–|—|to|or)\s*(\d{1,2}))?\s*moves?\b",
    re.I,
)
NO_MATE = re.compile(r"\b(?:no|not|don'?t|without|no need (?:for|of)|skip)\b(?:\s+\w+){0,3}?\s+check\s?mate\b", re.I)


@dataclass(frozen=True)
class MateTask:
    """'How can White checkmate in 4-5 moves?': the answer must contain a verified mate in that range."""

    side: str
    lo: int
    hi: int

    def text(self) -> str:
        span = f"{self.lo}-{self.hi}" if self.lo != self.hi else str(self.hi)
        return f"checkmate by {self.side} in {span} {self.side} moves (counting only {self.side}'s moves, the mating move included)"


def mate_task(question: str, side_to_move: str) -> MateTask | None:
    m = MATE_REQUEST.search(question)
    if not m or NO_MATE.search(question):
        return None
    if m.group(2):
        lo, hi = sorted((int(m.group(1)), int(m.group(2))))
    else:  # "in 11 moves" -> its 10th or 11th move
        hi = int(m.group(1))
        lo = max(1, hi - 1)
    if not 1 <= hi <= 20:
        return None
    white, black = re.search(r"\bwhite\b", question, re.I), re.search(r"\bblack\b", question, re.I)
    side = "white" if white and not black else "black" if black and not white else side_to_move
    return MateTask(side, lo, hi)


def mate_problem(task: MateTask, lines: list[CoachLine], fen: str) -> str | None:
    """None if a verified line delivers the requested mate; otherwise what is wrong, for the revision."""
    stm = "white" if fen.split()[1] == "w" else "black"
    seen = "none of the verified lines in your answer ends in checkmate"
    for line in lines:
        moves_by_side = sum(1 for i in range(len(line.steps)) if (i % 2 == 0) == (stm == task.side))
        last = line.steps[-1]
        if last.state == "checkmate" and last.winner == task.side:
            if task.lo <= moves_by_side <= task.hi:
                return None
            seen = f"your line ends in checkmate after {moves_by_side} {task.side} moves, outside the range asked"
    return (
        f"The player asked for {task.text()}, but {seen}. Give one line from the current position, as a legal_line "
        f"claim, that ends with {task.side}'s checkmating move inside that range, plus a checkmate claim with after = "
        f"the whole line. Build it with explore_line until it reports checkmate; use natural-looking mistakes for the "
        f"defending side where needed."
    )


def route(req: CoachRequest) -> str:
    """'deep' for questions that need real reasoning, 'fast' for quick lookups."""
    if req.depth != "auto":
        return req.depth
    q = req.question
    if len(q) > 180 or DEEP_WORDS.search(q) or len(SAN_TOKEN.findall(q)) >= 2:
        return "deep"
    return "fast"


class CoachAgent:
    def __init__(self, settings: Settings, chess: ChessClient, llm: LLMAdapter, memory: PlayerMemory | None = None):
        self.settings = settings
        self.chess = chess
        self.llm = llm
        self.memory = memory
        self.replay = GameReplay(chess)
        self._engine_real: bool | None = None

    async def _engine_is_real(self) -> bool:
        """Whether the chess API runs a real engine (the mock reports engine name "mock")."""
        if self._engine_real is None:
            try:
                self._engine_real = ((await self.chess.health()).get("engine") or {}).get("name") != "mock"
            except Exception:
                return False
        return self._engine_real

    async def ask(self, req: CoachRequest) -> CoachResponse:
        started = time.monotonic()
        position = req.position.model_dump()
        pos = await self.chess.position(position)  # also validates the position (422 on bad FEN/history)
        fen = pos["position"]["fen"]

        side_to_move = "white" if fen.split()[1] == "w" else "black"
        task = mate_task(req.question, side_to_move)
        tier = "deep" if task and req.depth != "fast" else route(req)
        tier_cfg: TierConfig = self.settings.deep if tier == "deep" else self.settings.fast
        remember = self.memory is not None and req.player_id != ANONYMOUS
        profile = self.memory.profile(req.player_id) if remember else None
        level = profile["level"] if profile else DEFAULT_LEVEL
        depth = profile["explanation_depth"] if profile else DEFAULT_DEPTH
        limits = {"depth": LEVEL_LIMITS[level]["depth"]}
        game_sans = await self.replay.sans(position)
        tools = ChessTools(
            self.chess, position, fen, limits,
            engine_real=await self._engine_is_real(), player_color=req.player_color, game_sans=game_sans,
        )
        tools.used.append("position")

        messages = [
            {
                "role": "user" if t.role == "user" else "assistant",
                # Turns about another position (or another game) must not be read as about this one.
                "content": f"[This message was about a different position: {t.fen}]\n{t.content}" if t.fen and t.fen != fen else t.content,
            }
            for t in req.history[-6:]
        ]
        memory_note = self.memory.context(profile, req.session_id) if profile else None
        context = self._context(pos, req, memory_note, game_sans)
        if task:
            context += f"\n\nTask: give a line that ends in {task.text()}."
        messages.append({"role": "user", "content": context})
        common = dict(
            model=tier_cfg.model,
            effort=tier_cfg.effort,
            system=system_prompt(level, depth),
            tools=TOOL_DEFINITIONS,
            execute=tools.run,
            output_schema=ANSWER_SCHEMA,
            max_tool_rounds=self.settings.max_tool_rounds,
        )

        usage = LLMUsage()
        result: LLMResult = await self.llm.run(messages=messages, **common)
        usage.add(result.usage)
        checked, steps = await self._verify(result.output.get("claims", []), position, limits, tools)

        # A checkmate-in-N request gets one extra round to find the mate.
        for _ in range(self.settings.max_revisions + (1 if task else 0)):
            problems = [
                f"\"{c.text}\" (checked: {c.checked}): {c.result['verdict']} - {c.result['reason']}"
                for c in checked
                if c.result["verdict"] != "supported"
            ]
            if task:
                missing = mate_problem(task, self._lines(checked, steps, fen), fen)
                if missing:
                    problems.append(missing)
            if not problems:
                break
            result = await self.llm.run(messages=[{"role": "user", "content": revision_request(problems)}], state=result.state, **common)
            usage.add(result.usage)
            checked, steps = await self._verify(result.output.get("claims", []), position, limits, tools)

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
                lines=self._lines(checked, steps, fen),
            )
        response.level, response.explanation_depth = level, depth
        response.usage = Usage(
            input_tokens=usage.input_tokens,
            cached_tokens=usage.cached_tokens,
            output_tokens=usage.output_tokens,
            reasoning_tokens=usage.reasoning_tokens,
            llm_calls=usage.calls,
            cost_usd=cost_usd(tier_cfg.model, usage),
        )
        if remember:
            self.memory.record_interaction(
                req.player_id, req.session_id or "default", req.question, response.answer, fen, response.tier, response.usage.cost_usd
            )
            for m in tools.mistakes:
                self.memory.record_mistakes(req.player_id, m["fen"], m["move"], m["color"], m["patterns"])
        verdicts = [c.result["verdict"] for c in response.claims]
        log.info(
            "answer tier=%s model=%s calls=%d in=%d cached=%d out=%d reasoning=%d cost=$%.4f claims=%s tools=%s %.1fs",
            response.tier, response.model, usage.calls, usage.input_tokens, usage.cached_tokens, usage.output_tokens,
            usage.reasoning_tokens, response.usage.cost_usd, verdicts, tools.used, time.monotonic() - started,
        )
        return response

    # ---------------------------------------------------------------- context

    @staticmethod
    def _context(pos: dict[str, Any], req: CoachRequest, memory_note: str | None = None, game_sans: list[str] | None = None) -> str:
        last = req.last_move.san if req.last_move else None
        game = numbered_game(game_sans, req.position.start_fen) if game_sans else "none yet"
        side = (
            f"The board faces {req.player_color}, so the player probably plays {req.player_color}. If the question says they "
            "play the other side, believe the question (and pass that side to review_game). Judge the player's moves, not "
            "the opponent's.\n"
            if req.player_color
            else ""
        )
        return (
            (f"{memory_note}\n\n" if memory_note else "")
            + side
            + f"Game so far ({len(req.position.moves)} plies, from the rules engine): {game}\n\n"
            "Current position (ground truth from the rules engine):\n"
            f"{position_brief(pos, last)}\n\n"
            f"Question: {req.question.strip()}"
        )

    # ---------------------------------------------------------------- verification

    async def _verify(
        self, raw_claims: list[dict[str, Any]], position: dict[str, Any], limits: dict[str, Any], tools: ChessTools
    ) -> tuple[list[CheckedClaim], dict[str, list[dict[str, Any]]]]:
        if raw_claims and "verify" not in tools.used:
            tools.used.append("verify")
        checker = ClaimChecker(self.chess, position, limits)
        checked = await checker.check(raw_claims)
        return checked, checker.lines

    @staticmethod
    def _lines(checked: list[CheckedClaim], steps: dict[str, list[dict[str, Any]]], start_fen: str) -> list[CoachLine]:
        """Supported line and move claims as playable lines (longest first, no duplicates or prefixes, at most 3)."""
        out: dict[tuple[str, ...], CoachLine] = {}
        for c in checked:
            line = steps.get(c.result.get("id", ""))
            if not line or c.result.get("verdict") != "supported":
                continue
            key = tuple(s["uci"] for s in line)
            if key not in out:
                out[key] = CoachLine(title=c.text, start_fen=start_fen, steps=line)
        # A move that is just the start of a longer line adds nothing to play back.
        keys = list(out)
        kept = [out[k] for k in keys if not any(len(o) > len(k) and o[: len(k)] == k for o in keys)]
        return sorted(kept, key=lambda l: -len(l.steps))[:3]

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
