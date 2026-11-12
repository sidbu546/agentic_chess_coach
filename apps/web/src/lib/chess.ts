import { Chess, type Square as CjsSquare } from "chess.js";
import type { Key } from "@lichess-org/chessground/types";
import type { Color, PieceType, Score } from "@schema";

// chess.js is used ONLY for instant feedback while dragging (legal-move dots, check highlight).
// The chess API is the final authority on every move.

export interface LocalPosition {
  dests: Map<Key, Key[]>;
  turn: Color;
  inCheck: boolean;
  /** False if chess.js could not load the FEN; the board then falls back to free moves + API check. */
  ok: boolean;
}

export function localPosition(fen: string): LocalPosition {
  const turn: Color = fen.split(" ")[1] === "b" ? "black" : "white";
  try {
    const chess = new Chess(fen);
    const dests = new Map<Key, Key[]>();
    for (const m of chess.moves({ verbose: true })) {
      const list = dests.get(m.from as Key) ?? [];
      if (!list.includes(m.to as Key)) list.push(m.to as Key);
      dests.set(m.from as Key, list);
    }
    return { dests, turn, inCheck: chess.inCheck(), ok: true };
  } catch {
    return { dests: new Map(), turn, inCheck: false, ok: false };
  }
}

export function isPromotion(fen: string, from: Key, to: Key): boolean {
  try {
    const piece = new Chess(fen, { skipValidation: true }).get(from as CjsSquare);
    return piece?.type === "p" && (to[1] === "8" || to[1] === "1");
  } catch {
    return false;
  }
}

/** Optimistic SAN for a move, used only to label a move while the API confirms it. */
export function localSan(fen: string, uci: string): string | null {
  try {
    const chess = new Chess(fen);
    return chess.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] }).san;
  } catch {
    return null;
  }
}

// ---------- material ----------

const VALUES: Record<string, number> = { p: 1, n: 3, b: 3, r: 5, q: 9, k: 0 };
export const ROLE_ORDER = ["q", "r", "b", "n", "p"] as const;
export type RoleChar = (typeof ROLE_ORDER)[number];

export interface MaterialDiff {
  /** Pieces White has more of (positive) or fewer of (negative), by role. */
  surplus: Record<RoleChar, number>;
  /** White minus Black in pawns. */
  points: number;
}

export function materialDiff(fen: string): MaterialDiff {
  const surplus: Record<RoleChar, number> = { q: 0, r: 0, b: 0, n: 0, p: 0 };
  let points = 0;
  for (const ch of fen.split(" ")[0]) {
    const lower = ch.toLowerCase();
    if (!(lower in VALUES) || lower === "k") continue;
    const sign = ch === lower ? -1 : 1;
    surplus[lower as RoleChar] += sign;
    points += sign * VALUES[lower];
  }
  return { surplus, points };
}

export const PIECE_LETTER: Record<PieceType, string> = {
  king: "k",
  queen: "q",
  rook: "r",
  bishop: "b",
  knight: "n",
  pawn: "p",
};

// ---------- scores (always White's point of view, per the contract) ----------

/** Lichess win-probability curve, 0..100 for White. */
export function winChance(score: Score): number {
  if (score.type === "mate") return score.value > 0 ? 100 : score.value < 0 ? 0 : 50;
  return 50 + 50 * (2 / (1 + Math.exp(-0.00368208 * score.value)) - 1);
}

export function formatScore(score: Score, precision = 2): string {
  if (score.type === "mate") return `${score.value > 0 ? "+" : "-"}M${Math.abs(score.value)}`;
  const v = score.value / 100;
  return `${v > 0 ? "+" : v < 0 ? "-" : ""}${Math.abs(v).toFixed(precision)}`;
}

export function sideToMove(fen: string): Color {
  return fen.split(" ")[1] === "b" ? "black" : "white";
}
