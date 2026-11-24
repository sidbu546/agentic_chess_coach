"""Puzzle comparison harness: the grader, the puzzle set, the board image and the statistics."""
import json
from pathlib import Path

from evaluation.puzzles.board_image import render
from evaluation.puzzles.grade import grade
from evaluation.puzzles.run import mcnemar_p, wilson

PUZZLES = json.loads((Path(__file__).resolve().parents[1] / "evaluation" / "puzzles" / "puzzles.json").read_text())["puzzles"]

# Black to move after Kg3; solution Rh3+ gxh3 Qf3+ Kh2 Qxh3#
P = next(p for p in PUZZLES if p["id"] == "1fx8b")


def g(answer: str) -> dict:
    return grade(P, answer)


def test_exact_solution_with_move_numbers_and_chatter():
    r = g("Rook sac first.\nFINAL: 28...Rh3+ 29.gxh3 Qf3+ 30.Kh2 Qxh3#")
    assert r["solved"] and r["first_move"] and not r["illegal"] and not r["fake_mate"]


def test_last_final_line_counts():
    assert g("FINAL: Qf3+\nOn second thought:\nFINAL: Rh3+ gxh3 Qf3+ Kh2 Qxh3#")["solved"]


def test_first_move_only_is_partial():
    r = g("FINAL: Rh3+")
    assert r["first_move"] and not r["solved"]


def test_wrong_first_move():
    r = g("FINAL: Qf3+ gxf3")
    assert not r["first_move"] and not r["solved"]


def test_illegal_move_and_fake_mate():
    assert g("FINAL: Rh3+ Kg2")["illegal"]                        # g2 is occupied by a pawn
    r = g("FINAL: Rh3+ gxh3 Qf3+ Kh2 Qf2#")
    assert r["fake_mate"] and not r["solved"]                       # Qf2 is legal but not mate


def test_no_final_line_is_unanswered():
    r = g("Rh3+ wins")
    assert not r["answered"] and not r["solved"]


def test_alternative_mate_counts():
    # mate-in-1 puzzle where any mating move is accepted
    p = {"fen": "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "solution": ["a1a8"]}
    assert grade(p, "FINAL: Ra8#")["solved"]
    p2 = {"fen": "6k1/5ppp/8/8/8/8/5PPP/RR4K1 w - - 0 1", "solution": ["a1a8"]}
    assert grade(p2, "FINAL: Rb8#")["solved"]


def test_every_stored_solution_grades_as_solved():
    assert len(PUZZLES) == 104 and len({p["id"] for p in PUZZLES}) == 104
    for p in PUZZLES:
        assert grade(p, "FINAL: " + " ".join(p["solution_san"]))["solved"], p["id"]


def test_board_image_is_png():
    png = render(P["fen"], white_bottom=False, last_move=P["last_move"]["uci"])
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 5000


def test_statistics():
    assert mcnemar_p(0, 0) == 1.0
    assert mcnemar_p(10, 10) == 1.0
    assert mcnemar_p(20, 5) < 0.01
    lo, hi = wilson(50, 100)
    assert 0.39 < lo < 0.41 and 0.59 < hi < 0.61
