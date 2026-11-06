"""Mock chess truth service for Person 2 to build against.

    python mock/server.py            # http://localhost:8064
    python mock/server.py --port 9000

What it does
- Validates every request body against openapi.yaml and answers 422 if it does not
  match, so contract mistakes surface on day one.
- Rules endpoints (/v1/position, /v1/move, /v1/game) are computed live with
  python-chess, so any position works.
- Engine endpoints (/v1/analyze, /v1/compare, /v1/verify) return the matching
  example from examples/ when the request matches one (limits ignored). Otherwise
  they return clearly fake engine data (engine name "mock", every score 0), and
  engine-backed claims come back "unverifiable".
- Every response has an X-Mock-Source header: fixture, live or fake.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import chessref as ref  # noqa: E402

try:
    import schema as contract  # tools/schema.py: needs pyyaml + jsonschema
except ImportError:  # validation is optional; the mock still runs without it
    contract = None

MOCK_ENGINE = {"name": "mock", "version": ref.SCHEMA_VERSION}
REQUEST_SCHEMA = {"/v1/position": "PositionRequest", "/v1/move": "MoveRequest", "/v1/analyze": "AnalyzeRequest",
                  "/v1/compare": "CompareRequest", "/v1/verify": "VerifyRequest", "/v1/game": "GameRequest"}


def key(path: str, body: dict | None) -> str:
    body = dict(body or {})
    body.pop("limits", None)
    if "position" in body:
        p = dict(body["position"])
        if p.get("start_fen") in (None, ref.STARTPOS):
            p.pop("start_fen", None)
        p.setdefault("moves", [])
        body["position"] = p
    return path + " " + json.dumps(body, sort_keys=True)


FIXTURES = {}
for f in sorted((ROOT / "examples").glob("*.json")):
    ex = json.loads(f.read_text())
    if ex["status"] == 200 and ex["path"] in ("/v1/analyze", "/v1/compare", "/v1/verify"):
        FIXTURES[key(ex["path"], ex["request"])] = ex["response"]


# ---------------------------------------------------------------- fake engine data

def _fake_order(board):
    def rank(m):
        return (not board.is_capture(m), not board.gives_check(m), m.uci())
    return sorted(board.legal_moves, key=rank)


def fake_analyze(req):
    board = ref.build_board(req["position"])
    multipv = (req.get("limits") or {}).get("multipv", 3)
    cands = []
    if not board.is_game_over():
        for i, mv in enumerate(_fake_order(board)[:multipv], start=1):
            m = ref.move_obj(board, mv)
            cands.append({"rank": i, "move": m, "score": {"type": "cp", "value": 0, "pov": "white"},
                          "pv": [m], "depth": 1})
    return {"schema_version": ref.SCHEMA_VERSION, "position": ref.position(board), "status": ref.status(board),
            "analysis": {"engine": MOCK_ENGINE, "depth": 1, "nodes": 0, "time_ms": 0, "multipv": multipv,
                         "candidates": cands}}


def fake_compare(req):
    board = ref.build_board(req["position"])
    if board.is_game_over():
        raise ref.ContractError("invalid_request", "Cannot compare moves: the game is over.")
    for uci in req["moves"]:
        if ref.chess.Move.from_uci(uci) not in board.legal_moves:
            raise ref.ContractError("invalid_request", f"{uci} is not legal here", details={"move": uci})
    zero = {"type": "cp", "value": 0, "pov": "white"}
    first = ref.move_obj(board, _fake_order(board)[0])
    lines = []
    for uci in req["moves"]:
        m = ref.move_obj(board, ref.chess.Move.from_uci(uci))
        lines.append({"move": m, "score": zero, "pv": [m], "loss_cp": 0, "is_best": uci == first["uci"],
                      "differences": []})
    return {"schema_version": ref.SCHEMA_VERSION, "position": ref.position(board),
            "best": {"rank": 1, "move": first, "score": zero, "pv": [first], "depth": 1}, "lines": lines}


def fake_verify(req):
    return ref.verify(req, None)  # rules claims are real, engine claims come back unverifiable


# ---------------------------------------------------------------- routing

LIVE = {"/v1/position": ref.describe, "/v1/move": ref.play, "/v1/game": ref.game}
ENGINE = {"/v1/analyze": fake_analyze, "/v1/compare": fake_compare, "/v1/verify": fake_verify}


def handle(path: str, body: dict) -> tuple[int, dict, str]:
    if contract is not None and path in REQUEST_SCHEMA:
        problems = contract.errors(REQUEST_SCHEMA[path], body)
        if problems:
            return 422, {"error": {"code": "invalid_request", "message": problems[0],
                                   "details": {"problems": problems[:10]}}}, "live"
    try:
        if path in LIVE:
            return 200, LIVE[path](body), "live"
        if path in ENGINE:
            ref.build_board(body["position"])  # same errors as the real service for bad positions
            hit = FIXTURES.get(key(path, body))
            if hit is not None:
                return 200, hit, "fixture"
            return 200, ENGINE[path](body), "fake"
    except ref.ContractError as exc:
        return exc.status, exc.body(), "live"
    return 404, {"error": {"code": "invalid_request", "message": f"No endpoint {path}"}}, "live"


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body, source):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Expose-Headers", "X-Mock-Source")
        self.send_header("X-Mock-Source", source)
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):  # CORS preflight for the browser app
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/v1/health":
            return self._send(200, {"schema_version": ref.SCHEMA_VERSION, "status": "ok", "engine": MOCK_ENGINE}, "live")
        self._send(404, {"error": {"code": "invalid_request", "message": f"No endpoint {self.path}"}}, "live")

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send(400, {"error": {"code": "invalid_request", "message": "Body is not valid JSON"}}, "live")
        try:
            status, out, source = handle(self.path, body)
        except Exception as exc:  # never crash the dev server
            status, out, source = 500, {"error": {"code": "internal", "message": str(exc)}}, "live"
        self._send(status, out, source)

    def log_message(self, fmt, *args):
        sys.stderr.write("mock  %s\n" % (fmt % args))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8064)
    a = ap.parse_args()
    print(f"Think64 mock on http://{a.host}:{a.port}  ({len(FIXTURES)} engine fixtures, "
          f"request validation {'on' if contract is not None else 'off: pip install pyyaml jsonschema'})")
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
