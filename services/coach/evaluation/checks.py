"""Deterministic checks on one coach answer. Each check is pass/fail in one category:

- chess: is the chess right? (no refuted claim reaches the player, verified claims, the key facts)
- task:  did it do what was asked? (mate in the asked range, a playable line, the right tool)
- level: does it fit the player? (length for the explanation depth, beginner-friendly wording)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from coach.schemas import CoachResponse

MAX_WORDS = {"short": 90, "normal": 230, "detailed": 420}
# Words a beginner shouldn't meet unexplained.
JARGON = re.compile(
    r"\b(centipawns?|cp|tempo|tempi|prophylaxis|prophylactic|zwischenzug|zugzwang|outpost|fianchetto|"
    r"initiative|desperado|minority attack|eval(uation)? of [+-]?\d)\b|(?<![\w.])[+-]\d+\.\d\d?\b",
    re.I,
)
PIECE_MOVE = re.compile(r"(?<![\w])[KQRBN][a-h1-8]?x?[a-h][1-8][+#]?")
GLOSSED_MOVE = re.compile(r"(?<![\w])[KQRBN][a-h1-8]?x?[a-h][1-8][+#]?\s*\(")
CATEGORIES = ("chess", "task", "level")


@dataclass
class CheckResult:
    name: str
    category: str
    passed: bool
    detail: str = ""

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "category": self.category, "passed": self.passed, "detail": self.detail}


def _mentions(text: str, word: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(word)}(?![A-Za-z0-9])", text, re.I) is not None


def _side_moves(line: Any, side: str) -> int:
    stm = "white" if line.start_fen.split()[1] == "w" else "black"
    return sum(1 for i in range(len(line.steps)) if (i % 2 == 0) == (stm == side))


def default_checks(case: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"no_refuted": True}, {"min_supported": case.get("min_supported", 1)}]
    out.append({"max_words": MAX_WORDS[case.get("depth", "normal")]})
    if case.get("level") == "beginner":
        out += [{"beginner_no_jargon": True}, {"beginner_explains_moves": True}]
    return out


def run_checks(case: dict[str, Any], r: CoachResponse) -> list[CheckResult]:
    answer = r.answer
    verdicts = [c.result.get("verdict") for c in r.claims]
    results: list[CheckResult] = []

    for check in default_checks(case) + list(case.get("checks", [])):
        (kind, arg), = check.items()
        if kind == "no_refuted":
            bad = verdicts.count("refuted")
            ok = bad == 0 and r.tier != "fallback"
            results.append(CheckResult("no refuted claim, no fallback", "chess", ok, f"tier={r.tier}, refuted={bad}"))
        elif kind == "min_supported":
            n = verdicts.count("supported")
            results.append(CheckResult(f"at least {arg} verified claim(s)", "chess", n >= arg, f"{n} supported of {len(verdicts)}"))
        elif kind == "mentions_any":
            hit = [w for w in arg if _mentions(answer, w)]
            results.append(CheckResult(f"mentions one of {arg}", "chess", bool(hit), f"found {hit}" if hit else "none found"))
        elif kind == "mentions_all":
            miss = [w for w in arg if not _mentions(answer, w)]
            results.append(CheckResult(f"mentions all of {arg}", "chess", not miss, f"missing {miss}" if miss else ""))
        elif kind == "not_mentions":
            hit = [w for w in arg if _mentions(answer, w)]
            results.append(CheckResult(f"does not say {arg}", "task", not hit, f"said {hit}" if hit else ""))
        elif kind == "claim_checked":
            ok = any(arg.lower() in c.checked.lower() and c.result.get("verdict") == "supported" for c in r.claims)
            results.append(CheckResult(f"a verified claim about '{arg}'", "chess", ok, "; ".join(c.checked for c in r.claims)[:200]))
        elif kind == "tool_used":
            ok = arg in r.tools_called
            results.append(CheckResult(f"used {arg}", "task", ok, f"called: {r.tools_called}"))
        elif kind == "mate_line":
            side, lo, hi = arg["side"], arg["lo"], arg["hi"]
            found = [
                _side_moves(l, side) for l in r.lines
                if l.steps[-1].state == "checkmate" and l.steps[-1].winner == side
            ]
            ok = any(lo <= n <= hi for n in found)
            results.append(CheckResult(f"verified mate by {side} in {lo}-{hi} moves", "task", ok,
                                       f"mating lines with {found} {side} moves" if found else f"{len(r.lines)} line(s), none mates"))
        elif kind == "playable_line":
            side, n = arg["side"], arg["moves"]
            best = max((_side_moves(l, side) for l in r.lines), default=0)
            results.append(CheckResult(f"playable line with {n}+ {side} moves", "task", best >= n, f"longest has {best}"))
        elif kind == "max_words":
            words = len(answer.split())
            results.append(CheckResult(f"at most {arg} words", "level", words <= arg, f"{words} words"))
        elif kind == "beginner_no_jargon":
            hit = sorted({m.group(0) for m in JARGON.finditer(answer)})
            results.append(CheckResult("no unexplained jargon for a beginner", "level", not hit, f"found {hit}" if hit else ""))
        elif kind == "beginner_explains_moves":
            moves = PIECE_MOVE.findall(answer)
            ok = not moves or GLOSSED_MOVE.search(answer) is not None
            results.append(CheckResult("moves explained in words for a beginner", "level", ok,
                                       "" if ok else f"{len(moves)} piece move(s), none explained like 'Nf3 (knight to f3)'"))
        else:
            raise ValueError(f"unknown check {kind!r} in case {case['id']}")
    return results


def category_scores(results: list[CheckResult]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for cat in CATEGORIES:
        mine = [r for r in results if r.category == cat]
        out[cat] = sum(r.passed for r in mine) / len(mine) if mine else None
    return out
