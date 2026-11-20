"""Regenerate examples/*.json from the reference implementation and Stockfish.

Usage:
    STOCKFISH_PATH=/path/to/stockfish python tools/generate_examples.py

Each example is one request/response pair. The mock server serves them and the
contract tests validate them, so regenerate after any change to the spec.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import chessref as ref  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent.parent / "examples"

NIMZO = ["d2d4", "g8f6", "c2c4", "e7e6", "b1c3", "f8b4"]
BG4_PIN = ["e2e4", "e7e5", "g1f3", "d7d6", "d2d4", "c8g4"]
SCHOLAR = ["e2e4", "e7e5", "f1c4", "b8c6", "d1h5", "g8f6"]
ITALIAN = ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6"]
REPEAT = ["g1f3", "g8f6", "f3g1", "f6g8"] * 2
STALEMATE_FEN = "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"
XRAY_FEN = "3qk3/8/8/8/3B4/8/8/3RK3 w - - 0 1"
LIMITS = {"depth": 16, "multipv": 3}

PGN = """[Event "Think64 contract example"]
[White "Student"]
[Black "Opponent"]
[Result "1-0"]

1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6? (3... g6 {defends f7 and attacks the queen} 4. Qf3) 4. Qxf7# 1-0
"""


def pos(moves=None, fen=None):
    out = {"moves": list(moves or [])}
    if fen:
        out["start_fen"] = fen
    return out


def scenarios():
    """(name, endpoint, description, request, handler) — handler gets (request, engine)."""
    R = lambda f: (lambda req, eng: f(req))  # noqa: E731  rules-only handler
    E = lambda f: (lambda req, eng: f(req, eng))  # noqa: E731
    return [
        ("health", "GET /v1/health", "Service status.", None,
         lambda req, eng: {"schema_version": ref.SCHEMA_VERSION, "status": "ok", "engine": eng.info}),
        ("start-position", "POST /v1/position", "The initial position: 20 legal moves, equal material, no facts.",
         {"position": pos()}, R(ref.describe)),
        ("start-play-e4", "POST /v1/move", "Playing 1.e4 returns the new PositionRef to send next.",
         {"position": pos(), "move": "e2e4"}, R(ref.play)),
        ("start-play-san", "POST /v1/move", "The same move sent in SAN, as an LLM might write it.",
         {"position": pos(), "move": "e4", "notation": "san"}, R(ref.play)),
        ("start-analyze", "POST /v1/analyze", "Top 3 engine moves from the initial position.",
         {"position": pos(), "limits": LIMITS}, E(ref.analyze)),
        ("absolute-pin-position", "POST /v1/position",
         "Nimzo-Indian: Bb4 pins Nc3 to the king. With include.pieces the knight shows geometric attacks but no legal moves.",
         {"position": pos(NIMZO), "include": {"pieces": True}}, R(ref.describe)),
        ("absolute-pin-illegal-move", "POST /v1/move",
         "Moving the pinned knight is illegal; the response carries the pin that explains why.",
         {"position": pos(NIMZO), "move": "c3e4"}, R(ref.play)),
        ("relative-pin-position", "POST /v1/position",
         "Bg4 pins Nf3 to the queen: a relative pin, so knight moves stay legal.",
         {"position": pos(BG4_PIN)}, R(ref.describe)),
        ("xray-position", "POST /v1/position",
         "Rd1 x-rays the black queen through its own bishop; the queen also pins that bishop to the rook.",
         {"position": pos(fen=XRAY_FEN)}, R(ref.describe)),
        ("mate-in-one-analyze", "POST /v1/analyze", "Scholar's mate set-up: the engine reports mate in 1 (score type mate).",
         {"position": pos(SCHOLAR), "limits": LIMITS}, E(ref.analyze)),
        ("checkmate-move", "POST /v1/move", "Qxf7# ends the game: status.state checkmate, winner white.",
         {"position": pos(SCHOLAR), "move": "h5f7"}, R(ref.play)),
        ("checkmate-position", "POST /v1/position", "After mate: no legal moves, game over.",
         {"position": pos(SCHOLAR + ["h5f7"])}, R(ref.describe)),
        ("checkmate-analyze", "POST /v1/analyze", "Analysis of a finished game returns no candidates.",
         {"position": pos(SCHOLAR + ["h5f7"]), "limits": LIMITS}, E(ref.analyze)),
        ("stalemate-position", "POST /v1/position", "Black to move has no legal moves and is not in check.",
         {"position": pos(fen=STALEMATE_FEN)}, R(ref.describe)),
        ("threefold-with-history", "POST /v1/position",
         "Knights out and back twice: with the move history the threefold claim is detected.",
         {"position": pos(REPEAT)}, R(ref.describe)),
        ("threefold-fen-only", "POST /v1/position",
         "The same board sent as a bare FEN: no history, so no repetition can be seen. This is why PositionRef carries moves.",
         {"position": pos(fen=ref.build_board(pos(REPEAT)).fen())}, R(ref.describe)),
        ("unparseable-move", "POST /v1/move", "Garbage input is a 200 with reason unparseable_move, not an HTTP error.",
         {"position": pos(), "move": "Zz9", "notation": "san"}, R(ref.play)),
        ("compare-italian", "POST /v1/compare",
         "Compare Ng5 (attacks f7), d3 (quiet) and Bxf7+ (gives up the bishop) against the engine's best move.",
         {"position": pos(ITALIAN), "moves": ["f3g5", "d2d3", "c4f7"], "limits": LIMITS}, E(ref.compare)),
        ("verify-pin-claims", "POST /v1/verify",
         "Claims an LLM might make about the Nimzo position, some true and some false.",
         {"position": pos(NIMZO), "claims": [
             {"id": "c1", "type": "pinned", "square": "c3", "absolute": True},
             {"id": "c2", "type": "legal_move", "move": "c3e4"},
             {"id": "c3", "type": "attacks", "from": "b4", "to": "c3"},
             {"id": "c4", "type": "piece_on", "square": "b4", "piece_type": "knight", "color": "black"},
             {"id": "c5", "type": "hanging", "square": "c3"},
             {"id": "c6", "type": "in_check", "color": "white"}]}, E(ref.verify)),
        ("verify-mate-claims", "POST /v1/verify", "Engine-backed claims in the Scholar's mate position.",
         {"position": pos(SCHOLAR), "limits": {"depth": 16}, "claims": [
             {"id": "m1", "type": "mate_in", "moves": 1, "winner": "white"},
             {"id": "m2", "type": "best_move", "move": "h5f7"},
             {"id": "m3", "type": "better_than", "move": "d2d3", "than": "h5f7"},
             {"id": "m4", "type": "legal_line", "moves": ["h5f7", "e8e7"]}]}, E(ref.verify)),
        ("verify-structural-claims", "POST /v1/verify",
         "v0.2 structural claims after 4. a3 Bxc3+ 5. bxc3 in the Nimzo: material, files, bishop pair, pawn structure. Rules-only.",
         {"position": pos(NIMZO + ["a2a3", "b4c3", "b2c3"]), "claims": [
             {"id": "s1", "type": "material_balance", "balance_cp": 0},
             {"id": "s2", "type": "open_file", "file": "b", "open_for": "white"},
             {"id": "s3", "type": "bishop_pair", "color": "white"},
             {"id": "s4", "type": "bishop_pair", "color": "black"},
             {"id": "s5", "type": "doubled_pawns", "color": "white", "file": "c"},
             {"id": "s6", "type": "isolated_pawn", "square": "a3"},
             {"id": "s7", "type": "passed_pawn", "square": "d4"},
             {"id": "s8", "type": "open_file", "file": "e", "open_for": None}]}, E(ref.verify)),
        ("game-with-variation", "POST /v1/game",
         "A PGN with a side variation and a comment, parsed into a move tree with a PositionRef per node.",
         {"pgn": PGN}, R(ref.game)),
    ]


ERRORS = [
    ("error-invalid-fen", "POST /v1/position", "A FEN that cannot be parsed.",
     {"position": {"start_fen": "not a fen", "moves": []}}),
    ("error-illegal-history", "POST /v1/analyze", "The third move in the history is illegal.",
     {"position": {"moves": ["e2e4", "e7e5", "e4e5"]}}),
    ("error-invalid-pgn", "POST /v1/game", "A PGN with an illegal move.",
     {"pgn": "1. e4 e5 2. Ke3 Ke6 3. Qxh8 *"}),
]


def main():
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    eng = ref.Engine()
    try:
        items = scenarios()
        for i, (name, endpoint, desc, req, handler) in enumerate(items, start=1):
            body = handler(req, eng)
            write(i, name, endpoint, desc, req, 200, body)
        for j, (name, endpoint, desc, req) in enumerate(ERRORS, start=len(items) + 1):
            try:
                handler = {"POST /v1/position": ref.describe, "POST /v1/game": ref.game,
                           "POST /v1/analyze": lambda r: ref.analyze(r, eng)}[endpoint]
                handler(req)
                raise SystemExit(f"{name}: expected an error")
            except ref.ContractError as exc:
                write(j, name, endpoint, desc, req, exc.status, exc.body())
    finally:
        eng.close()


def write(i, name, endpoint, desc, req, status, body):
    method, path = endpoint.split()
    doc = {"name": name, "method": method, "path": path, "description": desc,
           "request": req, "status": status, "response": body}
    path_ = OUT / f"{i:02d}-{name}.json"
    path_.write_text(json.dumps(doc, indent=2) + "\n")
    print("wrote", path_.name)


if __name__ == "__main__":
    main()
