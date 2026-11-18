import type { CoachRequest, CoachResponse, PlayerProfile, PlayerUpdate, SessionSummary } from "./types";

export const COACH_API_URL: string = (import.meta.env.VITE_COACH_API_URL ?? "http://localhost:8065").replace(/\/$/, "");

export class CoachApiError extends Error {
  constructor(
    message: string,
    public readonly offline: boolean,
  ) {
    super(message);
    this.name = "CoachApiError";
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${COACH_API_URL}${path}`, {
      ...init,
      headers: init.body ? { "Content-Type": "application/json" } : undefined,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new CoachApiError(`The coach service isn't reachable at ${COACH_API_URL}.`, true);
  }
  if (res.status === 204) return undefined as T;
  const body = (await res.json().catch(() => null)) as { error?: { message?: string }; detail?: unknown } | null;
  if (!res.ok) {
    const msg = body?.error?.message ?? `Coach error (HTTP ${res.status})`;
    throw new CoachApiError(msg, false);
  }
  return body as T;
}

export function askCoach(req: CoachRequest, signal?: AbortSignal): Promise<CoachResponse> {
  return call<CoachResponse>("/v1/coach/ask", { method: "POST", body: JSON.stringify(req), signal });
}

const player = (id: string) => `/v1/players/${encodeURIComponent(id)}`;

export const getPlayer = (id: string) => call<PlayerProfile>(player(id));
export const updatePlayer = (id: string, update: PlayerUpdate) =>
  call<PlayerProfile>(player(id), { method: "PATCH", body: JSON.stringify(update) });
export const forgetPlayer = (id: string) => call<void>(player(id), { method: "DELETE" });
export const getSessions = (id: string) =>
  call<{ sessions: SessionSummary[] }>(`${player(id)}/sessions`).then((r) => r.sessions);
