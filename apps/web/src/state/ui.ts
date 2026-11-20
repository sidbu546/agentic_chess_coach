import { create } from "zustand";
import type { DrawShape } from "@lichess-org/chessground/draw";

interface UiState {
  editing: boolean;
  /** Shapes previewed while hovering a fact, an engine line or a coach claim. */
  hoverShapes: DrawShape[];
  engineOn: boolean;
  multipv: number;
  depth: number;
  /** True while a move waits for the chess API to confirm it. */
  moveInFlight: boolean;
  importOpen: boolean;
  settingsOpen: boolean;
  set: (patch: Partial<Omit<UiState, "set">>) => void;
}

export const useUi = create<UiState>()((set) => ({
  editing: false,
  hoverShapes: [],
  engineOn: true,
  multipv: 3,
  depth: 16,
  moveInFlight: false,
  importOpen: false,
  settingsOpen: false,
  set: (patch) => set(patch),
}));
