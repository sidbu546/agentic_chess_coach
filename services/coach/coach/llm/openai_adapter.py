"""OpenAI Responses API adapter (GPT-6.1 Sol by default).

Follows OpenAI's guidance for reasoning models with tools: function tools with strict schemas,
the model's output items (including reasoning items) replayed in order on every round, and
store=False so nothing is kept server-side (reasoning comes back as encrypted content instead).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import openai
from openai import AsyncOpenAI

from .base import LLMResult, LLMUsage, LLMError, ToolExecutor

log = logging.getLogger("coach.llm.openai")


class OpenAIAdapter:
    name = "openai"

    def __init__(self, client: AsyncOpenAI | None = None):
        self.client = client or AsyncOpenAI()

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
    ) -> LLMResult:
        items: list[Any] = list(state or [])
        items += [{"role": m["role"], "content": m["content"]} for m in messages]
        fn_tools = [
            {"type": "function", "name": t["name"], "description": t["description"], "parameters": t["parameters"], "strict": True}
            for t in tools
        ]
        usage = LLMUsage()

        for round_no in range(max_tool_rounds + 1):
            last_round = round_no == max_tool_rounds
            try:
                resp = await self.client.responses.create(
                    model=model,
                    instructions=system,
                    input=items,
                    tools=fn_tools,
                    tool_choice="none" if last_round else "auto",
                    parallel_tool_calls=True,
                    reasoning={"effort": effort},
                    text={"format": {"type": "json_schema", "name": "coach_answer", "strict": True, "schema": output_schema}},
                    store=False,
                    include=["reasoning.encrypted_content"],
                )
            except openai.AuthenticationError as exc:
                raise LLMError("OpenAI rejected the API key (check OPENAI_API_KEY).") from exc
            except openai.RateLimitError as exc:
                raise LLMError("OpenAI rate limit reached; try again shortly.") from exc
            except openai.BadRequestError as exc:
                raise LLMError(f"OpenAI rejected the request: {exc}") from exc
            except (openai.APITimeoutError, openai.APIConnectionError) as exc:
                raise LLMError("Could not reach OpenAI.") from exc
            except openai.APIStatusError as exc:
                raise LLMError(f"OpenAI error (HTTP {exc.status_code}).") from exc

            usage.add(_usage(resp))
            items += resp.output  # reasoning + function_call + message items, in order

            calls = [it for it in resp.output if getattr(it, "type", None) == "function_call"]
            if calls:
                results = await asyncio.gather(*(self._call(execute, c) for c in calls))
                for call, result in zip(calls, results):
                    items.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(result)})
                continue

            if getattr(resp, "status", "completed") != "completed":
                raise LLMError(f"The model stopped early ({resp.status}).")
            for it in resp.output:
                for part in getattr(it, "content", None) or []:
                    if getattr(part, "type", None) == "refusal":
                        raise LLMError("The model declined to answer.")
            try:
                output = json.loads(resp.output_text)
            except (json.JSONDecodeError, TypeError) as exc:
                raise LLMError("The model's answer was not valid JSON.") from exc
            return LLMResult(output=output, model=model, usage=usage, state=items)

        raise LLMError("The model kept calling tools without answering.")

    @staticmethod
    async def _call(execute: ToolExecutor, call: Any) -> dict[str, Any]:
        try:
            args = json.loads(call.arguments or "{}")
        except json.JSONDecodeError:
            return {"error": "arguments were not valid JSON"}
        log.info("tool %s %s", call.name, args)
        return await execute(call.name, args)


def _usage(resp: Any) -> LLMUsage:
    u = getattr(resp, "usage", None)
    if u is None:
        return LLMUsage(calls=1)
    in_details = getattr(u, "input_tokens_details", None)
    out_details = getattr(u, "output_tokens_details", None)
    return LLMUsage(
        input_tokens=u.input_tokens or 0,
        cached_tokens=(getattr(in_details, "cached_tokens", 0) or 0) if in_details else 0,
        output_tokens=u.output_tokens or 0,
        reasoning_tokens=(getattr(out_details, "reasoning_tokens", 0) or 0) if out_details else 0,
        calls=1,
    )
