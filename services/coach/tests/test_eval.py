"""The evaluation harness: checks score answers correctly, and a run produces a report."""
from __future__ import annotations

import asyncio
from pathlib import Path

from coach.schemas import BoardAnnotations, CheckedClaim, CoachLine, CoachResponse, LineStep
from evaluation.checks import category_scores, run_checks
from evaluation.run import load_cases, main

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def response(answer: str, claims=(), lines=(), tier="deep", tools_called=()) -> CoachResponse:
    return CoachResponse(
        answer=answer, annotations=BoardAnnotations(), claims=list(claims), tools_used=[], model="m", tier=tier,
        lines=list(lines), tools_called=list(tools_called),
    )


def scholar_line() -> CoachLine:
    sans = ["e4", "e5", "Bc4", "Nc6", "Qh5", "Nf6", "Qxf7#"]
    steps = [LineStep(uci="x", san=s, fen="f", state="ongoing", in_check=False) for s in sans]
    steps[-1] = LineStep(uci="x", san="Qxf7#", fen="f", state="checkmate", in_check=True, winner="white")
    return CoachLine(title="t", start_fen=START, steps=steps)


def supported(checked: str) -> CheckedClaim:
    return CheckedClaim(text=checked, checked=checked, result={"id": "c0", "verdict": "supported", "reason": ""})


def test_a_good_beginner_mate_answer_passes_everything():
    case = {"id": "x", "question": "q", "level": "beginner", "checks": [
        {"mentions_any": ["I can see a win for White"]}, {"mate_line": {"side": "white", "lo": 4, "hi": 5}}]}
    r = response("I can see a win for White: 1. e4 e5 2. Bc4 (bishop to c4) Nc6 3. Qh5 Nf6?? 4. Qxf7# (queen takes on f7, checkmate).",
                 [supported("it is checkmate; white wins")], [scholar_line()])
    results = run_checks(case, r)
    assert all(c.passed for c in results), [c for c in results if not c.passed]
    assert category_scores(results) == {"chess": 1.0, "task": 1.0, "level": 1.0}


def test_failures_are_caught():
    case = {"id": "x", "question": "q", "level": "beginner", "checks": [{"mate_line": {"side": "white", "lo": 6, "hi": 7}}]}
    refuted = CheckedClaim(text="t", checked="t", result={"id": "c0", "verdict": "refuted", "reason": "no"})
    r = response("Play Nf3, the eval is +0.35 and you gain a tempo. " + "word " * 300, [refuted], [scholar_line()], tier="fallback")
    failed = {c.name for c in run_checks(case, r) if not c.passed}
    assert failed == {
        "no refuted claim, no fallback", "at least 1 verified claim(s)", "at most 230 words",
        "no unexplained jargon for a beginner", "moves explained in words for a beginner",
        "verified mate by white in 6-7 moves",
    }


def test_cases_file_is_valid():
    cases = load_cases(Path(__file__).resolve().parents[1] / "evaluation" / "cases.yaml")
    assert len(cases) >= 15
    for c in cases:  # every check kind is known and every case runs through the checker
        run_checks(c, response("ok"))


def test_a_run_writes_a_report(tmp_path, capsys):
    code = asyncio.run(main(["--only", "nimzo-pin,stalemate", "--out", str(tmp_path)]))
    assert code == 0
    md = next(tmp_path.glob("*.md")).read_text()
    assert "| scripted (no LLM) |" in md and "2 cases" in md
    assert next(tmp_path.glob("*.json")).stat().st_size > 0


def test_paid_runs_ask_first(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    code = asyncio.run(main(["--llm", "openai", "--only", "nimzo-pin", "--out", str(tmp_path)]))
    assert code == 1 and not list(tmp_path.iterdir())
    assert "Nothing was sent" in capsys.readouterr().out
