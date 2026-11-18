import { create } from "zustand";
import type { BoardAnnotations, CheckedClaim, CoachResponse } from "./types";

export interface ChatMessage {
  id: string;
  role: "user" | "coach";
  text: string;
  /** positionKey() of the board position this message is about. */
  positionKey: string;
  /** Node in the game tree the message was asked at, so clicking it can jump back there. */
  nodeId: string;
  status: "pending" | "ok" | "error";
  annotations?: BoardAnnotations;
  claims?: CheckedClaim[];
  toolsUsed?: string[];
  model?: string;
  tier?: CoachResponse["tier"];
  usage?: CoachResponse["usage"];
}

interface CoachState {
  messages: ChatMessage[];
  /** Coach message whose arrows/highlights are drawn on the board (only on its own position). */
  shownId: string | null;
  add: (m: ChatMessage) => void;
  update: (id: string, patch: Partial<ChatMessage>) => void;
  show: (id: string | null) => void;
  clear: () => void;
}

export const useCoach = create<CoachState>()((set) => ({
  messages: [],
  shownId: null,
  add: (m) => set((s) => ({ messages: [...s.messages, m] })),
  update: (id, patch) => set((s) => ({ messages: s.messages.map((m) => (m.id === id ? { ...m, ...patch } : m)) })),
  show: (id) => set({ shownId: id }),
  clear: () => set({ messages: [], shownId: null }),
}));

/** Stable per-browser player id; player memory is keyed by it (no accounts yet). */
export function playerId(): string {
  const k = "think64-player-id";
  try {
    let id = localStorage.getItem(k);
    if (!id) {
      id = `p_${crypto.randomUUID()}`;
      localStorage.setItem(k, id);
    }
    return id;
  } catch {
    return "p_anonymous";
  }
}

/** One id per page load, so player memory can group questions into sessions. */
export function sessionId(): string {
  const k = "think64-session-id";
  try {
    let id = sessionStorage.getItem(k);
    if (!id) {
      id = `s_${crypto.randomUUID()}`;
      sessionStorage.setItem(k, id);
    }
    return id;
  } catch {
    return "s_default";
  }
}
