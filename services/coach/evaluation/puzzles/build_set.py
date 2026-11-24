"""Pick a balanced, reproducible puzzle set from the Lichess puzzle database (CC0).

    curl -sL https://database.lichess.org/lichess_db_puzzle.csv.zst | zstd -dc | head -n 300001 > head.csv
    python -m evaluation.puzzles.build_set head.csv              # writes evaluation/puzzles/puzzles.json

Lichess format: FEN is the position *before* the opponent's move; Moves[0] is that move and the
rest is the solution, starting with the solver's move. Only well-tested puzzles are kept (many
plays, stable rating, liked by players), split evenly across rating bands and mate / non-mate.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

import chess

HERE = Path(__file__).resolve().parent
BANDS = [(600, 1200), (1200, 1600), (1600, 2000), (2000, 2600)]
MAX_SOLVER_MOVES = 3


def band_of(rating: int) -> str | None:
    for lo, hi in BANDS:
        if lo <= rating < hi:
            return f"{lo}-{hi}"
    return None


def to_puzzle(row: dict[str, str]) -> dict | None:
    moves = row["Moves"].split()
    solution = moves[1:]
    if not solution or (len(solution) + 1) // 2 > MAX_SOLVER_MOVES:
        return None
    board = chess.Board(row["FEN"])
    first = chess.Move.from_uci(moves[0])
    last_san = board.san(first)
    board.push(first)
    side = "white" if board.turn == chess.WHITE else "black"
    sans = []
    b = board.copy()
    for u in solution:
        m = chess.Move.from_uci(u)
        sans.append(b.san(m))
        b.push(m)
    themes = row["Themes"].split()
    return {
        "id": row["PuzzleId"],
        "fen": board.fen(),            # the puzzle position: solver to move
        "side": side,
        "last_move": {"uci": moves[0], "san": last_san},
        "source_fen": row["FEN"],      # Lichess's FEN, before the opponent's move
        "solution": solution,          # UCI, solver's move first
        "solution_san": sans,
        "rating": int(row["Rating"]),
        "band": band_of(int(row["Rating"])),
        "kind": "mate" if "mate" in themes else "other",
        "themes": themes,
        "url": f"https://lichess.org/training/{row['PuzzleId']}",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", type=Path)
    ap.add_argument("--per-cell", type=int, default=13, help="puzzles per rating band per kind (mate / other)")
    ap.add_argument("--seed", type=int, default=64)
    ap.add_argument("--out", type=Path, default=HERE / "puzzles.json")
    args = ap.parse_args(argv)

    cells: dict[tuple[str, str], list[dict]] = {}
    with args.csv.open() as f:
        for row in csv.DictReader(f):
            if int(row["NbPlays"]) < 1000 or int(row["RatingDeviation"]) > 80 or int(row["Popularity"]) < 85:
                continue
            if not band_of(int(row["Rating"])):
                continue
            p = to_puzzle(row)
            if p:
                cells.setdefault((p["band"], p["kind"]), []).append(p)

    rng = random.Random(args.seed)
    chosen: list[dict] = []
    for lo, hi in BANDS:
        for kind in ("mate", "other"):
            pool = sorted(cells.get((f"{lo}-{hi}", kind), []), key=lambda p: p["id"])
            if len(pool) < args.per_cell:
                raise SystemExit(f"only {len(pool)} puzzles for {lo}-{hi} {kind}; use a bigger CSV")
            chosen += rng.sample(pool, args.per_cell)
    rng.shuffle(chosen)
    meta = {"source": "Lichess puzzle database (CC0), database.lichess.org", "seed": args.seed,
            "filters": "NbPlays>=1000, RatingDeviation<=80, Popularity>=85, <=3 solver moves",
            "count": len(chosen)}
    args.out.write_text(json.dumps({"meta": meta, "puzzles": chosen}, indent=1))
    print(f"wrote {len(chosen)} puzzles to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
