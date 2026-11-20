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
  /** FEN of the position the turn was about, so the coach doesn't mix up positions. */
  fen?: string;
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
  /** Groups questions into sessions in player memory (one per page load). */
  session_id?: string;
  /** The side the player plays; the web app sends the board orientation. */
  player_color?: "white" | "black";
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
  /** Lines from the answer that /v1/verify supported, playable on the board. */
  lines?: CoachLine[];
  /** What player memory told the coach about who it is answering. */
  level?: Level;
  explanation_depth?: ExplanationDepth;
}

// ---------------------------------------------------------------- player memory

export type Level = "beginner" | "intermediate" | "advanced";
export type ExplanationDepth = "short" | "normal" | "detailed";

export interface RecurringMistake {
  theme: string;
  /** e.g. "left a piece undefended where it could be taken" */
  label: string;
  count: number;
  /** Unix seconds. */
  last_seen: number;
  last_example: { move: string; detail: string };
}

export interface PlayerProfile {
  player_id: string;
  rating: number | null;
  /** The level the coach uses: chosen by the player, else from the rating, else "intermediate". */
  level: Level;
  level_source: "chosen" | "rating" | "default";
  explanation_depth: ExplanationDepth;
  recurring_mistakes: RecurringMistake[];
  stats: { questions: number; sessions: number; first_seen: number | null; last_seen: number | null };
}

/** PATCH /v1/players/{id}: only the keys sent change; null clears rating or level. */
export interface PlayerUpdate {
  rating?: number | null;
  level?: Level | null;
  explanation_depth?: ExplanationDepth;
}

export interface SessionSummary {
  session_id: string;
  started: number;
  ended: number;
  questions: number;
  cost_usd: number;
  topics: string[];
}

// ---------------------------------------------------------------- playable lines

export interface LineStep {
  uci: string;
  san: string;
  /** Position after this move, from the chess API. */
  fen: string;
  state: "ongoing" | "checkmate" | "stalemate" | "insufficient_material" | "fivefold_repetition" | "seventyfive_moves";
  in_check: boolean;
  winner: "white" | "black" | null;
}

export interface CoachLine {
  /** The coach's words for this line. */
  title: string;
  start_fen: string;
  steps: LineStep[];
}
