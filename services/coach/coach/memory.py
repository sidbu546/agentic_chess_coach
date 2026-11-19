"""Player memory: rating, level, preferred explanation depth, recurring mistakes and past sessions.

Stored in SQLite (one file, `COACH_DB_PATH`). Everything here is about the *player*; nothing here
decides chess truth. Mistakes are recorded only from patterns the rules engine reported
(`detect_patterns`) or from a real engine's loss, never from the LLM.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

LEVELS = ("beginner", "intermediate", "advanced")
DEPTHS = ("short", "normal", "detailed")
DEFAULT_LEVEL = "intermediate"
DEFAULT_DEPTH = "normal"
ANONYMOUS = "p_anonymous"

# theme -> how the coach and the UI describe it
THEMES = {
    "left_piece_hanging": "left a piece undefended where it could be taken",
    "missed_free_piece": "missed a chance to take an undefended piece",
    "walked_into_pin": "let a piece get pinned",
    "engine_mistake": "played a move the engine rates as a mistake",
    # opening habits (from the moves and squares, no engine needed)
    "knight_on_rim": "moved a knight to the edge of the board in the opening",
    "early_queen": "brought the queen out in the first three moves",
    "slow_development": "still had two or more knights or bishops at home on move 10",
}
HOME_MINORS = {
    "white": {("b1", "knight"), ("g1", "knight"), ("c1", "bishop"), ("f1", "bishop")},
    "black": {("b8", "knight"), ("g8", "knight"), ("c8", "bishop"), ("f8", "bishop")},
}
VALUE = {"pawn": 1, "knight": 3, "bishop": 3, "rook": 5, "queen": 9, "king": 100}


def level_for_rating(rating: int | None) -> str | None:
    if rating is None:
        return None
    if rating < 1200:
        return "beginner"
    if rating < 1800:
        return "intermediate"
    return "advanced"


SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    player_id TEXT PRIMARY KEY,
    rating INTEGER,
    level TEXT,
    explanation_depth TEXT NOT NULL DEFAULT 'normal',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    ts REAL NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    fen TEXT NOT NULL,
    tier TEXT NOT NULL,
    cost_usd REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS interactions_player ON interactions (player_id, ts);
CREATE TABLE IF NOT EXISTS mistakes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id TEXT NOT NULL,
    theme TEXT NOT NULL,
    ts REAL NOT NULL,
    fen TEXT NOT NULL,          -- position before the move
    move_san TEXT NOT NULL,
    color TEXT NOT NULL,        -- side that played the move
    detail TEXT NOT NULL,
    UNIQUE (player_id, theme, fen, move_san)   -- asking about the same move twice counts once
);
CREATE INDEX IF NOT EXISTS mistakes_player ON mistakes (player_id, theme);
"""


class PlayerMemory:
    def __init__(self, path: str | Path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    def _q(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            cur = self._db.execute(sql, args)
            rows = cur.fetchall()
            self._db.commit()
            return rows

    # ------------------------------------------------------------------ profile

    def profile(self, player_id: str) -> dict[str, Any]:
        row = self._q("SELECT * FROM players WHERE player_id = ?", (player_id,))
        p = dict(row[0]) if row else {"player_id": player_id, "rating": None, "level": None, "explanation_depth": DEFAULT_DEPTH}
        from_rating = level_for_rating(p["rating"])
        level, source = (p["level"], "chosen") if p["level"] else (from_rating, "rating") if from_rating else (DEFAULT_LEVEL, "default")
        stats = self._q(
            "SELECT COUNT(*) AS questions, COUNT(DISTINCT session_id) AS sessions, MIN(ts) AS first_seen, MAX(ts) AS last_seen "
            "FROM interactions WHERE player_id = ?",
            (player_id,),
        )[0]
        return {
            "player_id": player_id,
            "rating": p["rating"],
            "level": level,
            "level_source": source,
            "explanation_depth": p["explanation_depth"],
            "recurring_mistakes": self.mistakes(player_id),
            "stats": dict(stats),
        }

    def update(self, player_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        """Set rating / level / explanation_depth. A key present with None clears it."""
        now = time.time()
        self._q(
            "INSERT INTO players (player_id, explanation_depth, created_at, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(player_id) DO NOTHING",
            (player_id, DEFAULT_DEPTH, now, now),
        )
        for key in ("rating", "level", "explanation_depth"):
            if key in changes:
                value = changes[key] if changes[key] is not None or key != "explanation_depth" else DEFAULT_DEPTH
                self._q(f"UPDATE players SET {key} = ?, updated_at = ? WHERE player_id = ?", (value, now, player_id))
        return self.profile(player_id)

    def forget(self, player_id: str) -> None:
        for table in ("players", "interactions", "mistakes"):
            self._q(f"DELETE FROM {table} WHERE player_id = ?", (player_id,))

    # ------------------------------------------------------------------ mistakes

    def record_mistakes(self, player_id: str, fen: str, move_san: str, color: str, patterns: list[dict[str, str]]) -> None:
        for p in patterns:
            self._q(
                "INSERT OR IGNORE INTO mistakes (player_id, theme, ts, fen, move_san, color, detail) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (player_id, p["theme"], time.time(), fen, move_san, color, p["detail"]),
            )

    def mistakes(self, player_id: str, limit: int = 5) -> list[dict[str, Any]]:
        rows = self._q(
            "SELECT theme, COUNT(*) AS count, MAX(ts) AS last_seen FROM mistakes WHERE player_id = ? "
            "GROUP BY theme ORDER BY count DESC, last_seen DESC LIMIT ?",
            (player_id, limit),
        )
        out = []
        for r in rows:
            ex = self._q(
                "SELECT move_san, detail FROM mistakes WHERE player_id = ? AND theme = ? ORDER BY ts DESC LIMIT 1",
                (player_id, r["theme"]),
            )[0]
            out.append({
                "theme": r["theme"],
                "label": THEMES.get(r["theme"], r["theme"]),
                "count": r["count"],
                "last_seen": r["last_seen"],
                "last_example": {"move": ex["move_san"], "detail": ex["detail"]},
            })
        return out

    # ------------------------------------------------------------------ sessions

    def record_interaction(self, player_id: str, session_id: str, question: str, answer: str, fen: str, tier: str, cost_usd: float) -> None:
        self._q(
            "INSERT INTO interactions (player_id, session_id, ts, question, answer, fen, tier, cost_usd) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (player_id, session_id, time.time(), question[:1000], answer[:2000], fen, tier, cost_usd),
        )

    def sessions(self, player_id: str, limit: int = 10) -> list[dict[str, Any]]:
        rows = self._q(
            "SELECT session_id, MIN(ts) AS started, MAX(ts) AS ended, COUNT(*) AS questions, SUM(cost_usd) AS cost_usd "
            "FROM interactions WHERE player_id = ? GROUP BY session_id ORDER BY ended DESC LIMIT ?",
            (player_id, limit),
        )
        out = []
        for r in rows:
            qs = self._q(
                "SELECT question FROM interactions WHERE player_id = ? AND session_id = ? ORDER BY ts LIMIT 5",
                (player_id, r["session_id"]),
            )
            out.append({**dict(r), "cost_usd": round(r["cost_usd"] or 0, 4), "topics": [q["question"] for q in qs]})
        return out

    # ------------------------------------------------------------------ for the LLM

    def context(self, profile: dict[str, Any], current_session: str | None) -> str:
        """Short block for the coach's context. Only what helps pitch the explanation."""
        lines = [f"- Level: {profile['level']}" + (f" (rating {profile['rating']})" if profile["rating"] else "")]
        lines.append(f"- Prefers {profile['explanation_depth']} explanations")
        found = profile["recurring_mistakes"]
        if found:
            lines.append(
                "- Mistake patterns found in their reviewed moves so far (all games): "
                + "; ".join(f"{m['label']} ({m['count']} times, last: {m['last_example']['detail']})" for m in found[:5])
            )
        earlier = [s for s in self.sessions(profile["player_id"], limit=4) if s["session_id"] != current_session][:3]
        if earlier:
            topics = [t for s in earlier for t in s["topics"][:2]][:4]
            lines.append(f"- {profile['stats']['sessions']} session(s) so far; earlier questions: " + " | ".join(f'"{t[:80]}"' for t in topics))
        return "About this player (player memory):\n" + "\n".join(lines)


# ---------------------------------------------------------------------- mistake patterns


def detect_patterns(before: dict[str, Any], after: dict[str, Any], mover: str, move: dict[str, str]) -> list[dict[str, str]]:
    """Mistake patterns in one move, from the rules engine's facts before and after it.

    `before`/`after` are /v1/position responses (with pieces), `move` is {uci, san}. Pawns are left
    out: a pawn left hanging is often a gambit, a free pawn often poisoned.
    """
    opp = "black" if mover == "white" else "white"
    to_sq = move["uci"][2:4]
    pieces_before = {e["piece"]["square"]: e["piece"] for e in before.get("pieces") or []}
    opp_after = {e["piece"]["square"] for e in after.get("pieces") or [] if e["piece"]["color"] == opp}
    captured = pieces_before.get(to_sq)
    out: list[dict[str, str]] = []

    def hanging(pos: dict[str, Any], color: str) -> dict[str, dict[str, Any]]:
        return {
            f["piece"]["square"]: f["piece"]
            for f in pos["facts"]
            if f["kind"] == "hanging" and f["piece"]["color"] == color and f["piece"]["type"] not in ("pawn", "king")
        }

    gives_check = after["status"]["in_check"]
    if not gives_check:  # after a check the opponent can't just take
        for sq, p in hanging(after, mover).items():
            if sq == to_sq and captured and VALUE[captured["type"]] >= VALUE[p["type"]]:
                continue  # an even or winning trade, e.g. NxN with the knight now attacked
            out.append({"theme": "left_piece_hanging", "detail": f"after {move['san']} the {p['type']} on {sq} could be taken for free"})

    if not before["status"]["in_check"]:  # out of check, the move was forced
        for sq, p in hanging(before, opp).items():
            if sq != to_sq and sq in opp_after:
                out.append({"theme": "missed_free_piece", "detail": f"instead of {move['san']}, the undefended {p['type']} on {sq} could be taken"})

    pinned_before = {f["pinned"]["square"] for f in before["facts"] if f["kind"] == "pin" and f["pinned"]["color"] == mover}
    for f in after["facts"]:
        if (
            f["kind"] == "pin"
            and f["pinned"]["color"] == mover
            and f["pinned"]["square"] not in pinned_before
            and (f["pinned"]["type"] != "pawn" or f["absolute"])  # a pawn shielding a piece is noise
        ):
            p = f["pinned"]
            out.append({
                "theme": "walked_into_pin",
                "detail": f"after {move['san']} the {p['type']} on {p['square']} is pinned to the {f['shielded']['type']} by the {f['pinner']['type']} on {f['pinner']['square']}",
            })
    # one entry per theme per move
    seen: set[str] = set()
    return [p for p in out if not (p["theme"] in seen or seen.add(p["theme"]))]


def opening_habits(before: dict[str, Any], mover: str, move: dict[str, str]) -> list[dict[str, str]]:
    """Habits visible from one move: knight to the rim, early queen, slow development (at move 10)."""
    full = int(before["position"]["fen"].split()[5])
    san, to_sq = move["san"], move["uci"][2:4]
    label = f"{full}{'.' if mover == 'white' else '...'} {san}"
    out = []
    if san.startswith("N") and to_sq[0] in "ah" and full <= 10:
        out.append({"theme": "knight_on_rim", "detail": f"{label} put the knight on the edge, where it controls fewer squares"})
    if san.startswith("Q") and full <= 3:
        out.append({"theme": "early_queen", "detail": f"{label} brought the queen out on move {full}"})
    if full == 10:
        home = {(e["piece"]["square"], e["piece"]["type"]) for e in before.get("pieces") or [] if e["piece"]["color"] == mover}
        left = sorted(sq for sq, t in HOME_MINORS[mover] & home)
        if len(left) >= 2:
            out.append({"theme": "slow_development", "detail": f"on move 10 the pieces on {', '.join(left)} had not moved yet"})
    return out
