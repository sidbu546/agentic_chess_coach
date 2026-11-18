"""Web app <-> coach service types. Mirrors apps/web/src/coach/types.ts; Person 2 owns both ends.

Chess types (PositionRef, Move, ClaimResult) follow packages/analysis-schema/openapi.yaml.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AnnotationColor = Literal["green", "red", "blue", "yellow"]
SQUARE = r"^[a-h][1-8]$"


class PositionRef(BaseModel):
    start_fen: str = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    moves: list[str] = Field(default_factory=list)


class Move(BaseModel):
    uci: str
    san: str


class ChatTurn(BaseModel):
    role: Literal["user", "coach"]
    content: str


PLAYER_ID = r"^p_[A-Za-z0-9_-]{1,64}$"
Level = Literal["beginner", "intermediate", "advanced"]
ExplanationDepth = Literal["short", "normal", "detailed"]


class CoachRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    position: PositionRef
    last_move: Move | None = None
    player_id: str = Field(default="p_anonymous", pattern=PLAYER_ID)
    history: list[ChatTurn] = Field(default_factory=list, max_length=12)
    # Optional override of the automatic routing ("think harder").
    depth: Literal["auto", "fast", "deep"] = "auto"
    # Groups questions into sessions in player memory (one per page load in the web app).
    session_id: str | None = Field(default=None, max_length=64)


class BoardArrow(BaseModel):
    from_: str = Field(alias="from", pattern=SQUARE)
    to: str = Field(pattern=SQUARE)
    color: AnnotationColor

    model_config = {"populate_by_name": True}


class BoardHighlight(BaseModel):
    square: str = Field(pattern=SQUARE)
    color: AnnotationColor


class BoardAnnotations(BaseModel):
    arrows: list[BoardArrow] = Field(default_factory=list)
    highlights: list[BoardHighlight] = Field(default_factory=list)


class CheckedClaim(BaseModel):
    # The model's own words.
    text: str
    # What the verifier actually tested, written by the coach (e.g. "the pawn on d4 is passed").
    checked: str = ""
    # ClaimResult from /v1/verify: {id, verdict, reason, facts?}
    result: dict[str, Any]


class Usage(BaseModel):
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    llm_calls: int = 0
    cost_usd: float = 0.0


class CoachResponse(BaseModel):
    answer: str
    annotations: BoardAnnotations
    claims: list[CheckedClaim]
    tools_used: list[str]
    model: str
    tier: Literal["fast", "deep", "fallback"] = "fast"
    usage: Usage = Field(default_factory=Usage)
    # What player memory told the coach, so the UI can show who it answered for.
    level: Level = "intermediate"
    explanation_depth: ExplanationDepth = "normal"

    def to_json(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)


class PlayerUpdate(BaseModel):
    """PATCH /v1/players/{id}. Only the fields sent are changed; null clears rating or level."""

    rating: int | None = Field(default=None, ge=100, le=3500)
    level: Level | None = None
    explanation_depth: ExplanationDepth | None = None

    model_config = {"extra": "forbid"}
