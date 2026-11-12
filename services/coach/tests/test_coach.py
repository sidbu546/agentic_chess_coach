from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from coach.agent import route
from coach.app import create_app
from coach.config import Settings, TierConfig
from coach.llm.base import LLMError, LLMUsage
from coach.llm.openai_adapter import OpenAIAdapter
from coach.llm.scripted import ScriptedAdapter
from coach.pricing import cost_usd
from coach.prompts import ANSWER_SCHEMA
from coach.schemas import CoachRequest, PositionRef
from coach.tools import TOOL_DEFINITIONS, numbered

from .conftest import NIMZO, QueueLLM, answer, claim


def settings(url: str) -> Settings:
    return Settings(
        chess_api_url=url,
        llm="scripted",
        fast=TierConfig("gpt-6.1-sol", "low"),
        deep=TierConfig("gpt-6.1-sol", "high"),
    )


def ask(url: str, llm, question: str, position: dict | None = None, **extra):
    with TestClient(create_app(settings(url), llm=llm)) as client:
        body = {"question": question, "position": position or {"moves": []}, **extra}
        return client.post("/v1/coach/ask", json=body)


# ---------------------------------------------------------------- routing


@pytest.mark.parametrize(
    "question,tier",
    [
        ("best move?", "fast"),
        ("Is my knight hanging?", "fast"),
        ("Why is Nd5 better than Bxf6 here?", "deep"),
        ("What's the plan for White?", "deep"),
        ("Compare e4 and d4", "deep"),
        ("What happens after Nf3 Nc6 Bb5?", "deep"),
    ],
)
def test_route(question, tier):
    req = CoachRequest(question=question, position=PositionRef())
    assert route(req) == tier


def test_route_override():
    req = CoachRequest(question="best move?", position=PositionRef(), depth="deep")
    assert route(req) == "deep"


# ---------------------------------------------------------------- the verify loop


def test_supported_claims_pass_through_with_arrows(chess_api_url):
    llm = QueueLLM([answer(
        "Your knight on c3 is pinned to the king by the bishop on b4.",
        [claim("knight on c3 is pinned", "pinned", square="c3", absolute=True)],
        [{"move": None, "from": "b4", "to": "e1", "color": "red"}, {"move": "a3", "from": None, "to": None, "color": "green"}],
    )])
    res = ask(chess_api_url, llm, "Is my knight hanging?", NIMZO)
    assert res.status_code == 200
    body = res.json()
    assert body["claims"][0]["result"]["verdict"] == "supported"
    assert len(llm.calls) == 1  # nothing to revise
    # the SAN arrow's squares come from the chess API, not the model
    assert {"from": "a2", "to": "a3", "color": "green"} in body["annotations"]["arrows"]
    assert {"from": "b4", "to": "e1", "color": "red"} in body["annotations"]["arrows"]
    assert body["tier"] == "fast" and "verify" in body["tools_used"]
    assert body["usage"]["llm_calls"] == 1 and body["usage"]["cost_usd"] > 0


def test_refuted_claim_is_sent_back_and_fixed(chess_api_url):
    llm = QueueLLM([
        answer("The knight on f3 is pinned.", [claim("knight on f3 is pinned", "pinned", square="f3")]),
        answer("The knight on c3 is pinned.", [claim("knight on c3 is pinned", "pinned", square="c3")]),
    ])
    body = ask(chess_api_url, llm, "What is pinned?", NIMZO).json()
    assert len(llm.calls) == 2
    feedback = llm.calls[1]["messages"][0]["content"]
    assert "knight on f3 is pinned" in feedback and "refuted" in feedback
    assert llm.calls[1]["state"] == ["s"]  # the revision continues the same conversation
    assert body["answer"] == "The knight on c3 is pinned."
    assert [c["result"]["verdict"] for c in body["claims"]] == ["supported"]
    assert body["usage"]["llm_calls"] == 2


def test_persistent_false_claim_falls_back_to_verified_facts(chess_api_url):
    wrong = answer("Black is in check.", [claim("Black is in check", "in_check", color="black")])
    llm = QueueLLM([wrong, wrong])
    body = ask(chess_api_url, llm, "Who is in check?", NIMZO).json()
    assert body["tier"] == "fallback"
    assert "Black is in check" not in body["answer"]
    assert "pinned" in body["answer"]  # the real pin fact from /v1/position
    assert body["claims"] == []


def test_illegal_san_is_refuted_without_reaching_verify(chess_api_url):
    llm = QueueLLM([
        answer("Ke2 is legal.", [claim("Ke2 is legal", "legal_move", move="Ke2")]),
        answer("e4 is a legal first move.", [claim("e4 is legal", "legal_move", move="e4")]),
    ])
    body = ask(chess_api_url, llm, "Can I play Ke2?").json()
    assert "Ke2" in llm.calls[1]["messages"][0]["content"]
    assert body["claims"][0]["result"]["verdict"] == "supported"


def test_engine_claims_on_mock_are_unverifiable_and_revised(chess_api_url):
    # Away from the fixtures, the mock can't check engine claims; the coach must not state them as fact.
    pos = {"moves": ["e2e4", "c7c5"]}
    llm = QueueLLM([
        answer("Nf3 is best.", [claim("Nf3 is best", "best_move", move="Nf3")]),
        answer("Nf3 is a natural developing move.", [claim("Nf3 is legal", "legal_move", move="Nf3")]),
    ])
    body = ask(chess_api_url, llm, "best move?", pos).json()
    assert "unverifiable" in llm.calls[1]["messages"][0]["content"]
    assert [c["result"]["verdict"] for c in body["claims"]] == ["supported"]


def test_tools_reach_the_chess_api(chess_api_url):
    llm = QueueLLM(
        [answer("ok")],
        tool_calls=[
            ("analyze_position", {"multipv": 3}),
            ("compare_moves", {"moves": ["a3", "Qxz9"]}),
            ("explore_line", {"moves": ["a3", "Bxc3+", "bxc3"]}),
            ("review_last_move", {}),
        ],
    )
    body = ask(chess_api_url, llm, "Why is a3 good here?", NIMZO).json()
    analyze, compare, explore, review = llm.tool_results
    assert analyze["engine"] == "mock" and analyze["engine_note"]  # placeholders are flagged for the model
    assert compare["illegal"][0]["move"] == "Qxz9" and compare["lines"][0]["move"] == "a3"
    assert explore["legal"] and explore["line"] == "4. a3 Bxc3+ 5. bxc3"
    assert "Status:" in explore["resulting_position"]
    assert review["available"] and review["played"] == "Bb4" and review["played_by"] == "black"
    assert body["tier"] == "deep"
    assert set(body["tools_used"]) >= {"position", "analyze", "move", "compare"}


def test_start_position_fixture_gives_real_engine_lines(chess_api_url):
    llm = QueueLLM([answer("ok")], tool_calls=[("analyze_position", {"multipv": 3})])
    ask(chess_api_url, llm, "best move?")
    lines = llm.tool_results[0]["lines"]
    assert [ln["move"] for ln in lines] == ["e4", "d4", "Nf3"]  # Stockfish fixture, example 05
    assert lines[0]["line"].startswith("1. e4")


# ---------------------------------------------------------------- scripted mode (no API key)


def test_scripted_mode_runs_end_to_end(chess_api_url):
    body = ask(chess_api_url, ScriptedAdapter(), "What's going on here?", NIMZO).json()
    assert "Template answer" in body["answer"]
    assert "pinned" in body["answer"]
    verdicts = {c["text"]: c["result"]["verdict"] for c in body["claims"]}
    assert all(v == "supported" for v in verdicts.values()) and verdicts


# ---------------------------------------------------------------- errors


def test_bad_position_is_422(chess_api_url):
    res = ask(chess_api_url, QueueLLM([]), "best move?", {"moves": ["e2e5"]})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "illegal_move_in_history"


def test_llm_failure_is_503(chess_api_url):
    res = ask(chess_api_url, QueueLLM([LLMError("Could not reach OpenAI.")]), "best move?")
    assert res.status_code == 503
    assert res.json()["error"]["message"] == "Could not reach OpenAI."


def test_chess_api_down_is_503():
    res = ask("http://127.0.0.1:9", QueueLLM([]), "best move?")
    assert res.status_code == 503


def test_health(chess_api_url):
    with TestClient(create_app(settings(chess_api_url), llm=ScriptedAdapter())) as client:
        h = client.get("/v1/health").json()
    assert h["status"] == "ok" and h["llm"] == "scripted" and h["models"]["deep"] == "gpt-6.1-sol"


# ---------------------------------------------------------------- pieces


def test_cost_uses_cached_rate():
    u = LLMUsage(input_tokens=40_000, cached_tokens=30_000, output_tokens=5_000)
    # 10k uncached x $2 + 30k cached x $0.10 + 5k x $10, per million
    assert cost_usd("gpt-6.1-sol", u) == pytest.approx(0.02 + 0.003 + 0.05)
    assert cost_usd("unknown-model", u) == 0.0


def test_numbered_lines():
    assert numbered(["e4", "e5", "Nf3"], 1, True) == "1. e4 e5 2. Nf3"
    assert numbered(["Bb4", "a3"], 3, False) == "3... Bb4 4. a3"


def test_schemas_are_strict():
    """OpenAI strict mode: every object lists all its properties as required and forbids extras."""
    def check(s):
        if s.get("type") == "object" or s.get("type") == ["object"]:
            assert s["additionalProperties"] is False
            assert set(s["required"]) == set(s["properties"])
            for p in s["properties"].values():
                check(p)
        if "items" in s:
            check(s["items"])
    check(ANSWER_SCHEMA)
    for t in TOOL_DEFINITIONS:
        check(t["parameters"])


# ---------------------------------------------------------------- OpenAI adapter, with a fake client


class FakeResponses:
    """Simulates responses.create: first a function call, then the final JSON message."""

    def __init__(self, final: dict):
        self.final = final
        self.requests: list[dict] = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        usage = SimpleNamespace(
            input_tokens=500, output_tokens=100,
            input_tokens_details=SimpleNamespace(cached_tokens=100),
            output_tokens_details=SimpleNamespace(reasoning_tokens=60),
        )
        if len(self.requests) == 1:
            call = SimpleNamespace(type="function_call", name="analyze_position", arguments='{"multipv": 2}', call_id="call_1")
            reasoning = SimpleNamespace(type="reasoning", encrypted_content="xyz")
            return SimpleNamespace(output=[reasoning, call], output_text="", status="completed", usage=usage)
        msg = SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text", text=json.dumps(self.final))])
        return SimpleNamespace(output=[msg], output_text=json.dumps(self.final), status="completed", usage=usage)


def test_openai_adapter_tool_loop():
    asyncio.run(_openai_adapter_tool_loop())


async def _openai_adapter_tool_loop():
    final = answer("e4 is best.")
    fake = FakeResponses(final)
    adapter = OpenAIAdapter(client=SimpleNamespace(responses=fake))
    executed = []

    async def execute(name, args):
        executed.append((name, args))
        return {"lines": []}

    result = await adapter.run(
        model="gpt-6.1-sol", effort="high", system="sys", messages=[{"role": "user", "content": "q"}],
        tools=TOOL_DEFINITIONS, execute=execute, output_schema=ANSWER_SCHEMA, max_tool_rounds=4,
    )
    assert result.output == final
    assert executed == [("analyze_position", {"multipv": 2})]
    first, second = fake.requests
    assert first["reasoning"] == {"effort": "high"} and first["store"] is False
    assert first["tools"][0]["strict"] is True and first["text"]["format"]["strict"] is True
    # the reasoning item and the call are replayed in order, followed by the tool output
    replay = second["input"]
    assert replay[1].type == "reasoning" and replay[2].type == "function_call"
    assert replay[3] == {"type": "function_call_output", "call_id": "call_1", "output": json.dumps({"lines": []})}
    assert result.usage.calls == 2 and result.usage.reasoning_tokens == 120 and result.usage.cached_tokens == 200
