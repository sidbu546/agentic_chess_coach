import type { CoachRequest, CoachResponse } from "./types";

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

export async function askCoach(req: CoachRequest, signal?: AbortSignal): Promise<CoachResponse> {
  let res: Response;
  try {
    res = await fetch(`${COACH_API_URL}/v1/coach/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
      signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new CoachApiError(`The coach service isn't reachable at ${COACH_API_URL}.`, true);
  }
  const body = (await res.json().catch(() => null)) as { error?: { message?: string } } | CoachResponse | null;
  if (!res.ok) {
    const msg = (body as { error?: { message?: string } } | null)?.error?.message ?? `Coach error (HTTP ${res.status})`;
    throw new CoachApiError(msg, false);
  }
  return body as CoachResponse;
}
