import { create } from "zustand";
import type { Color, Role } from "@lichess-org/chessground/types";

// Position-setup state. The board placement is edited locally; the final FEN is validated by
// the chess API (/v1/position) before it becomes the game's start position.

export type Castling = { K: boolean; Q: boolean; k: boolean; q: boolean };
export type EditTool = { color: Color; role: Role } | "trash" | null;

interface EditorState {
  placement: string;
  turn: "w" | "b";
  castling: Castling;
  tool: EditTool;
  begin: (fen: string) => void;
  setPlacement: (placement: string) => void;
  setTurn: (t: "w" | "b") => void;
  setCastling: (c: Partial<Castling>) => void;
  setTool: (t: EditTool) => void;
}

export const EMPTY_PLACEMENT = "8/8/8/8/8/8/8/8";
export const START_PLACEMENT = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR";

/** Piece letter on `square` in a FEN placement, or null. */
export function pieceAt(placement: string, square: string): string | null {
  const file = square.charCodeAt(0) - 97;
  const rank = Number(square[1]);
  const row = placement.split("/")[8 - rank];
  if (!row) return null;
  let f = 0;
  for (const ch of row) {
    if (/\d/.test(ch)) f += Number(ch);
    else {
      if (f === file) return ch;
      f++;
    }
    if (f > file) return null;
  }
  return null;
}

/** Castling rights that are possible given where the kings and rooks stand. */
export function possibleCastling(placement: string): Castling {
  return {
    K: pieceAt(placement, "e1") === "K" && pieceAt(placement, "h1") === "R",
    Q: pieceAt(placement, "e1") === "K" && pieceAt(placement, "a1") === "R",
    k: pieceAt(placement, "e8") === "k" && pieceAt(placement, "h8") === "r",
    q: pieceAt(placement, "e8") === "k" && pieceAt(placement, "a8") === "r",
  };
}

export function editorFen(s: Pick<EditorState, "placement" | "turn" | "castling">): string {
  const ok = possibleCastling(s.placement);
  const rights = (["K", "Q", "k", "q"] as const).filter((c) => s.castling[c] && ok[c]).join("");
  return `${s.placement} ${s.turn} ${rights || "-"} - 0 1`;
}

export const useEditor = create<EditorState>()((set) => ({
  placement: START_PLACEMENT,
  turn: "w",
  castling: { K: true, Q: true, k: true, q: true },
  tool: null,
  begin: (fen) => {
    const [placement, turn, rights = "-"] = fen.split(" ");
    set({
      placement,
      turn: turn === "b" ? "b" : "w",
      castling: { K: rights.includes("K"), Q: rights.includes("Q"), k: rights.includes("k"), q: rights.includes("q") },
      tool: null,
    });
  },
  setPlacement: (placement) => set({ placement }),
  setTurn: (turn) => set({ turn }),
  setCastling: (c) => set((s) => ({ castling: { ...s.castling, ...c } })),
  setTool: (tool) => set({ tool }),
}));
