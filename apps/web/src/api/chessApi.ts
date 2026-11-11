// Typed client for the chess truth API (packages/analysis-schema/openapi.yaml).
// The web app never decides chess truth itself: legality, SAN, game trees and facts all come from here.
import type {
  AnalyzeRequest,
  AnalyzeResponse,
  CompareRequest,
  CompareResponse,
  ErrorResponse,
  GameRequest,
  GameResponse,
  HealthResponse,
  MoveRequest,
  MoveResponse,
  PositionRef,
  PositionRequest,
  PositionResponse,
  VerifyRequest,
  VerifyResponse,
} from "@schema";

export const CHESS_API_URL: string = (import.meta.env.VITE_CHESS_API_URL ?? "http://localhost:8064").replace(/\/$/, "");

export type ErrorCode = ErrorResponse["error"]["code"] | "network" | "http";

export class ChessApiError extends Error {
  constructor(
    public readonly code: ErrorCode,
    message: string,
    public readonly status: number,
    public readonly details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "ChessApiError";
  }
}

/** Where the last response came from, per the mock's X-Mock-Source header (absent on the real service). */
export type DataSource = "fixture" | "live" | "fake" | "real";

export interface WithSource<T> {
  data: T;
  source: DataSource;
}

async function call<T>(method: "GET" | "POST", path: string, body?: unknown, signal?: AbortSignal): Promise<WithSource<T>> {
  let res: Response;
  try {
    res = await fetch(CHESS_API_URL + path, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ChessApiError("network", `Chess API unreachable at ${CHESS_API_URL}`, 0);
  }
  const json = (await res.json().catch(() => null)) as unknown;
  if (!res.ok) {
    const e = (json as ErrorResponse | null)?.error;
    throw new ChessApiError(e?.code ?? "http", e?.message ?? `HTTP ${res.status}`, res.status, e?.details);
  }
  const source = (res.headers.get("X-Mock-Source") as DataSource | null) ?? "real";
  return { data: json as T, source };
}

export const chessApi = {
  health: (signal?: AbortSignal) => call<HealthResponse>("GET", "/v1/health", undefined, signal),
  position: (req: PositionRequest, signal?: AbortSignal) => call<PositionResponse>("POST", "/v1/position", req, signal),
  move: (req: MoveRequest, signal?: AbortSignal) => call<MoveResponse>("POST", "/v1/move", req, signal),
  analyze: (req: AnalyzeRequest, signal?: AbortSignal) => call<AnalyzeResponse>("POST", "/v1/analyze", req, signal),
  compare: (req: CompareRequest, signal?: AbortSignal) => call<CompareResponse>("POST", "/v1/compare", req, signal),
  verify: (req: VerifyRequest, signal?: AbortSignal) => call<VerifyResponse>("POST", "/v1/verify", req, signal),
  game: (req: GameRequest, signal?: AbortSignal) => call<GameResponse>("POST", "/v1/game", req, signal),
};

export const STARTPOS = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

/** Stable cache key for a PositionRef (history matters: repetition depends on it). */
export function positionKey(ref: PositionRef): string {
  return `${ref.start_fen ?? STARTPOS}|${ref.moves.join(",")}`;
}
