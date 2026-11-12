"""Reference implementation of the contract, used to produce the example fixtures.

It is built on python-chess (rules) and Stockfish (engine). Its job is to make the
examples *correct*, not to be the production service: Person 1 may start from it,
reshape it, or replace it, as long as the contract tests still pass.
"""
from __future__ import annotations

import io
import os
import time

import chess
import chess.engine
import chess.pgn

SCHEMA_VERSION = "0.2.0"
STARTPOS = chess.STARTING_FEN
DEFAULT_DEPTH = 16

COLOR = {chess.WHITE: "white", chess.BLACK: "black"}
PTYPE = {chess.KING: "king", chess.QUEEN: "queen", chess.ROOK: "rook",
         chess.BISHOP: "bishop", chess.KNIGHT: "knight", chess.PAWN: "pawn"}
VALUE = {chess.PAWN: 100, chess.KNIGHT: 300, chess.BISHOP: 300,
         chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}
MATE_CP = 10000


class ContractError(Exception):
    """Maps to an ErrorResponse."""

    def __init__(self, code: str, message: str, status: int = 422, details: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.status, self.details = code, message, status, details

    def body(self) -> dict:
        err = {"code": self.code, "message": self.message}
        if self.details:
            err["details"] = self.details
        return {"error": err}


# ---------------------------------------------------------------- positions

def build_board(ref: dict) -> chess.Board:
    start = ref.get("start_fen", STARTPOS)
    try:
        board = chess.Board(start)
    except ValueError as exc:
        raise ContractError("invalid_fen", f"Invalid start_fen: {exc}")
    if not board.is_valid():
        raise ContractError("invalid_fen", f"start_fen is not a legal chess position ({board.status()!r})")
    for i, uci in enumerate(ref.get("moves", [])):
        try:
            mv = chess.Move.from_uci(uci)
        except ValueError:
            mv = None
        if mv is None or mv not in board.legal_moves:
            raise ContractError("illegal_move_in_history", f"Move {i + 1} ({uci}) is not legal in its position",
                                details={"index": i, "move": uci})
        board.push(mv)
    return board


def ref_of(board: chess.Board) -> dict:
    root = board.root()
    return {"start_fen": root.fen(), "moves": [m.uci() for m in board.move_stack]}


def position(board: chess.Board) -> dict:
    return {"fen": board.fen(), "side_to_move": COLOR[board.turn],
            "fullmove_number": board.fullmove_number, "halfmove_clock": board.halfmove_clock,
            "ply": len(board.move_stack)}


def status(board: chess.Board) -> dict:
    out = board.outcome(claim_draw=False)
    state = "ongoing"
    if out is not None:
        state = {chess.Termination.CHECKMATE: "checkmate", chess.Termination.STALEMATE: "stalemate",
                 chess.Termination.INSUFFICIENT_MATERIAL: "insufficient_material",
                 chess.Termination.FIVEFOLD_REPETITION: "fivefold_repetition",
                 chess.Termination.SEVENTYFIVE_MOVES: "seventyfive_moves"}.get(out.termination, "ongoing")
    claimable = []
    if out is None:
        if board.can_claim_threefold_repetition():
            claimable.append("threefold_repetition")
        if board.can_claim_fifty_moves():
            claimable.append("fifty_moves")
    return {"state": state, "is_game_over": out is not None, "in_check": board.is_check(),
            "winner": COLOR[out.winner] if out is not None and out.winner is not None else None,
            "claimable_draws": claimable}


def move_obj(board: chess.Board, mv: chess.Move) -> dict:
    return {"uci": mv.uci(), "san": board.san(mv)}


def legal_moves(board: chess.Board) -> list[dict]:
    return sorted((move_obj(board, m) for m in board.legal_moves), key=lambda m: m["uci"])


def material(board: chess.Board) -> dict:
    def count(color):
        return {PTYPE[p]: len(board.pieces(p, color))
                for p in (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)}
    bal = sum(VALUE[p] * (len(board.pieces(p, chess.WHITE)) - len(board.pieces(p, chess.BLACK)))
              for p in VALUE)
    return {"white": count(chess.WHITE), "black": count(chess.BLACK), "balance_cp": bal}


# ---------------------------------------------------------------- facts

def piece(board: chess.Board, sq: int) -> dict:
    p = board.piece_at(sq)
    return {"square": chess.square_name(sq), "type": PTYPE[p.piece_type], "color": COLOR[p.color]}


DIRS = {chess.ROOK: [(1, 0), (-1, 0), (0, 1), (0, -1)],
        chess.BISHOP: [(1, 1), (1, -1), (-1, 1), (-1, -1)]}
DIRS[chess.QUEEN] = DIRS[chess.ROOK] + DIRS[chess.BISHOP]


def _ray(sq: int, df: int, dr: int):
    f, r = chess.square_file(sq) + df, chess.square_rank(sq) + dr
    while 0 <= f < 8 and 0 <= r < 8:
        yield chess.square(f, r)
        f, r = f + df, r + dr


def _first_two(board, sq, df, dr):
    """First two occupied squares along a ray, plus the squares walked up to the second."""
    hits, walked = [], []
    for s in _ray(sq, df, dr):
        walked.append(s)
        if board.piece_at(s):
            hits.append(s)
            if len(hits) == 2:
                break
    return hits, walked


def pins(board: chess.Board) -> list[dict]:
    out = []
    for sq, p in board.piece_map().items():
        if p.piece_type not in DIRS:
            continue
        for df, dr in DIRS[p.piece_type]:
            hits, walked = _first_two(board, sq, df, dr)
            if len(hits) < 2:
                continue
            a, b = board.piece_at(hits[0]), board.piece_at(hits[1])
            if a.color == p.color or b.color != a.color or a.piece_type == chess.KING:
                continue
            absolute = b.piece_type == chess.KING
            if not absolute and VALUE[b.piece_type] <= VALUE[a.piece_type]:
                continue
            out.append({"kind": "pin", "pinned": piece(board, hits[0]), "pinner": piece(board, sq),
                        "shielded": piece(board, hits[1]), "absolute": absolute,
                        "ray": [chess.square_name(sq)] + [chess.square_name(s) for s in walked]})
    return out


def xrays(board: chess.Board) -> list[dict]:
    out = []
    for sq, p in board.piece_map().items():
        if p.piece_type not in DIRS:
            continue
        for df, dr in DIRS[p.piece_type]:
            hits, _ = _first_two(board, sq, df, dr)
            if len(hits) < 2:
                continue
            a, b = board.piece_at(hits[0]), board.piece_at(hits[1])
            if a.color == p.color and b.color != p.color and b.piece_type != chess.PAWN:
                out.append({"kind": "xray", "attacker": piece(board, sq), "blocker": piece(board, hits[0]),
                            "target": piece(board, hits[1])})
    return out


def _real_attackers(board: chess.Board, color: bool, sq: int) -> list[int]:
    """Attackers of `sq` by `color`, minus absolutely pinned pieces that cannot capture along their pin."""
    return [a for a in board.attackers(color, sq)
            if not board.is_pinned(color, a) or sq in board.pin(color, a)]


def hanging(board: chess.Board) -> list[dict]:
    out = []
    for sq, p in board.piece_map().items():
        if p.piece_type == chess.KING:
            continue
        attackers = _real_attackers(board, not p.color, sq)
        if attackers and not _real_attackers(board, p.color, sq):
            out.append({"kind": "hanging", "piece": piece(board, sq),
                        "attackers": [piece(board, a) for a in sorted(attackers)]})
    return out


def files(board: chess.Board) -> list[dict]:
    out = []
    for f in range(8):
        mask = chess.BB_FILES[f]
        w = bool(board.pieces_mask(chess.PAWN, chess.WHITE) & mask)
        b = bool(board.pieces_mask(chess.PAWN, chess.BLACK) & mask)
        name = chess.FILE_NAMES[f]
        if not w and not b:
            out.append({"kind": "open_file", "file": name})
        elif w != b:
            out.append({"kind": "semi_open_file", "file": name, "open_for": "black" if w else "white"})
    return out


def facts(board: chess.Board) -> list[dict]:
    out = []
    king = board.king(board.turn)
    for c in sorted(board.checkers()):
        out.append({"kind": "check", "checker": piece(board, c), "king": piece(board, king)})
    return out + pins(board) + xrays(board) + hanging(board) + files(board)


def pieces(board: chess.Board) -> list[dict]:
    pin_by_sq = {f["pinned"]["square"]: f for f in pins(board)}
    out = []
    for sq in sorted(board.piece_map()):
        p = board.piece_at(sq)
        pin = pin_by_sq.get(chess.square_name(sq))
        out.append({
            "piece": piece(board, sq),
            "attacks": [chess.square_name(s) for s in sorted(board.attacks(sq))],
            "legal_moves": sorted((move_obj(board, m) for m in board.legal_moves if m.from_square == sq),
                                  key=lambda m: m["uci"]),
            "attacked_by": [piece(board, a) for a in sorted(board.attackers(not p.color, sq))],
            "defended_by": [piece(board, a) for a in sorted(board.attackers(p.color, sq))],
            "pin": None if pin is None else {"pinner": pin["pinner"], "shielded": pin["shielded"],
                                             "absolute": pin["absolute"]},
        })
    return out


# ---------------------------------------------------------------- rules endpoints

def describe(req: dict) -> dict:
    board = build_board(req["position"])
    inc = {"legal_moves": True, "facts": True, "pieces": False, **req.get("include", {})}
    out = {"schema_version": SCHEMA_VERSION, "position": position(board), "status": status(board),
           "legal_moves": legal_moves(board) if inc["legal_moves"] else [],
           "material": material(board), "facts": facts(board) if inc["facts"] else []}
    if inc["pieces"]:
        out["pieces"] = pieces(board)
    return out


def play(req: dict) -> dict:
    board = build_board(req["position"])
    raw, notation = req["move"], req.get("notation", "uci")
    illegal = {"schema_version": SCHEMA_VERSION, "legal": False, "move": None, "next": None,
               "position": None, "status": None}
    if board.is_game_over():
        return {**illegal, "reason": {"code": "game_over", "message": "The game is already over."}}
    try:
        mv = board.parse_san(raw) if notation == "san" else chess.Move.from_uci(raw)
    except ValueError:
        if notation == "san":
            # parse_san raises for both garbage and illegal SAN; tell them apart
            code = "illegal_move" if _looks_like_san(raw) else "unparseable_move"
            return {**illegal, "reason": {"code": code, "message": f"{raw!r} is not a legal move here."}}
        return {**illegal, "reason": {"code": "unparseable_move", "message": f"{raw!r} is not valid UCI."}}
    if mv not in board.legal_moves:
        reason = {"code": "illegal_move", "message": f"{raw} is not legal in this position."}
        why = [f for f in pins(board) if f["absolute"] and f["pinned"]["square"] == chess.square_name(mv.from_square)]
        if board.is_check():
            why += [f for f in facts(board) if f["kind"] == "check"]
        if why:
            reason["facts"] = why
        return {**illegal, "reason": reason}
    m = move_obj(board, mv)
    board.push(mv)
    return {"schema_version": SCHEMA_VERSION, "legal": True, "move": m, "next": ref_of(board),
            "position": position(board), "status": status(board), "reason": None}


def _looks_like_san(s: str) -> bool:
    import re
    return bool(re.fullmatch(r"(O-O(-O)?|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](=[QRBN])?)[+#]?", s))


def game(req: dict) -> dict:
    pgn = chess.pgn.read_game(io.StringIO(req["pgn"]))
    if pgn is None or pgn.errors:
        msg = str(pgn.errors[0]) if pgn is not None and pgn.errors else "No game found in PGN."
        raise ContractError("invalid_pgn", msg)
    nodes, counter = [], [0]

    def walk(node, parent_id, mainline):
        for i, child in enumerate(node.variations):
            counter[0] += 1
            nid = f"n{counter[0]}"
            entry = {"id": nid, "parent_id": parent_id, "ply": child.ply(),
                     "move": move_obj(node.board(), child.move), "fen_after": child.board().fen(),
                     "position": ref_of(child.board()), "is_mainline": mainline and i == 0,
                     "children": [], "comment": child.comment or None, "nags": sorted(child.nags)}
            nodes.append(entry)
            if parent_id is not None:
                next(n for n in nodes if n["id"] == parent_id)["children"].append(nid)
            walk(child, nid, mainline and i == 0)

    walk(pgn, None, True)
    mainline = [n["id"] for n in nodes if n["is_mainline"]]
    return {"schema_version": SCHEMA_VERSION, "headers": dict(pgn.headers), "start_fen": pgn.board().fen(),
            "result": pgn.headers.get("Result", "*") if pgn.headers.get("Result") in ("1-0", "0-1", "1/2-1/2") else "*",
            "nodes": nodes, "mainline": mainline}


# ---------------------------------------------------------------- engine

class Engine:
    def __init__(self, path: str | None = None):
        self.path = path or os.environ.get("STOCKFISH_PATH", "stockfish")
        self.sf = chess.engine.SimpleEngine.popen_uci(self.path)
        self.sf.configure({"Threads": 1, "Hash": 64})
        name = self.sf.id.get("name", "Stockfish")
        parts = name.split()
        self.info = {"name": parts[0], "version": " ".join(parts[1:]) or "unknown"}

    def close(self):
        self.sf.quit()

    @staticmethod
    def limit(limits: dict | None) -> chess.engine.Limit:
        limits = limits or {}
        kw = {}
        if "depth" in limits:
            kw["depth"] = limits["depth"]
        if "movetime_ms" in limits:
            kw["time"] = limits["movetime_ms"] / 1000
        if "nodes" in limits:
            kw["nodes"] = limits["nodes"]
        return chess.engine.Limit(**(kw or {"depth": DEFAULT_DEPTH}))

    def search(self, board: chess.Board, limits: dict | None, multipv: int):
        t0 = time.monotonic()
        infos = self.sf.analyse(board, self.limit(limits), multipv=multipv, game=object())
        return infos, int((time.monotonic() - t0) * 1000)


def score(pov_score: chess.engine.PovScore) -> dict:
    w = pov_score.white()
    if w.is_mate():
        return {"type": "mate", "value": w.mate(), "pov": "white"}
    return {"type": "cp", "value": w.score(), "pov": "white"}


def mover_cp(s: dict, mover: bool) -> int:
    if s["type"] == "mate":
        v = MATE_CP if s["value"] > 0 else -MATE_CP
    else:
        v = s["value"]
    return v if mover == chess.WHITE else -v


def pv_moves(board: chess.Board, moves) -> list[dict]:
    b, out = board.copy(), []
    for mv in moves:
        out.append(move_obj(b, mv))
        b.push(mv)
    return out


def candidates(board, infos) -> list[dict]:
    out = []
    for rank, info in enumerate(infos, start=1):
        if "pv" not in info or not info["pv"]:
            continue
        pv = pv_moves(board, info["pv"])
        out.append({"rank": rank, "move": pv[0], "score": score(info["score"]), "pv": pv,
                    "depth": info.get("depth", 1)})
    return out


def analyze(req: dict, eng: Engine) -> dict:
    board = build_board(req["position"])
    limits = req.get("limits") or {}
    multipv = limits.get("multipv", 3)
    base = {"schema_version": SCHEMA_VERSION, "position": position(board), "status": status(board)}
    if board.is_game_over():
        return {**base, "analysis": {"engine": eng.info, "depth": 0, "nodes": 0, "time_ms": 0,
                                     "multipv": multipv, "candidates": []}}
    infos, ms = eng.search(board, limits, multipv)
    return {**base, "analysis": {"engine": eng.info, "depth": max(i.get("depth", 0) for i in infos),
                                 "nodes": max(i.get("nodes", 0) for i in infos), "time_ms": ms,
                                 "multipv": multipv, "candidates": candidates(board, infos)}}


def _fact_key(f):
    import json
    return json.dumps(f, sort_keys=True)


def line_differences(board: chess.Board, pv: list[chess.Move], s: dict) -> list[dict]:
    diffs = []
    after = board.copy()
    after.push(pv[0])
    before_f = {_fact_key(f): f for f in facts(board)}
    after_f = {_fact_key(f): f for f in facts(after)}
    for k in sorted(after_f.keys() - before_f.keys()):
        diffs.append({"kind": "fact_created", "at_ply": 1, "fact": after_f[k]})
    for k in sorted(before_f.keys() - after_f.keys()):
        diffs.append({"kind": "fact_removed", "at_ply": 1, "fact": before_f[k]})
    end = board.copy()
    for mv in pv:
        end.push(mv)
    b0, b1 = material(board)["balance_cp"], material(end)["balance_cp"]
    if b0 != b1:
        diffs.append({"kind": "material", "balance_cp_before": b0, "balance_cp_after": b1,
                      "after_plies": len(pv)})
    if s["type"] == "mate":
        diffs.append({"kind": "mate", "in_moves": abs(s["value"]),
                      "winner": "white" if s["value"] > 0 else "black"})
    return diffs


def compare(req: dict, eng: Engine) -> dict:
    board = build_board(req["position"])
    if board.is_game_over():
        raise ContractError("invalid_request", "Cannot compare moves: the game is over.")
    limits = req.get("limits") or {}
    for uci in req["moves"]:
        if chess.Move.from_uci(uci) not in board.legal_moves:
            raise ContractError("invalid_request", f"{uci} is not legal here; use /v1/move to check legality first.",
                                details={"move": uci})
    infos, _ = eng.search(board, limits, 1)
    best = candidates(board, infos)[0]
    best_cp = mover_cp(best["score"], board.turn)
    lines = []
    for uci in req["moves"]:
        mv = chess.Move.from_uci(uci)
        after = board.copy()
        after.push(mv)
        if uci == best["move"]["uci"]:
            # reuse the root search so the best move's line and score match `best` exactly
            pv = [chess.Move.from_uci(m["uci"]) for m in best["pv"]]
            s = best["score"]
        elif after.is_game_over():
            pv = [mv]
            # the move itself ends the game: mate in 1 from the root, or a dead draw
            s = ({"type": "mate", "value": 1 if board.turn == chess.WHITE else -1, "pov": "white"}
                 if after.is_checkmate() else {"type": "cp", "value": 0, "pov": "white"})
        else:
            sub, _ = eng.search(after, limits, 1)
            pv = [mv] + list(sub[0].get("pv", []))
            s = score(sub[0]["score"])
        line_cp = mover_cp(s, board.turn)
        is_best = uci == best["move"]["uci"]
        lines.append({"move": move_obj(board, mv), "score": s, "pv": pv_moves(board, pv),
                      "loss_cp": 0 if is_best else max(0, best_cp - line_cp), "is_best": is_best,
                      "differences": line_differences(board, pv, s)})
    return {"schema_version": SCHEMA_VERSION, "position": position(board), "best": best, "lines": lines}


def verify(req: dict, eng: Engine | None) -> dict:
    board = build_board(req["position"])
    limits = req.get("limits") or {}
    results = []
    for c in req["claims"]:
        results.append({"id": c["id"], **_verify_one(board, c, eng, limits)})
    return {"schema_version": SCHEMA_VERSION, "results": results}


def _verdict(ok: bool, reason: str, facts_=None) -> dict:
    out = {"verdict": "supported" if ok else "refuted", "reason": reason}
    if facts_:
        out["facts"] = facts_
    return out


def _verify_one(board, c, eng, limits) -> dict:
    t = c["type"]
    sq = lambda name: chess.parse_square(name)  # noqa: E731
    if t == "legal_move":
        mv = chess.Move.from_uci(c["move"])
        ok = mv in board.legal_moves
        why = [] if ok else [f for f in pins(board) if f["absolute"] and f["pinned"]["square"] == chess.square_name(mv.from_square)]
        return _verdict(ok, f"{c['move']} is {'' if ok else 'not '}legal", why)
    if t == "legal_line":
        b = board.copy()
        for i, u in enumerate(c["moves"]):
            mv = chess.Move.from_uci(u)
            if mv not in b.legal_moves:
                return _verdict(False, f"move {i + 1} ({u}) is illegal")
            b.push(mv)
        return _verdict(True, f"all {len(c['moves'])} moves are legal")
    if t == "piece_on":
        p = board.piece_at(sq(c["square"]))
        ok = p is not None and PTYPE[p.piece_type] == c["piece_type"] and COLOR[p.color] == c["color"]
        actual = "empty" if p is None else f"{COLOR[p.color]} {PTYPE[p.piece_type]}"
        return _verdict(ok, f"{c['square']} holds: {actual}")
    if t in ("attacks", "defends"):
        f, to = sq(c["from"]), sq(c["to"])
        p, q = board.piece_at(f), board.piece_at(to)
        if p is None:
            return _verdict(False, f"no piece on {c['from']}")
        hits = to in board.attacks(f)
        if t == "defends":
            ok = hits and q is not None and q.color == p.color
            return _verdict(ok, f"{c['from']} {'defends' if ok else 'does not defend'} {c['to']}")
        return _verdict(hits, f"{c['from']} {'attacks' if hits else 'does not attack'} {c['to']}")
    if t == "pinned":
        found = [f for f in pins(board) if f["pinned"]["square"] == c["square"]]
        if "absolute" in c:
            found = [f for f in found if f["absolute"] == c["absolute"]]
        return _verdict(bool(found), f"{c['square']} is {'' if found else 'not '}pinned", found)
    if t == "hanging":
        found = [f for f in hanging(board) if f["piece"]["square"] == c["square"]]
        return _verdict(bool(found), f"{c['square']} is {'' if found else 'not '}hanging", found)
    if t == "in_check":
        color = chess.WHITE if c["color"] == "white" else chess.BLACK
        ok = board.turn == color and board.is_check()
        return _verdict(ok, f"{c['color']} is {'' if ok else 'not '}in check")
    structural = _verify_structural(board, c)
    if structural is not None:
        return structural
    # engine-backed claims
    if eng is None:
        return {"verdict": "unverifiable", "reason": "engine unavailable"}
    if t == "mate_in":
        infos, _ = eng.search(board, limits or {"depth": 20}, 1)
        s = score(infos[0]["score"])
        want = 1 if c["winner"] == "white" else -1
        ok = s["type"] == "mate" and s["value"] * want > 0 and abs(s["value"]) <= c["moves"]
        return _verdict(ok, f"engine score: {s['type']} {s['value']}")
    if t in ("best_move", "better_than"):
        def eval_after(u):
            b = board.copy()
            b.push(chess.Move.from_uci(u))
            if b.is_checkmate():
                return MATE_CP
            sub, _ = eng.search(b, limits, 1)
            return mover_cp(score(sub[0]["score"]), board.turn)
        for u in [c["move"]] + ([c["than"]] if t == "better_than" else []):
            if chess.Move.from_uci(u) not in board.legal_moves:
                return _verdict(False, f"{u} is not legal")
        if t == "better_than":
            a, b = eval_after(c["move"]), eval_after(c["than"])
            return _verdict(a > b, f"{c['move']}: {a} cp, {c['than']}: {b} cp (mover's view)")
        infos, _ = eng.search(board, limits, 1)
        best_cp = mover_cp(score(infos[0]["score"]), board.turn)
        mine = eval_after(c["move"])
        tol = c.get("tolerance_cp", 30)
        return _verdict(best_cp - mine <= tol, f"best {best_cp} cp, {c['move']} {mine} cp (mover's view)")
    return {"verdict": "unverifiable", "reason": f"unknown claim type {t}"}


# ---------------------------------------------------------------- structural claims (v0.2, rules-only)

def _pawn_files(board: chess.Board, color: bool) -> list[int]:
    return [chess.square_file(s) for s in board.pieces(chess.PAWN, color)]


def _verify_structural(board: chess.Board, c: dict) -> dict | None:
    """Claims about material and pawn structure. Returns None for other claim types."""
    t = c["type"]
    if t == "material_balance":
        bal = material(board)["balance_cp"]
        return _verdict(bal == c["balance_cp"], f"material balance is {bal} cp (White minus Black)")
    if t == "open_file":
        f = chess.FILE_NAMES.index(c["file"])
        w = f in _pawn_files(board, chess.WHITE)
        b = f in _pawn_files(board, chess.BLACK)
        if c["open_for"] is None:
            ok, what = not w and not b, "open"
        else:
            mine, theirs = (w, b) if c["open_for"] == "white" else (b, w)
            ok, what = not mine and theirs, f"semi-open for {c['open_for']}"
        pawns = ", ".join(n for n, has in (("white", w), ("black", b)) if has) or "no"
        return _verdict(ok, f"{c['file']}-file is {'' if ok else 'not '}{what} ({pawns} pawns on it)")
    if t == "bishop_pair":
        color = chess.WHITE if c["color"] == "white" else chess.BLACK
        bishops = board.pieces(chess.BISHOP, color)
        light = bool(bishops & chess.BB_LIGHT_SQUARES)
        dark = bool(bishops & chess.BB_DARK_SQUARES)
        ok = light and dark
        return _verdict(ok, f"{c['color']} has {'' if ok else 'not got '}the bishop pair ({len(bishops)} bishop(s))")
    if t == "doubled_pawns":
        color = chess.WHITE if c["color"] == "white" else chess.BLACK
        n = _pawn_files(board, color).count(chess.FILE_NAMES.index(c["file"]))
        return _verdict(n >= 2, f"{c['color']} has {n} pawn(s) on the {c['file']}-file")
    if t in ("isolated_pawn", "passed_pawn"):
        sq = chess.parse_square(c["square"])
        p = board.piece_at(sq)
        if p is None or p.piece_type != chess.PAWN:
            return _verdict(False, f"no pawn on {c['square']}")
        f, r = chess.square_file(sq), chess.square_rank(sq)
        near = {f - 1, f + 1} & set(range(8))
        if t == "isolated_pawn":
            ok = not (near & set(_pawn_files(board, p.color)))
            return _verdict(ok, f"{c['square']} is {'' if ok else 'not '}isolated")
        ahead = (lambda rr: rr > r) if p.color == chess.WHITE else (lambda rr: rr < r)
        blockers = [chess.square_name(s) for s in board.pieces(chess.PAWN, not p.color)
                    if chess.square_file(s) in near | {f} and ahead(chess.square_rank(s))]
        ok = not blockers
        return _verdict(ok, f"{c['square']} is {'' if ok else 'not '}passed" + ("" if ok else f" (stopped by {', '.join(blockers)})"))
    return None
