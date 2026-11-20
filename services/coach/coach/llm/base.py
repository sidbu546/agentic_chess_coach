"""The LLM adapter interface. One implementation per provider; the agent only sees this.

An adapter runs the whole tool loop for one turn (providers differ in how tool calls and their
results are threaded), then returns the model's final JSON matching `output_schema`. `state` lets
the agent continue the same conversation, e.g. to ask for a revision after /v1/verify.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


class LLMError(Exception):
    """The model call failed (provider down, refusal, unparseable output)."""


@dataclass
class LLMUsage:
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    calls: int = 0

    def add(self, other: "LLMUsage") -> None:
        self.input_tokens += other.input_tokens
        self.cached_tokens += other.cached_tokens
        self.output_tokens += other.output_tokens
        self.reasoning_tokens += other.reasoning_tokens
        self.calls += other.calls


@dataclass
class LLMResult:
    output: dict[str, Any]
    model: str
    usage: LLMUsage = field(default_factory=LLMUsage)
    # Provider-specific conversation so far, passed back to continue it.
    state: Any = None


class LLMAdapter(Protocol):
    name: str

    async def run(
        self,
        *,
        model: str,
        effort: str,
        system: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        execute: ToolExecutor,
        output_schema: dict[str, Any],
        max_tool_rounds: int,
        state: Any = None,
    ) -> LLMResult: ...
