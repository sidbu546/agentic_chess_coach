import { create } from "zustand";
import type { PositionRef } from "@schema";
import type { CoachLine } from "@/coach/types";
import { playLine } from "./actions";
import { useGameTree } from "./gameTree";

/**
 * Plays a coach line back on the board without touching the game: the board shows the line's
 * positions (from the chess API) until the player closes it, adds it to the game, or makes their
 * own move from one of its positions.
 */
interface LinePlayerState {
  line: CoachLine | null;
  /** Game-tree node the line starts from. */
  startNodeId: string | null;
  /** 0 = start position, k = after the k-th move. */
  index: number;
  playing: boolean;
  /** Seconds per move. */
  speed: number;
  /** Draw the engine's top moves in each position of the line (needs a real engine). */
  ideas: boolean;
  setIdeas: (ideas: boolean) => void;
  open: (line: CoachLine, startNodeId: string) => void;
  close: () => void;
  go: (index: number) => void;
  step: (delta: number) => void;
  setPlaying: (playing: boolean) => void;
  setSpeed: (speed: number) => void;
  /** Put the first `count` moves of the line into the game (as a variation if the game went elsewhere). */
  addToGame: (count?: number) => Promise<void>;
}

export const useLinePlayer = create<LinePlayerState>()((set, get) => ({
  line: null,
  startNodeId: null,
  index: 0,
  playing: false,
  speed: 1.2,
  ideas: false,
  setIdeas: (ideas) => set({ ideas }),
  open: (line, startNodeId) => set({ line, startNodeId, index: 0, playing: true }),
  close: () => set({ line: null, startNodeId: null, index: 0, playing: false }),
  go: (index) => {
    const n = get().line?.steps.length ?? 0;
    set({ index: Math.max(0, Math.min(n, index)) });
  },
  step: (delta) => {
    get().go(get().index + delta);
    set({ playing: false });
  },
  setPlaying: (playing) => {
    const { line, index } = get();
    // Pressing play at the end starts again from the beginning.
    if (playing && line && index >= line.steps.length) set({ index: 0 });
    set({ playing });
  },
  setSpeed: (speed) => set({ speed }),
  addToGame: async (count) => {
    const { line, startNodeId } = get();
    if (!line || !startNodeId) return;
    const tree = useGameTree.getState();
    if (tree.nodes[startNodeId]) tree.goTo(startNodeId);
    get().close();
    await playLine(line.steps.slice(0, count ?? line.steps.length).map((s) => s.uci));
  },
}));

/** "1. e4 e5 2. Bc4" numbering for a line starting at `startFen`. */
export function moveLabel(startFen: string, ply: number, san: string): string {
  const [, side, , , , full] = startFen.split(" ");
  const whiteFirst = side !== "b";
  const absolute = ply + (whiteFirst ? 0 : 1); // plies since White's move of the start move number
  const number = Number(full || 1) + Math.floor(absolute / 2);
  return absolute % 2 === 0 ? `${number}. ${san}` : `${number}... ${san}`;
}

export function lineText(line: CoachLine): string {
  return line.steps
    .map((s, i) => {
      const label = moveLabel(line.start_fen, i, s.san);
      return i === 0 || label.includes(". ") && !label.includes("...") ? label : s.san;
    })
    .join(" ");
}

/** The position the line player is showing, as a PositionRef the chess API understands. */
export function usePreviewPosition(): { fen: string; position: PositionRef } | null {
  const line = useLinePlayer((s) => s.line);
  const index = useLinePlayer((s) => s.index);
  const startId = useLinePlayer((s) => s.startNodeId);
  const start = useGameTree((s) => (startId ? (s.nodes[startId] ?? null) : null));
  if (!line || !start) return null;
  return {
    fen: index === 0 ? line.start_fen : line.steps[index - 1].fen,
    position: { ...start.position, moves: [...start.position.moves, ...line.steps.slice(0, index).map((s) => s.uci)] },
  };
}
