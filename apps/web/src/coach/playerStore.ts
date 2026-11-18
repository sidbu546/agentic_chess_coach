import { create } from "zustand";
import { CoachApiError, forgetPlayer, getPlayer, updatePlayer } from "./coachApi";
import { playerId } from "./coachStore";
import type { PlayerProfile, PlayerUpdate } from "./types";

interface PlayerState {
  profile: PlayerProfile | null;
  /** Set when the coach service can't be reached or rejects a change. */
  error: string | null;
  load: () => Promise<void>;
  save: (update: PlayerUpdate) => Promise<void>;
  forget: () => Promise<void>;
}

const message = (err: unknown) =>
  err instanceof CoachApiError && err.offline ? "The coach service isn't running, so your profile can't be loaded." : (err as Error).message;

export const usePlayer = create<PlayerState>()((set) => ({
  profile: null,
  error: null,
  load: async () => {
    try {
      set({ profile: await getPlayer(playerId()), error: null });
    } catch (err) {
      set({ error: message(err) });
    }
  },
  save: async (update) => {
    try {
      set({ profile: await updatePlayer(playerId(), update), error: null });
    } catch (err) {
      set({ error: message(err) });
    }
  },
  forget: async () => {
    try {
      await forgetPlayer(playerId());
      set({ profile: await getPlayer(playerId()), error: null });
    } catch (err) {
      set({ error: message(err) });
    }
  },
}));
