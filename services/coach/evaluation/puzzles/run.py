"""Puzzle-solving comparison: Think64 vs general-purpose models on the same Lichess puzzles.

    cd services/coach && source ../../.venv/bin/activate
    python -m evaluation.puzzles.run --systems oracle,random                  # free: checks the grader
    python -m evaluation.puzzles.run --systems think64,claude-image,claude-fen,sol-fen --limit 20
    python -m evaluation.puzzles.run                                         # all 104 puzzles, default systems

Systems (every one gets the same question and must end with "FINAL: <moves>"):
  think64        the coach: GPT-6.1 Sol deep tier + chess tools + claim checking (needs OPENAI_API_KEY)
  claude-image   Claude Opus 5.5, high effort, a picture of the board (as a player would upload it)
  claude-fen     Claude Opus 5.5, high effort, the position as FEN text
  sol-image      GPT-6.1 Sol alone, high effort, the picture (same model as Think64, no system around it)
  sol-fen        GPT-6.1 Sol alone, high effort, FEN text
  oracle, random free self-tests: the known solution / a random legal move

Grading is done by python-chess against the puzzle's stored solution (see grade.py), never by a model.
Results go to evaluation/results/puzzles-<time>.json and .md.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import math
import os
import random
import statistics
import sys
import time
from dataclasses import replace
from itertools import combinations
from pathlib import Path
from typing import Any, Awaitable, Callable

import chess

from coach.agent import CoachAgent
from coach.app import make_llm
from coach.chess_client import ChessClient
from coach.config import Settings, TierConfig
from coach.memory import PlayerMemory
from coach.pricing import cost_usd
from coach.schemas import CoachRequest, PositionRef

from ..run import start_mock
from .board_image import render
from .grade import grade

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent / "results"
CLAUDE_MODEL = "claude-opus-5-5"
SOL_MODEL = "gpt-6.1-sol"
# USD per 1M tokens (input, output); Anthropic list prices, checked 2026-11-24. Output includes thinking.
CLAUDE_PRICES = {"claude-opus-5-5": (4.00, 20.00), "claude-sonnet-5-5": (2.00, 10.00)}
# Rough $/answer for the spending warning only; the report uses real token usage.
EST = {"think64": 0.03, "claude-image": 0.10, "claude-fen": 0.10, "sol-image": 0.04, "sol-fen": 0.04}
DEFAULT_SYSTEMS = "think64,claude-image,claude-fen,sol-fen"

PROMPT = (
    "Chess puzzle: {Side} to move. {Opp} just played {last}.\n"
    "Find the best move for {Side} and the winning continuation, including {Opp}'s best replies.\n"
    "Explain briefly, then end your reply with exactly one line in this format:\n"
    "FINAL: <the line in SAN, starting with {Side}'s move>\n"
    "Example: FINAL: Qh5+ Kg8 Qh7#"
)


def question(p: dict[str, Any], mode: str) -> str:
    side, opp = p["side"].capitalize(), ("Black" if p["side"] == "white" else "White")
    q = PROMPT.format(Side=side, Opp=opp, last=p["last_move"]["san"])
    if mode == "image":
        return f"The image shows the position, seen from {side}'s side.\n" + q
    if mode == "fen":
        return f"Position (FEN): {p['fen']}\n" + q
    return q


def image_b64(p: dict[str, Any]) -> str:
    return base64.standard_b64encode(render(p["fen"], p["side"] == "white", p["last_move"]["uci"])).decode()


Answer = dict[str, Any]  # {"text", "cost_usd", "tokens_in", "tokens_out", "note"?}


# ---------- systems ----------

def claude_system(mode: str, model: str, effort: str) -> Callable[[dict[str, Any]], Awaitable[Answer]]:
    import anthropic

    client = anthropic.AsyncAnthropic(max_retries=4)
    p_in, p_out = CLAUDE_PRICES.get(model, (0.0, 0.0))

    async def ask(p: dict[str, Any]) -> Answer:
        content: list[dict[str, Any]] = []
        if mode == "image":
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_b64(p)}})
        content.append({"type": "text", "text": question(p, mode)})
        async with client.messages.stream(
            model=model,
            max_tokens=32000,
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            messages=[{"role": "user", "content": content}],
        ) as stream:
            msg = await stream.get_final_message()
        text = "".join(b.text for b in msg.content if b.type == "text")
        u = msg.usage
        return {"text": text, "cost_usd": round((u.input_tokens * p_in + u.output_tokens * p_out) / 1e6, 6),
                "tokens_in": u.input_tokens, "tokens_out": u.output_tokens,
                "note": None if msg.stop_reason == "end_turn" else f"stop_reason={msg.stop_reason}"}

    return ask


def sol_system(mode: str, model: str, effort: str) -> Callable[[dict[str, Any]], Awaitable[Answer]]:
    from openai import AsyncOpenAI

    from coach.llm.openai_adapter import _usage

    client = AsyncOpenAI(max_retries=4)

    async def ask(p: dict[str, Any]) -> Answer:
        content: list[dict[str, Any]] = []
        if mode == "image":
            content.append({"type": "input_image", "image_url": f"data:image/png;base64,{image_b64(p)}"})
        content.append({"type": "input_text", "text": question(p, mode)})
        resp = await client.responses.create(model=model, reasoning={"effort": effort},
                                             input=[{"role": "user", "content": content}], store=False)
        u = _usage(resp)
        return {"text": resp.output_text or "", "cost_usd": cost_usd(model, u), "tokens_in": u.input_tokens,
                "tokens_out": u.output_tokens, "note": None if resp.status == "completed" else f"status={resp.status}"}

    return ask


class Think64:
    """The coach exactly as the web app calls it, on the puzzle position with the last move played."""

    def __init__(self, chess_url: str, llm: str, model: str):
        settings = Settings(chess_api_url=chess_url, llm=llm, fast=TierConfig(model, "low"),
                            deep=TierConfig(model, "high"), db_path=":memory:")
        self.chess = ChessClient(chess_url)
        self.memory = PlayerMemory(":memory:")
        self.agent = CoachAgent(settings, self.chess, make_llm(settings), self.memory)

    async def ask(self, p: dict[str, Any]) -> Answer:
        pid = f"p_puzzle-{p['id']}"
        self.memory.update(pid, {"level": "advanced", "explanation_depth": "short"})
        req = CoachRequest(
            question=question(p, "board"),
            position=PositionRef(start_fen=p["source_fen"], moves=[p["last_move"]["uci"]]),
            last_move=p["last_move"], player_id=pid, player_color=p["side"], depth="deep",
        )
        r = await self.agent.ask(req)
        text, note = r.answer, None
        if "FINAL" not in text.upper() and r.lines:  # fall back to its first verified line
            text += "\nFINAL: " + " ".join(s.san for s in r.lines[0].steps)
            note = "final line taken from its verified line"
        u = r.usage
        return {"text": text, "cost_usd": u.cost_usd, "tokens_in": u.input_tokens, "tokens_out": u.output_tokens,
                "note": note, "tier": r.tier}

    async def close(self) -> None:
        await self.chess.aclose()
        self.memory.close()


async def oracle(p: dict[str, Any]) -> Answer:
    return {"text": "FINAL: " + " ".join(p["solution_san"]), "cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0}


async def random_move(p: dict[str, Any]) -> Answer:
    b = chess.Board(p["fen"])
    m = random.Random(p["id"]).choice(sorted(b.legal_moves, key=lambda m: m.uci()))
    return {"text": "FINAL: " + b.san(m), "cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0}


# ---------- statistics ----------

def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def mcnemar_p(b: int, c: int) -> float:
    """Exact two-sided McNemar test on the discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    k = sum(r["grade"]["solved"] for r in rows)
    lo, hi = wilson(k, n)
    cost = sum(r["cost_usd"] for r in rows)
    lat = sorted(r["latency_s"] for r in rows)

    def rate(key: str) -> float:
        return round(sum(bool(r["grade"][key]) for r in rows) / max(1, n), 3)

    def by(field: str) -> dict[str, str]:
        out = {}
        for val in sorted({r[field] for r in rows}):
            sub = [r for r in rows if r[field] == val]
            out[val] = f"{sum(r['grade']['solved'] for r in sub)}/{len(sub)}"
        return out

    return {
        "n": n, "solved": k, "accuracy": round(k / max(1, n), 3), "ci95": [round(lo, 3), round(hi, 3)],
        "first_move": rate("first_move"), "illegal": rate("illegal"), "fake_mate": rate("fake_mate"),
        "no_answer": round(sum(not r["grade"]["answered"] for r in rows) / max(1, n), 3),
        "errors": sum(1 for r in rows if r.get("error")),
        "cost_total_usd": round(cost, 4), "cost_per_answer_usd": round(cost / max(1, n), 4),
        "cost_per_solved_usd": round(cost / k, 4) if k else None,
        "latency_p50_s": round(statistics.median(lat), 1) if lat else 0,
        "by_band": by("band"), "by_kind": by("kind"),
    }


def pairwise(runs: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Compares only puzzles both systems actually answered: a failed API call is not a wrong answer."""
    out = []
    for a, b in combinations(runs, 2):
        sa = {r["id"]: r["grade"]["solved"] for r in runs[a] if not r.get("error")}
        sb = {r["id"]: r["grade"]["solved"] for r in runs[b] if not r.get("error")}
        ids = sa.keys() & sb.keys()
        if not ids:
            continue
        a_only = sum(1 for i in ids if sa[i] and not sb[i])
        b_only = sum(1 for i in ids if sb[i] and not sa[i])
        out.append({"a": a, "b": b, "n": len(ids), "a_only": a_only, "b_only": b_only,
                    "p": round(mcnemar_p(a_only, b_only), 4)})
    return out


def report(meta: dict[str, Any], summaries: dict[str, dict[str, Any]], pairs: list[dict[str, Any]]) -> str:
    pct = lambda v: f"{v * 100:.0f}%"  # noqa: E731
    bands = sorted({b for s in summaries.values() for b in s["by_band"]}, key=lambda b: int(b.split("-")[0]))
    lines = [
        f"# Puzzle solving · {meta['time']}", "",
        f"{meta['puzzles']} Lichess puzzles · graded by python-chess against the known solution · chess API: {meta['chess']}", "",
        "| System | Solved | 95% CI | First move | Illegal move | Fake mate | $/answer | $/solved |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    failed = {name: s["errors"] for name, s in summaries.items() if s["errors"]}
    if failed:
        lines[2:2] = [f"> ⚠ **Not a valid comparison:** API calls failed for "
                      + ", ".join(f"{k} ({v}/{summaries[k]['n']})" for k, v in failed.items())
                      + ". Failed calls count as unsolved below; the head-to-head skips them. Fix and re-run.", ""]
    for name, s in summaries.items():
        cps = f"${s['cost_per_solved_usd']:.3f}" if s["cost_per_solved_usd"] is not None else "–"
        lines.append(f"| {name} | {s['solved']}/{s['n']} ({pct(s['accuracy'])}) | {pct(s['ci95'][0])}–{pct(s['ci95'][1])} "
                     f"| {pct(s['first_move'])} | {pct(s['illegal'])} | {pct(s['fake_mate'])} "
                     f"| ${s['cost_per_answer_usd']:.3f} | {cps} |")
    lines += ["", "## By difficulty (Lichess rating) and type", "",
              "| System | " + " | ".join(bands) + " | Mate | Other |", "| --- |" + " ---: |" * (len(bands) + 2)]
    for name, s in summaries.items():
        lines.append(f"| {name} | " + " | ".join(s["by_band"].get(b, "–") for b in bands)
                     + f" | {s['by_kind'].get('mate', '–')} | {s['by_kind'].get('other', '–')} |")
    if pairs:
        lines += ["", "## Head to head (puzzles only one of the two solved)", "",
                  "| A | B | puzzles both answered | only A solved | only B solved | p (McNemar) | Verdict |",
                  "| --- | --- | ---: | ---: | ---: | ---: | --- |"]
        for x in pairs:
            verdict = "no significant difference" if x["p"] >= 0.05 else f"**{x['a'] if x['a_only'] > x['b_only'] else x['b']} better**"
            lines.append(f"| {x['a']} | {x['b']} | {x['n']} | {x['a_only']} | {x['b_only']} | {x['p']} | {verdict} |")
    lines += ["", "Solved = every move of the solver matches the Lichess solution (another mating move also counts). "
              "First move = the key move only. Illegal move / Fake mate = share of answers whose FINAL line contains "
              "an illegal move / a '#' that is not checkmate. p < 0.05 means the difference is unlikely to be luck."]
    return "\n".join(lines)


# ---------- main ----------

async def check_keys(paid: list[str], claude_model: str, sol_model: str) -> list[str]:
    """Free check (model lookup, no tokens) that each provider accepts its key, before anything is spent."""
    problems = []
    if any(s.startswith("claude") for s in paid):
        import anthropic

        try:
            await anthropic.AsyncAnthropic(max_retries=1).models.retrieve(claude_model)
        except anthropic.AuthenticationError:
            problems.append("Anthropic rejected ANTHROPIC_API_KEY (401). Create a new key at console.anthropic.com.")
        except anthropic.NotFoundError:
            problems.append(f"Anthropic has no model {claude_model!r} for this key.")
        except anthropic.APIError as exc:
            problems.append(f"Anthropic check failed: {exc}")
    if any(s in ("think64", "sol-image", "sol-fen") for s in paid):
        import openai

        try:
            await openai.AsyncOpenAI(max_retries=1).models.retrieve(sol_model)
        except openai.AuthenticationError:
            problems.append("OpenAI rejected OPENAI_API_KEY (401).")
        except openai.NotFoundError:
            problems.append(f"OpenAI has no model {sol_model!r} for this key.")
        except openai.APIError as exc:
            problems.append(f"OpenAI check failed: {exc}")
    return problems


async def run_system(name: str, ask: Callable[[dict[str, Any]], Awaitable[Answer]], puzzles: list[dict[str, Any]],
                     parallel: int) -> list[dict[str, Any]]:
    gate = asyncio.Semaphore(parallel)

    async def one(p: dict[str, Any]) -> dict[str, Any]:
        async with gate:
            started = time.monotonic()
            try:
                ans = await ask(p)
                err = None
            except Exception as exc:  # a failed call scores as unsolved but doesn't stop the run
                ans, err = {"text": "", "cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0}, f"{type(exc).__name__}: {exc}"[:300]
            g = grade(p, ans["text"])
            row = {"id": p["id"], "band": p["band"], "kind": p["kind"], "rating": p["rating"],
                   "solution": " ".join(p["solution_san"]), **ans, "grade": g, "error": err,
                   "latency_s": round(time.monotonic() - started, 1)}
            mark = "ERROR" if err else ("solved" if g["solved"] else ("first move" if g["first_move"] else "wrong"))
            print(f"  [{name}] {p['id']} {p['band']:>9} {p['kind']:<5} {mark:<10} ${row['cost_usd']:.4f} {row['latency_s']}s", flush=True)
            return row

    return list(await asyncio.gather(*(one(p) for p in puzzles)))


async def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compare puzzle solving: Think64 vs general-purpose models.")
    ap.add_argument("--systems", default=DEFAULT_SYSTEMS)
    ap.add_argument("--limit", type=int, help="first N puzzles (the set is shuffled, so any N is mixed)")
    ap.add_argument("--only", help="comma-separated puzzle ids")
    ap.add_argument("--claude-model", default=CLAUDE_MODEL)
    ap.add_argument("--sol-model", default=SOL_MODEL)
    ap.add_argument("--effort", default="high", help="reasoning effort for the plain models (Think64 deep tier is high)")
    ap.add_argument("--think64-llm", choices=["openai", "scripted"], default="openai")
    ap.add_argument("--chess-url", help="chess API for Think64 (default: the mock, in-process)")
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--yes", action="store_true", help="don't ask before spending money")
    args = ap.parse_args(argv)
    for name in ("httpx", "httpx2", "coach", "anthropic", "openai"):
        logging.getLogger(name).setLevel(logging.WARNING)

    data = json.loads((HERE / "puzzles.json").read_text())
    puzzles = data["puzzles"]
    if args.only:
        wanted = set(args.only.split(","))
        puzzles = [p for p in puzzles if p["id"] in wanted]
    if args.limit:
        puzzles = puzzles[: args.limit]
    systems = [s.strip() for s in args.systems.split(",") if s.strip()]
    known = {"think64", "claude-image", "claude-fen", "sol-image", "sol-fen", "oracle", "random"}
    if unknown := [s for s in systems if s not in known]:
        raise SystemExit(f"unknown system(s) {unknown}; choose from {sorted(known)}")

    paid = [s for s in systems if s in EST and not (s == "think64" and args.think64_llm == "scripted")]
    missing = [k for k, need in (("OPENAI_API_KEY", any(s in paid for s in ("think64", "sol-image", "sol-fen"))),
                                 ("ANTHROPIC_API_KEY", any(s.startswith("claude") for s in paid))) if need and not os.environ.get(k)]
    if missing:
        raise SystemExit(f"set {', '.join(missing)} in your terminal first (export ...=...)")
    if paid and not args.yes:
        est = sum(EST[s] for s in paid) * len(puzzles)
        print(f"This sends {len(puzzles)} puzzles to {', '.join(paid)}: roughly ${est:.2f} in total.")
        if not sys.stdin.isatty() or input("Continue? [y/N] ").strip().lower() != "y":
            print("Stopped. Nothing was sent.")
            return 1

    if problems := await check_keys(paid, args.claude_model, args.sol_model):
        print("Stopped before sending any puzzle:\n  " + "\n  ".join(problems))
        return 1

    httpd = None
    chess_url = args.chess_url
    if "think64" in systems and not chess_url:
        chess_url, httpd = start_mock()
    print(f"{len(puzzles)} puzzles × {len(systems)} system(s)")

    runs: dict[str, list[dict[str, Any]]] = {}
    think = None
    try:
        for s in systems:
            if s == "think64":
                think = Think64(chess_url, args.think64_llm, args.sol_model)
                ask = think.ask
            elif s.startswith("claude"):
                ask = claude_system(s.split("-")[1], args.claude_model, args.effort)
            elif s.startswith("sol"):
                ask = sol_system(s.split("-")[1], args.sol_model, args.effort)
            else:
                ask = oracle if s == "oracle" else random_move
            label = f"think64 (scripted)" if s == "think64" and args.think64_llm == "scripted" else s
            runs[label] = await run_system(label, ask, puzzles, args.parallel)
    finally:
        if think:
            await think.close()
        if httpd:
            httpd.shutdown()

    summaries = {name: summarize(rows) for name, rows in runs.items()}
    pairs = pairwise(runs)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    meta = {"time": time.strftime("%Y-%m-%d %H:%M"), "puzzles": len(puzzles),
            "chess": ("mock" if httpd else chess_url) if "think64" in systems else "–",
            "claude_model": args.claude_model, "sol_model": args.sol_model, "effort": args.effort}
    md = report(meta, summaries, pairs)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"puzzles-{stamp}.json").write_text(json.dumps({"meta": meta, "summaries": summaries, "pairs": pairs, "runs": runs}, indent=1))
    (RESULTS / f"puzzles-{stamp}.md").write_text(md)
    print("\n" + md)
    print(f"\nSaved evaluation/results/puzzles-{stamp}.json and .md")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
