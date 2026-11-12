"""Coach service settings, read from the environment (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


@dataclass(frozen=True)
class TierConfig:
    model: str
    effort: str


@dataclass(frozen=True)
class Settings:
    chess_api_url: str = field(default_factory=lambda: _env("CHESS_API_URL", "http://localhost:8064").rstrip("/"))
    llm: str = field(default_factory=lambda: _env("COACH_LLM", "auto"))
    fast: TierConfig = field(
        default_factory=lambda: TierConfig(_env("COACH_MODEL_FAST", "gpt-6.1-sol"), _env("COACH_EFFORT_FAST", "low"))
    )
    deep: TierConfig = field(
        default_factory=lambda: TierConfig(_env("COACH_MODEL_DEEP", "gpt-6.1-sol"), _env("COACH_EFFORT_DEEP", "high"))
    )
    port: int = field(default_factory=lambda: int(_env("COACH_PORT", "8065")))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(o.strip() for o in _env("COACH_CORS_ORIGINS", "http://localhost:5173").split(","))
    )
    # One revision round after /v1/verify, then the safe fallback.
    max_revisions: int = 1
    # Tool-call rounds per model run before the model must answer.
    max_tool_rounds: int = 6

    def resolved_llm(self) -> str:
        if self.llm == "auto":
            return "openai" if os.environ.get("OPENAI_API_KEY") else "scripted"
        return self.llm
