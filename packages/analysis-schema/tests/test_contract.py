"""Contract tests. Both sides run the same file.

    pytest tests/                                            # checks the spec and every example
    CONTRACT_BASE_URL=http://localhost:8064 pytest tests/    # also checks a running server

Person 1 points CONTRACT_BASE_URL at the real chess truth service.
Person 2 can point it at the mock to confirm the mock matches the spec.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

import chess
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import schema as contract  # noqa: E402

EXAMPLES = [json.loads(p.read_text()) for p in sorted((ROOT / "examples").glob("*.json"))]
IDS = [e["name"] for e in EXAMPLES]
BASE = os.environ.get("CONTRACT_BASE_URL", "").rstrip("/")
RULES_PATHS = {"/v1/position", "/v1/move", "/v1/game"}


# ------------------------------------------------------------------ helpers

def board_for(ref: dict) -> chess.Board:
    b = chess.Board(ref.get("start_fen", chess.STARTING_FEN))
    for m in ref.get("moves", []):
        b.push_uci(m)
    return b


def assert_valid(schema_name: str, instance):
    problems = contract.errors(schema_name, instance)
    assert not problems, f"{schema_name} violations:\n  " + "\n  ".join(problems)


def assert_line_legal(board: chess.Board, moves: list[dict]):
    b = board.copy()
    for m in moves:
        mv = chess.Move.from_uci(m["uci"])
        assert mv in b.legal_moves, f"{m['uci']} illegal in {b.fen()}"
        assert b.san(mv) == m["san"], f"SAN mismatch for {m['uci']}: {m['san']} vs {b.san(mv)}"
        b.push(mv)


def check_semantics(example: dict, body: dict):
    """Invariants that hold for any correct implementation, not just the reference one."""
    req, path = example["request"], example["path"]
    if example["status"] != 200:
        return
    if path != "/v1/move" and "position" in body and req and "position" in req:
        board = board_for(req["position"])
        assert body["position"]["fen"] == board.fen()
        assert body["position"]["ply"] == len(req["position"].get("moves", []))
    if path == "/v1/position":
        board = board_for(req["position"])
        ucis = [m["uci"] for m in body["legal_moves"]]
        if req.get("include", {}).get("legal_moves", True):
            assert ucis == sorted({m.uci() for m in board.legal_moves}), "legal_moves wrong or unsorted"
            for m in body["legal_moves"]:
                assert board.san(chess.Move.from_uci(m["uci"])) == m["san"], f"bad SAN for {m['uci']}"
    if path == "/v1/move" and body["legal"]:
        assert body["next"]["moves"] == req["position"].get("moves", []) + [body["move"]["uci"]]
        assert body["position"]["fen"] == board_for(body["next"]).fen()
        assert body["reason"] is None
    if path == "/v1/move" and not body["legal"]:
        assert body["next"] is None and body["position"] is None and body["reason"] is not None
    if path == "/v1/analyze":
        board = board_for(req["position"])
        cands = body["analysis"]["candidates"]
        assert [c["rank"] for c in cands] == list(range(1, len(cands) + 1))
        for c in cands:
            assert c["pv"][0] == c["move"], "pv must start with the candidate move"
            assert_line_legal(board, c["pv"])
        if board.is_game_over():
            assert cands == []
    if path == "/v1/compare":
        board = board_for(req["position"])
        assert [l["move"]["uci"] for l in body["lines"]] == req["moves"], "lines must follow request order"
        assert_line_legal(board, body["best"]["pv"])
        for line in body["lines"]:
            assert line["pv"][0] == line["move"]
            assert_line_legal(board, line["pv"])
            if line["is_best"]:
                assert line["loss_cp"] == 0
    if path == "/v1/verify":
        assert [r["id"] for r in body["results"]] == [c["id"] for c in req["claims"]]
    if path == "/v1/game":
        ids = {n["id"] for n in body["nodes"]}
        for n in body["nodes"]:
            assert n["parent_id"] is None or n["parent_id"] in ids
            assert set(n["children"]) <= ids
            assert board_for(n["position"]).fen() == n["fen_after"]
        assert all(i in ids for i in body["mainline"])


# ------------------------------------------------------------------ the spec and the examples

def test_every_schema_compiles():
    for name in contract.SPEC["components"]["schemas"]:
        contract.validator(name).check_schema(contract.validator(name).schema)
        contract.errors(name, {})  # forces every $ref to resolve


def test_every_endpoint_has_examples():
    covered = {(e["method"], e["path"]) for e in EXAMPLES}
    missing = set(contract.ENDPOINTS) - covered
    assert not missing, f"endpoints without examples: {missing}"


@pytest.mark.parametrize("example", EXAMPLES, ids=IDS)
def test_example_matches_schema(example):
    req_schema, resp_schema = contract.ENDPOINTS[(example["method"], example["path"])]
    if req_schema:
        assert_valid(req_schema, example["request"])
    assert_valid(resp_schema if example["status"] == 200 else "ErrorResponse", example["response"])


@pytest.mark.parametrize("example", EXAMPLES, ids=IDS)
def test_example_semantics(example):
    check_semantics(example, example["response"])


# ------------------------------------------------------------------ a live server

def call(method: str, path: str, body):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def same_unordered(a: list, b: list) -> bool:
    key = lambda x: json.dumps(x, sort_keys=True)  # noqa: E731
    return sorted(map(key, a)) == sorted(map(key, b))


live = pytest.mark.skipif(not BASE, reason="set CONTRACT_BASE_URL to test a running server")


@live
@pytest.mark.parametrize("example", EXAMPLES, ids=IDS)
def test_live_server(example):
    status, body = call(example["method"], example["path"], example["request"])
    assert status == example["status"], f"HTTP {status}: {body}"
    _, resp_schema = contract.ENDPOINTS[(example["method"], example["path"])]
    assert_valid(resp_schema if status == 200 else "ErrorResponse", body)
    if status != 200:
        assert body["error"]["code"] == example["response"]["error"]["code"]
        return
    check_semantics(example, body)
    expected = example["response"]
    if example["path"] in RULES_PATHS:
        # rules output is deterministic: it must match the example (facts in any order)
        exp, got = dict(expected), dict(body)
        if "facts" in exp:
            assert same_unordered(got.pop("facts"), exp.pop("facts")), "facts differ from the example"
        assert got == exp
    if example["path"] == "/v1/verify":
        # verdicts are objective even when engine depth differs
        verdicts = [(r["id"], r["verdict"]) for r in body["results"]]
        assert verdicts == [(r["id"], r["verdict"]) for r in expected["results"]]
    if example["name"] == "mate-in-one-analyze" and body["analysis"]["engine"]["name"] != "mock":
        top = body["analysis"]["candidates"][0]
        assert top["move"]["uci"] == "h5f7" and top["score"] == {"type": "mate", "value": 1, "pov": "white"}


@live
def test_live_rejects_malformed_request():
    status, body = call("POST", "/v1/analyze", {"position": {"moves": ["not-a-move"]}})
    assert status == 422
    assert_valid("ErrorResponse", body)
