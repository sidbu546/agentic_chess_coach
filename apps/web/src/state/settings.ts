import { create } from "zustand";
import { createJSONStorage, persist, type StateStorage } from "zustand/middleware";

export const BOARD_THEMES = {
  // Think64 default: white light squares, orange dark squares.
  orange: { label: "Orange", light: "#ffffff", dark: "#f28c28" },
  // En Croissant's default board.
  gray: { label: "Gray", light: "#e9ecef", dark: "#868e96" },
  brown: { label: "Brown", light: "#f0d9b5", dark: "#b58863" },
  blue: { label: "Blue", light: "#dee3e6", dark: "#8ca2ad" },
  green: { label: "Green", light: "#ffffdd", dark: "#86a666" },
} as const;
export type BoardTheme = keyof typeof BOARD_THEMES;

export const PIECE_SETS = { staunty: "Staunty", cburnett: "Cburnett" } as const;
export type PieceSet = keyof typeof PIECE_SETS;

export type Orientation = "white" | "black";

interface Settings {
  boardTheme: BoardTheme;
  pieceSet: PieceSet;
  showCoordinates: boolean;
  showDests: boolean;
  highlightLastMove: boolean;
  animation: boolean;
  scrollToNavigate: boolean;
  showEvalBar: boolean;
  showEngineArrows: boolean;
  autoQueen: boolean;
  orientation: Orientation;
  set: (patch: Partial<Omit<Settings, "set">>) => void;
}

// localStorage may be missing or throw (private windows, blocked storage): never let that break the app.
const safeStorage: StateStorage = {
  getItem: (k) => {
    try {
      return localStorage.getItem(k);
    } catch {
      return null;
    }
  },
  setItem: (k, v) => {
    try {
      localStorage.setItem(k, v);
    } catch {
      /* ignore */
    }
  },
  removeItem: (k) => {
    try {
      localStorage.removeItem(k);
    } catch {
      /* ignore */
    }
  },
};

export const useSettings = create<Settings>()(
  persist(
    (set) => ({
      boardTheme: "orange",
      pieceSet: "staunty",
      showCoordinates: true,
      showDests: true,
      highlightLastMove: true,
      animation: true,
      scrollToNavigate: true,
      showEvalBar: true,
      showEngineArrows: true,
      autoQueen: false,
      orientation: "white",
      set: (patch) => set(patch),
    }),
    { name: "think64-settings", storage: createJSONStorage(() => safeStorage), version: 1 },
  ),
);
