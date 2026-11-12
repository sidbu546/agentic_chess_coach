// Web app <-> coach service (services/coach). Person 2 owns both ends, so these types live on the
// coach side rather than in packages/analysis-schema. Keep in sync with services/coach.
import type { ClaimResult, Move, PositionRef, Square } from "@schema";

export type AnnotationColor = "green" | "red" | "blue" | "yellow";

export interface BoardArrow {
  from: Square;
  to: Square;
  color: AnnotationColor;
}

export interface BoardHighlight {
  square: Square;
  color: AnnotationColor;
}

export interface BoardAnnotations {
  arrows: BoardArrow[];
  highlights: BoardHighlight[];
}

export interface ChatTurn {
  role: "user" | "coach";
  content: string;
}

export interface CoachRequest {
  question: string;
  /** The position on the board when the question was asked (start FEN + full history). */
  position: PositionRef;
  /** The move that led to this position, if any, so "why was that bad?" has a referent. */
  last_move?: Move | null;
  player_id: string;
  /** Recent turns of this conversation, oldest first. */
  history: ChatTurn[];
  /** "deep" forces the stronger tier ("Think harder"); "auto" lets the coach route. */
  depth?: "auto" | "fast" | "deep";
}

export interface CoachUsage {
  input_tokens: number;
  cached_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  llm_calls: number;
  cost_usd: number;
}

/** One claim the coach made, with the verifier's verdict from /v1/verify. */
export interface CheckedClaim {
  /** The model's own words. */
  text: string;
  /** What the verifier actually tested, written by the coach (e.g. "after a3 Bxc3+ bxc3: white has doubled c-pawns"). */
  checked?: string;
  result: ClaimResult;
}

export interface CoachResponse {
  answer: string;
  annotations: BoardAnnotations;
  claims: CheckedClaim[];
  /** Chess API endpoints the agent called, for transparency in the UI. */
  tools_used: string[];
  model: string;
  /** Which tier answered; "fallback" means only verified facts could be given. */
  tier?: "fast" | "deep" | "fallback";
  usage?: CoachUsage;
}
