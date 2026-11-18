"""Player memory: profile, level/depth in the prompt, sessions, mistakes from rules-engine facts."""
from __future__ import annotations

from fastapi.testclient import TestClient

from coach.app import create_app
from coach.memory import PlayerMemory, detect_patterns
from .conftest import QueueLLM, answer
from .test_coach import settings

P = "p_test-player"
BA6 = {"moves": ["e2e4", "e7e5", "f1a6"]}  # 2.Ba6?? - the bishop hangs to bxa6 / Nxa6
BG5 = {"moves": ["d2d4", "e7e5", "c1g5"]}  # 2.Bg5?? - the bishop hangs to Qxg5


class Coach:
    """One coach app with one shared in-memory player database."""

    def __init__(self, url: str, llm=None):
        self.memory = PlayerMemory(":memory:")
        self.llm = llm or QueueLLM([answer("ok")] * 10)
        self.client = TestClient(create_app(settings(url), llm=self.llm, memory=self.memory))
        self.client.__enter__()

    def ask(self, question="Hi", position=None, last_move=None, player_id=P, **extra):
        body = {"question": question, "position": position or {"moves": []}, "player_id": player_id, **extra}
        if last_move:
            body["last_move"] = last_move
        r = self.client.post("/v1/coach/ask", json=body)
        assert r.status_code == 200, r.text
        return r.json()

    def profile(self, player_id=P):
        return self.client.get(f"/v1/players/{player_id}").json()

    def close(self):
        self.client.__exit__(None, None, None)


def test_new_player_defaults(chess_api_url):
    c = Coach(chess_api_url)
    p = c.profile()
    assert (p["level"], p["level_source"], p["explanation_depth"], p["rating"]) == ("intermediate", "default", "normal", None)
    assert p["recurring_mistakes"] == [] and p["stats"]["questions"] == 0
    c.close()


def test_rating_sets_level_and_a_chosen_level_wins(chess_api_url):
    c = Coach(chess_api_url)
    p = c.client.patch(f"/v1/players/{P}", json={"rating": 950}).json()
    assert (p["level"], p["level_source"]) == ("beginner", "rating")
    p = c.client.patch(f"/v1/players/{P}", json={"level": "advanced"}).json()
    assert (p["level"], p["level_source"], p["rating"]) == ("advanced", "chosen", 950)
    p = c.client.patch(f"/v1/players/{P}", json={"level": None}).json()
    assert (p["level"], p["level_source"]) == ("beginner", "rating")
    assert c.client.patch(f"/v1/players/{P}", json={"level": "master"}).status_code == 422
    assert c.client.patch(f"/v1/players/{P}", json={"mood": "happy"}).status_code == 422
    c.close()


def test_level_and_depth_reach_the_prompt_and_engine_limits(chess_api_url):
    llm = QueueLLM([answer("ok")], tool_calls=[("analyze_position", {"multipv": 2})])
    c = Coach(chess_api_url, llm)
    c.client.patch(f"/v1/players/{P}", json={"rating": 900, "explanation_depth": "short"})
    body = c.ask("What's the best move?")
    assert (body["level"], body["explanation_depth"]) == ("beginner", "short")
    system = llm.calls[0]["system"]
    assert "The player is a beginner" in system and "prefers short answers" in system
    assert "knight to f3" in system  # beginners get notation explained
    c.close()


def test_sessions_are_recorded_and_earlier_questions_reach_the_context(chess_api_url):
    c = Coach(chess_api_url)
    c.ask("How can White win in 4 moves?", session_id="s1")
    c.ask("What about Black?", session_id="s1")
    c.ask("Explain the Italian", session_id="s2")
    p = c.profile()
    assert (p["stats"]["questions"], p["stats"]["sessions"]) == (3, 2)
    sessions = c.client.get(f"/v1/players/{P}/sessions").json()["sessions"]
    assert [s["session_id"] for s in sessions] == ["s2", "s1"]
    assert sessions[1]["topics"] == ["How can White win in 4 moves?", "What about Black?"]
    context = c.llm.calls[-1]["messages"][-1]["content"]
    assert "About this player (player memory)" in context
    assert '"How can White win in 4 moves?"' in context  # from the earlier session, not this one
    c.close()


def test_anonymous_players_are_not_remembered(chess_api_url):
    c = Coach(chess_api_url)
    body = c.ask(player_id="p_anonymous")
    assert body["level"] == "intermediate"
    assert c.profile("p_anonymous")["stats"]["questions"] == 0
    assert "player memory" not in c.llm.calls[0]["messages"][-1]["content"]
    c.close()


def test_bad_player_id_is_rejected(chess_api_url):
    c = Coach(chess_api_url)
    assert c.client.get("/v1/players/robert'); DROP TABLE players;--").status_code in (404, 422)
    assert c.client.get("/v1/players/nope").status_code == 422
    c.close()


def test_hanging_piece_mistakes_are_recorded_once_per_move_and_become_recurring(chess_api_url):
    llm = QueueLLM([answer("ok")] * 4, tool_calls=[("review_last_move", {})])
    c = Coach(chess_api_url, llm)
    ba6 = {"uci": "f1a6", "san": "Ba6"}
    c.ask("What was wrong with my last move?", BA6, ba6)
    assert "the bishop on a6 could be taken for free" in llm.tool_results[0]["patterns_from_rules_engine"][0]
    c.ask("Why was that bad?", BA6, ba6)  # same move again: still one mistake
    m = c.profile()["recurring_mistakes"]
    assert [(x["theme"], x["count"]) for x in m] == [("left_piece_hanging", 1)]

    c.ask("What was wrong with my last move?", BG5, {"uci": "c1g5", "san": "Bg5"})
    m = c.profile()["recurring_mistakes"]
    assert [(x["theme"], x["count"]) for x in m] == [("left_piece_hanging", 2)]
    assert m[0]["last_example"]["move"] == "Bg5"

    c.ask("Anything else?", session_id="later")
    assert "left a piece undefended where it could be taken (2 times)" in llm.calls[-1]["messages"][-1]["content"]
    c.close()


def test_missed_free_piece(chess_api_url):
    llm = QueueLLM([answer("ok")], tool_calls=[("review_last_move", {})])
    c = Coach(chess_api_url, llm)
    c.ask("Was Nf6 good?", {"moves": ["e2e4", "e7e5", "f1a6", "g8f6"]}, {"uci": "g8f6", "san": "Nf6"})
    m = c.profile()["recurring_mistakes"]
    assert [x["theme"] for x in m] == ["missed_free_piece"]
    assert "the undefended bishop on a6 could be taken" in m[0]["last_example"]["detail"]
    c.close()


def test_with_a_real_engine_only_moves_it_rates_as_mistakes_count(chess_api_url):
    """The mock's compare reports 0 loss; with a 'real' engine that means no mistake is stored."""
    llm = QueueLLM([answer("ok")], tool_calls=[("review_last_move", {})])
    c = Coach(chess_api_url, llm)
    c.client.app.state.agent._engine_real = True
    c.ask("What was wrong with my last move?", BA6, {"uci": "f1a6", "san": "Ba6"})
    assert c.profile()["recurring_mistakes"] == []
    c.close()


def test_forget_deletes_everything(chess_api_url):
    llm = QueueLLM([answer("ok")], tool_calls=[("review_last_move", {})])
    c = Coach(chess_api_url, llm)
    c.client.patch(f"/v1/players/{P}", json={"rating": 2000})
    c.ask("What was wrong?", BA6, {"uci": "f1a6", "san": "Ba6"})
    assert c.client.delete(f"/v1/players/{P}").status_code == 204
    p = c.profile()
    assert (p["rating"], p["stats"]["questions"], p["recurring_mistakes"]) == (None, 0, [])
    c.close()


# ---------------------------------------------------------------- detect_patterns edge cases


def _pos(facts, pieces=(), in_check=False):
    return {"facts": facts, "pieces": [{"piece": p} for p in pieces], "status": {"in_check": in_check}}


def _hanging(sq, type_, color):
    return {"kind": "hanging", "piece": {"square": sq, "type": type_, "color": color}, "attackers": [{"square": "a1", "type": "rook", "color": "x"}]}


def test_even_trade_is_not_a_hanging_piece():
    before = _pos([], [{"square": "e5", "type": "knight", "color": "black"}])
    after = _pos([_hanging("e5", "knight", "white")])
    assert detect_patterns(before, after, "white", {"uci": "f3e5", "san": "Nxe5"}) == []


def test_hanging_piece_after_giving_check_is_not_counted():
    after = _pos([_hanging("a6", "bishop", "white")], in_check=True)
    assert detect_patterns(_pos([]), after, "white", {"uci": "f1a6", "san": "Ba6+"}) == []


def test_pawns_are_ignored():
    after = _pos([_hanging("e4", "pawn", "white")])
    assert detect_patterns(_pos([]), after, "white", {"uci": "e2e4", "san": "e4"}) == []
