"""Run the coach on the fixed cases, score every answer, and compare models.

    python -m evaluation.run                                   # free: scripted LLM against the in-process mock
    python -m evaluation.run --llm openai --models gpt-6.1-sol # real model (costs money; asks first)
    python -m evaluation.run --llm openai --models gpt-6.1-sol,gpt-6.1-terra --judge gpt-6-luna --yes

Run from services/coach. Without --chess-url the analysis-schema mock is started in-process.
Results go to evaluation/results/<time>.json and .md.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import statistics
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from coach.agent import CoachAgent
from coach.app import make_llm
from coach.chess_client import ChessClient
from coach.config import Settings, TierConfig
from coach.llm.base import LLMUsage
from coach.memory import PlayerMemory
from coach.pricing import PRICES, cost_usd
from coach.schemas import CoachRequest, PositionRef

from .checks import CATEGORIES, category_scores, run_checks
from .judge import judge

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
EST_COST_PER_ANSWER = 0.025  # USD, GPT-6.1 Sol deep tier from the live tests; used only for the warning


def load_cases(path: Path, only: list[str] | None = None) -> list[dict[str, Any]]:
    cases = yaml.safe_load(path.read_text())
    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case ids")
    if only:
        cases = [c for c in cases if c["id"] in only]
    return cases


def start_mock() -> tuple[str, Any]:
    sys.path.insert(0, str(REPO / "packages" / "analysis-schema" / "mock"))
    from http.server import ThreadingHTTPServer

    import server as mock_server  # packages/analysis-schema/mock/server.py

    mock_server.Handler.log_message = lambda *a, **k: None
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), mock_server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{httpd.server_address[1]}", httpd


async def run_case(agent: CoachAgent, memory: PlayerMemory, case: dict[str, Any], judge_llm: Any, judge_model: str | None) -> dict[str, Any]:
    pid = f"p_eval-{case['id']}"
    memory.forget(pid)
    memory.update(pid, {"level": case.get("level", "intermediate"), "explanation_depth": case.get("depth", "normal")})
    req = CoachRequest(
        question=case["question"],
        position=PositionRef(**{k: v for k, v in case["position"].items() if v is not None}),
        last_move=case.get("last_move"),
        player_id=pid,
        player_color=case.get("player_color"),
        depth=case.get("tier", "auto"),
    )
    started = time.monotonic()
    try:
        r = await agent.ask(req)
    except Exception as exc:  # a crash scores zero but doesn't stop the run
        return {"id": case["id"], "error": f"{type(exc).__name__}: {exc}", "scores": {c: 0.0 for c in CATEGORIES},
                "checks": [], "latency_s": round(time.monotonic() - started, 2), "cost_usd": 0.0}
    latency = time.monotonic() - started
    checks = run_checks(case, r)
    out: dict[str, Any] = {
        "id": case["id"],
        "question": case["question"],
        "level": case.get("level"),
        "answer": r.answer,
        "tier": r.tier,
        "tools_called": r.tools_called,
        "claims": [{"checked": c.checked or c.text, "verdict": c.result.get("verdict")} for c in r.claims],
        "lines": [" ".join(s.san for s in l.steps) for l in r.lines],
        "checks": [c.to_json() for c in checks],
        "scores": category_scores(checks),
        "latency_s": round(latency, 2),
        "cost_usd": r.usage.cost_usd,
        "llm_calls": r.usage.llm_calls,
    }
    if judge_model:
        pos = await agent.chess.position(req.position.model_dump())
        verdict, usage = await judge(judge_llm, judge_model, case, pos["position"]["fen"], r)
        out["judge"] = verdict
        out["scores"]["judge"] = round((verdict["explains_why"] + verdict["level_fit"] + verdict["clarity"] - 3) / 12, 3)
        out["judge_cost_usd"] = cost_usd(judge_model, usage)
    return out


async def run_model(model: str, cases: list[dict[str, Any]], base: Settings, judge_model: str | None, parallel: int) -> dict[str, Any]:
    settings = replace(base, fast=replace(base.fast, model=model), deep=replace(base.deep, model=model))
    chess = ChessClient(settings.chess_api_url)
    memory = PlayerMemory(":memory:")
    llm = make_llm(settings)
    agent = CoachAgent(settings, chess, llm, memory)
    judge_llm = make_llm(replace(settings, llm="openai")) if judge_model else None
    gate = asyncio.Semaphore(parallel)

    async def one(case: dict[str, Any]) -> dict[str, Any]:
        async with gate:
            res = await run_case(agent, memory, case, judge_llm, judge_model)
            status = "ERROR" if "error" in res else " ".join(f"{k}={v:.2f}" for k, v in res["scores"].items() if v is not None)
            print(f"  [{model if settings.resolved_llm() == 'openai' else 'scripted'}] {case['id']:<28} {status}  ${res['cost_usd']:.4f}  {res['latency_s']}s", flush=True)
            return res

    try:
        results = await asyncio.gather(*(one(c) for c in cases))
    finally:
        await chess.aclose()
        memory.close()
    label = model if llm.name not in ("scripted",) else "scripted (no LLM)"
    return {"model": label, "llm": llm.name, "cases": results, "summary": summarize(results)}


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    cats = list(CATEGORIES) + (["judge"] if any("judge" in r["scores"] for r in results) else [])
    means = {}
    for cat in cats:
        vals = [r["scores"][cat] for r in results if r["scores"].get(cat) is not None]
        means[cat] = round(sum(vals) / len(vals), 3) if vals else None
    overall_vals = [v for v in means.values() if v is not None]
    lat = sorted(r["latency_s"] for r in results)
    checks = [c for r in results for c in r["checks"]]
    return {
        "overall": round(sum(overall_vals) / len(overall_vals), 3) if overall_vals else 0.0,
        **means,
        "checks_passed": f"{sum(c['passed'] for c in checks)}/{len(checks)}",
        "errors": sum(1 for r in results if "error" in r),
        "cost_total_usd": round(sum(r["cost_usd"] for r in results), 4),
        "cost_per_answer_usd": round(sum(r["cost_usd"] for r in results) / max(1, len(results)), 4),
        "judge_cost_usd": round(sum(r.get("judge_cost_usd", 0.0) for r in results), 4),
        "latency_p50_s": round(statistics.median(lat), 1) if lat else 0,
        "latency_max_s": lat[-1] if lat else 0,
    }


def report(runs: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    cats = [c for c in ("overall", *CATEGORIES, "judge") if any(r["summary"].get(c) is not None for r in runs)]
    pct = lambda v: "–" if v is None else f"{v * 100:.0f}%"  # noqa: E731
    lines = [
        f"# Coach evaluation · {meta['time']}",
        "",
        f"{meta['cases']} cases · chess API: {meta['chess']} · LLM: {meta['llm']}" + (f" · judge: {meta['judge']}" if meta["judge"] else ""),
        "",
        "| Model | " + " | ".join(c.capitalize() for c in cats) + " | Checks | $/answer | p50 latency |",
        "| --- |" + " ---: |" * (len(cats) + 3),
    ]
    for run in runs:
        s = run["summary"]
        lines.append(
            f"| {run['model']} | " + " | ".join(pct(s.get(c)) for c in cats)
            + f" | {s['checks_passed']} | ${s['cost_per_answer_usd']:.4f} | {s['latency_p50_s']}s |"
        )
    lines += ["", "Chess = correctness (no refuted claim, verified claims, key facts) · Task = did what was asked",
              "· Level = length and wording for the player · Judge = LLM-graded explanation quality (optional)", ""]
    for run in runs:
        failed = [(r["id"], c) for r in run["cases"] for c in r["checks"] if not c["passed"]]
        errors = [r for r in run["cases"] if "error" in r]
        lines.append(f"## {run['model']}: {len(failed)} failed check(s)" + (f", {len(errors)} error(s)" if errors else ""))
        lines.append("")
        for r in errors:
            lines.append(f"- **{r['id']}** crashed: {r['error']}")
        for cid, c in failed:
            lines.append(f"- **{cid}** · {c['category']} · {c['name']}" + (f" ({c['detail']})" if c["detail"] else ""))
        lines.append("")
    return "\n".join(lines)


async def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Evaluate the Think64 coach on fixed positions and questions.")
    ap.add_argument("--llm", choices=["scripted", "openai"], default="scripted")
    ap.add_argument("--models", default="gpt-6.1-sol", help="comma-separated model ids to compare")
    ap.add_argument("--effort-fast", default="low")
    ap.add_argument("--effort-deep", default="high")
    ap.add_argument("--cases", type=Path, default=HERE / "cases.yaml")
    ap.add_argument("--only", help="comma-separated case ids")
    ap.add_argument("--judge", metavar="MODEL", help="also grade explanations with this OpenAI model (costs money)")
    ap.add_argument("--chess-url", help="chess API to use (default: start the mock in-process)")
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--out", type=Path, default=HERE / "results")
    ap.add_argument("--yes", action="store_true", help="don't ask before spending money")
    args = ap.parse_args(argv)

    for name in ("httpx", "coach"):  # per-request logs would drown the results
        logging.getLogger(name).setLevel(logging.WARNING)
    cases = load_cases(args.cases, args.only.split(",") if args.only else None)
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if args.llm == "scripted":
        models = models[:1]

    if (args.llm == "openai" or args.judge) and not args.yes:
        n = len(cases) * (len(models) if args.llm == "openai" else 0)
        est = n * EST_COST_PER_ANSWER + (len(cases) * len(models) * 0.002 if args.judge else 0)
        unpriced = [m for m in models + ([args.judge] if args.judge else []) if m not in PRICES]
        print(f"This sends {n} coach questions{' plus judge calls' if args.judge else ''} to OpenAI: roughly ${est:.2f}.")
        if unpriced:
            print(f"No price on file for {unpriced}; their cost will show as $0.")
        if not sys.stdin.isatty() or input("Continue? [y/N] ").strip().lower() != "y":
            print("Stopped. Nothing was sent.")
            return 1

    httpd = None
    chess_url = args.chess_url
    if not chess_url:
        chess_url, httpd = start_mock()
    base = Settings(
        chess_api_url=chess_url,
        llm=args.llm,
        fast=TierConfig(models[0], args.effort_fast),
        deep=TierConfig(models[0], args.effort_deep),
        db_path=":memory:",
    )
    print(f"{len(cases)} cases × {len(models)} model(s) · chess API {chess_url}{' (mock)' if httpd else ''}")
    try:
        runs = [await run_model(m, cases, base, args.judge, args.parallel) for m in models]
    finally:
        if httpd:
            httpd.shutdown()

    stamp = time.strftime("%Y%m%d-%H%M%S")
    meta = {"time": time.strftime("%Y-%m-%d %H:%M"), "cases": len(cases), "chess": "mock" if httpd else chess_url,
            "llm": args.llm, "judge": args.judge}
    args.out.mkdir(parents=True, exist_ok=True)
    md = report(runs, meta)
    (args.out / f"{stamp}.json").write_text(json.dumps({"meta": meta, "runs": runs}, indent=2))
    (args.out / f"{stamp}.md").write_text(md)
    print("\n" + md)
    print(f"Saved evaluation/results/{stamp}.json and .md")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
