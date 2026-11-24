"""Grade one answer against a puzzle's known solution with a neutral rules referee (python-chess),
independent of both the coach and the model being tested.

The answer must end with a line "FINAL: <moves in SAN>", starting with the solver's move.
- solved:     every solver move matches the solution (a different move that mates also counts, as on Lichess)
- first_move: the first move matches (or mates)
- illegal:    a move in the FINAL line is not legal in the position the line has reached
- fake_mate:  the line marks a move as mate (#) that is not checkmate (or is not even legal)
"""
from __future__ import annotations

import re
from typing import Any

import chess

FINAL = re.compile(r"FINAL\s*:\s*(.+)", re.IGNORECASE)
MOVE_NO = re.compile(r"^\d+\.(\.\.)?|^\.\.\.")
TRIM = "!?,;.()[]*`'\""


def final_line(text: str) -> str | None:
    found = FINAL.findall(text or "")
    return found[-1].strip() if found else None


def tokens(line: str) -> list[str]:
    out = []
    for raw in line.replace("…", "...").split():
        tok = MOVE_NO.sub("", raw).strip(TRIM)
        tok = tok.replace("0-0-0", "O-O-O").replace("0-0", "O-O")
        if tok and not re.fullmatch(r"\d+\.*|1-0|0-1|1/2-1/2", tok):
            out.append(tok)
    return out


def parse(board: chess.Board, toks: list[str]) -> tuple[list[chess.Move], bool, bool]:
    """Play the tokens; returns (legal moves played, illegal?, fake mate?)."""
    b = board.copy()
    moves: list[chess.Move] = []
    fake_mate = False
    for tok in toks:
        try:
            m = b.parse_san(tok)
        except ValueError:
            try:
                m = chess.Move.from_uci(tok.lower())
                if m not in b.legal_moves:
                    raise ValueError
            except ValueError:
                return moves, True, fake_mate or "#" in tok
        b.push(m)
        moves.append(m)
        if "#" in tok and not b.is_checkmate():
            fake_mate = True
    return moves, False, fake_mate


def grade(puzzle: dict[str, Any], answer: str) -> dict[str, Any]:
    board = chess.Board(puzzle["fen"])
    line = final_line(answer)
    result: dict[str, Any] = {"final": line, "answered": bool(line), "solved": False, "first_move": False,
                              "illegal": False, "fake_mate": False, "played": []}
    if not line:
        return result
    moves, illegal, fake_mate = parse(board, tokens(line))
    result.update(illegal=illegal, fake_mate=fake_mate, played=[m.uci() for m in moves])

    solution = [chess.Move.from_uci(u) for u in puzzle["solution"]]
    b = board.copy()
    solved = True
    for k, sol in enumerate(solution):
        if k % 2 == 0:  # solver's move
            if k >= len(moves):
                solved = False
                break
            mv = moves[k]
            if mv != sol:
                after = b.copy()
                after.push(mv)
                mated = after.is_checkmate()
                if k == 0:
                    result["first_move"] = mated
                solved = mated
                break
            if k == 0:
                result["first_move"] = True
        else:  # opponent's reply: the answer must expect the solution's defence
            if k < len(moves) and moves[k] != sol:
                solved = False
                break
        b.push(sol)
    result["solved"] = solved and result["first_move"]
    return result
