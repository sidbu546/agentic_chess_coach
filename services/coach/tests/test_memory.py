"""Player memory: profile, level/depth in the prompt, sessions, mistakes from rules-engine facts."""
from __future__ import annotations

from fastapi.testclient import TestClient

from coach.app import create_app
from coach.memory import PlayerMemory, detect_patterns, material_given_away
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
    assert "left a piece undefended where it could be taken (2 times, last: after Bg5" in llm.calls[-1]["messages"][-1]["content"]
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


# ---------------------------------------------------------------- whole-game review, side, history labels

# 1.e4 e5 2.Na3 Qh4 3.Nc4 Qxe4+ - White's knight goes to the rim; Black's queen comes out on move 2.
GAME = {"moves": ["e2e4", "e7e5", "b1a3", "d8h4", "a3c4", "h4e4"]}


def test_game_moves_reach_the_context_in_san(chess_api_url):
    c = Coach(chess_api_url)
    c.ask("What happened?", GAME)
    context = c.llm.calls[0]["messages"][-1]["content"]
    assert "Game so far (6 plies, from the rules engine): 1. e4 e5 2. Na3 Qh4 3. Nc4 Qxe4+" in context
    c.close()


def test_review_game_finds_habits_for_the_players_side_only_and_saves_them(chess_api_url):
    llm = QueueLLM([answer("ok")], tool_calls=[("review_game", {})])
    c = Coach(chess_api_url, llm)
    c.ask("What mistakes do I keep making?", GAME, player_color="white")
    review = llm.tool_results[0]
    assert review["reviewed"] == "3 white moves"
    assert [f["move"] for f in review["findings"]] == ["2. Na3"]
    assert "put the knight on the edge" in review["findings"][0]["patterns"][0]
    assert all(f["by"] == "white" for f in review["findings"])  # Black's early Qh4 is not the player's habit
    themes = {m["theme"] for m in c.profile()["recurring_mistakes"]}
    assert themes == {"knight_on_rim"}
    c.close()


def test_review_game_without_a_side_reviews_both(chess_api_url):
    llm = QueueLLM([answer("ok")], tool_calls=[("review_game", {})])
    c = Coach(chess_api_url, llm)
    c.ask("Review the game", GAME)
    review = llm.tool_results[0]
    assert review["reviewed"] == "6 white and black moves"
    assert {f["move"] for f in review["findings"]} >= {"2. Na3", "2... Qh4"}
    c.close()


def test_review_last_move_does_not_blame_the_player_for_the_opponents_move(chess_api_url):
    llm = QueueLLM([answer("ok")], tool_calls=[("review_last_move", {})])
    c = Coach(chess_api_url, llm)
    # White's 2.Ba6?? hangs the bishop, but the player is Black
    c.ask("What was wrong with that move?", BA6, {"uci": "f1a6", "san": "Ba6"}, player_color="black")
    assert c.profile()["recurring_mistakes"] == []
    c.close()


def test_history_about_another_position_is_labelled(chess_api_url):
    c = Coach(chess_api_url)
    other = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    start = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    c.ask("And now?", history=[
        {"role": "user", "content": "Is e4 good?", "fen": other},
        {"role": "coach", "content": "Yes.", "fen": other},
        {"role": "user", "content": "What about here?", "fen": start},
    ])
    msgs = c.llm.calls[0]["messages"]
    assert msgs[0]["content"].startswith("[This message was about a different position: " + other)
    assert msgs[1]["role"] == "assistant" and msgs[1]["content"].startswith("[This message was about a different position")
    assert msgs[2]["content"] == "What about here?"
    c.close()


# The game from the live test: the player said "I am Black" but the board faced White.
# 1.e4 b5 2.Bxb5 e5 3.Bf1 d5 4.exd5 Qxd5 5.Nc3 c5 6.Nxd5 a5 7.Nf3
LIVE = {"moves": ["e2e4", "b7b5", "f1b5", "e7e5", "b5f1", "d7d5", "e4d5", "d8d5", "b1c3", "c7c5", "c3d5", "a7a5", "g1f3"]}


def test_review_game_side_from_the_question_beats_the_board_orientation(chess_api_url):
    llm = QueueLLM([answer("ok")], tool_calls=[("review_game", {"side": "black"})])
    c = Coach(chess_api_url, llm)
    c.ask("I am black now, what mistakes am I making?", LIVE, player_color="white")
    review = llm.tool_results[0]
    assert review["reviewed"] == "6 black moves"
    found = {f["move"]: f["patterns"] for f in review["findings"]}
    assert "Bxb5 won a pawn (1 pawn of material) and it wasn't won back" in found["1... b5"][0]
    assert found["5... c5"] == ["after c5 the queen on d5 could be taken for free"]
    assert "3... d5" not in found  # exd5 Qxd5 is an even trade
    themes = {m["theme"]: m["count"] for m in c.profile()["recurring_mistakes"]}
    assert themes == {"gave_away_material": 1, "left_piece_hanging": 1}
    context = llm.calls[0]["messages"][-1]["content"]
    assert "If the question says they play the other side, believe the question" in context
    c.close()


def test_material_given_away_ignores_a_recapture():
    def pos(balance, white, black, fen="8/8/8/8/8/8/8/8 b - - 0 1"):
        return {"material": {"balance_cp": balance, "white": white, "black": black}, "position": {"fen": fen}}

    zero = {"queen": 1, "rook": 2, "bishop": 2, "knight": 2, "pawn": 8}
    seven = {**zero, "pawn": 7}
    # Black's pawn is taken, and Black takes one back before their next move is counted
    assert material_given_away(pos(0, zero, zero), pos(0, seven, seven), "black", {"uci": "d7d5", "san": "d5"}, "exd5") == []
    assert material_given_away(pos(0, zero, zero), pos(100, zero, seven), "black", {"uci": "b7b5", "san": "b5"}, "Bxb5")
