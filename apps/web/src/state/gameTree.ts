import { create } from "zustand";
import type { GameResponse, Move, PositionRef } from "@schema";
import { STARTPOS } from "@/api/chessApi";

// The move tree the board displays and navigates. Its contents always come from the chess API:
// /v1/game for imported PGNs, /v1/move for moves the player makes. Nothing here parses PGN or
// decides legality.

export const ROOT_ID = "root";

export interface TreeNode {
  id: string;
  parentId: string | null;
  /** Plies from the start position (0 for the root). */
  ply: number;
  /** The move that led here; null for the root. */
  move: Move | null;
  fen: string;
  /** Ready-to-send PositionRef (start FEN + full history) for this node. */
  position: PositionRef;
  /** Child ids; the first is the main continuation. */
  children: string[];
  comment: string | null;
  nags: number[];
}

export interface GameHeaders {
  [tag: string]: string;
}

interface GameTreeState {
  nodes: Record<string, TreeNode>;
  currentId: string;
  headers: GameHeaders;
  result: string;
  /** Bumped whenever a whole new game or position is loaded. */
  gameVersion: number;

  reset: (startFen?: string, headers?: GameHeaders) => void;
  loadGame: (game: GameResponse) => void;
  /** Adds a move under `parentId` (or reuses an identical child) and makes it current. */
  addMove: (parentId: string, move: Move, position: PositionRef, fen: string) => string;
  goTo: (id: string) => void;
  next: () => void;
  prev: () => void;
  start: () => void;
  end: () => void;
  deleteNode: (id: string) => void;
  promoteToMainline: (id: string) => void;
}

let counter = 0;
const newId = () => `u${++counter}`;

function rootNode(startFen: string): TreeNode {
  return {
    id: ROOT_ID,
    parentId: null,
    ply: 0,
    move: null,
    fen: startFen,
    position: { start_fen: startFen, moves: [] },
    children: [],
    comment: null,
    nags: [],
  };
}

export const useGameTree = create<GameTreeState>()((set, get) => ({
  nodes: { [ROOT_ID]: rootNode(STARTPOS) },
  currentId: ROOT_ID,
  headers: {},
  result: "*",
  gameVersion: 0,

  reset: (startFen = STARTPOS, headers = {}) =>
    set((s) => ({
      nodes: { [ROOT_ID]: rootNode(startFen) },
      currentId: ROOT_ID,
      headers,
      result: "*",
      gameVersion: s.gameVersion + 1,
    })),

  loadGame: (game) =>
    set((s) => {
      const root = rootNode(game.start_fen);
      const nodes: Record<string, TreeNode> = { [ROOT_ID]: root };
      for (const n of game.nodes) {
        nodes[n.id] = {
          id: n.id,
          parentId: n.parent_id ?? ROOT_ID,
          ply: n.ply,
          move: n.move,
          fen: n.fen_after,
          position: n.position,
          children: [...n.children],
          comment: n.comment,
          nags: n.nags,
        };
        if (n.parent_id === null) root.children.push(n.id);
      }
      // /v1/game lists root moves in PGN order; make sure the mainline move comes first.
      const first = game.mainline[0];
      if (first) root.children = [first, ...root.children.filter((c) => c !== first)];
      return { nodes, currentId: ROOT_ID, headers: game.headers, result: game.result, gameVersion: s.gameVersion + 1 };
    }),

  addMove: (parentId, move, position, fen) => {
    const { nodes } = get();
    const parent = nodes[parentId];
    const existing = parent.children.find((c) => nodes[c].move?.uci === move.uci);
    if (existing) {
      set({ currentId: existing });
      return existing;
    }
    const id = newId();
    const node: TreeNode = {
      id,
      parentId,
      ply: parent.ply + 1,
      move,
      fen,
      position,
      children: [],
      comment: null,
      nags: [],
    };
    set({
      nodes: { ...nodes, [id]: node, [parentId]: { ...parent, children: [...parent.children, id] } },
      currentId: id,
    });
    return id;
  },

  goTo: (id) => get().nodes[id] && set({ currentId: id }),
  next: () => {
    const { nodes, currentId } = get();
    const child = nodes[currentId].children[0];
    if (child) set({ currentId: child });
  },
  prev: () => {
    const { nodes, currentId } = get();
    const parent = nodes[currentId].parentId;
    if (parent) set({ currentId: parent });
  },
  start: () => set({ currentId: ROOT_ID }),
  end: () => {
    const { nodes } = get();
    let id = get().currentId;
    while (nodes[id].children.length) id = nodes[id].children[0];
    set({ currentId: id });
  },

  deleteNode: (id) => {
    if (id === ROOT_ID) return;
    const { nodes, currentId } = get();
    const target = nodes[id];
    const doomed = new Set<string>();
    const stack = [id];
    while (stack.length) {
      const x = stack.pop()!;
      doomed.add(x);
      stack.push(...nodes[x].children);
    }
    const next: Record<string, TreeNode> = {};
    for (const [k, v] of Object.entries(nodes)) if (!doomed.has(k)) next[k] = v;
    const parent = nodes[target.parentId!];
    next[parent.id] = { ...parent, children: parent.children.filter((c) => c !== id) };
    set({ nodes: next, currentId: doomed.has(currentId) ? parent.id : currentId });
  },

  promoteToMainline: (id) => {
    const nodes = { ...get().nodes };
    let child = id;
    let parentId = nodes[child].parentId;
    while (parentId) {
      const p = nodes[parentId];
      if (p.children[0] !== child) nodes[parentId] = { ...p, children: [child, ...p.children.filter((c) => c !== child)] };
      child = parentId;
      parentId = nodes[parentId].parentId;
    }
    set({ nodes });
  },
}));

// ---------- selectors / helpers ----------

export function pathTo(nodes: Record<string, TreeNode>, id: string): TreeNode[] {
  const out: TreeNode[] = [];
  let n: TreeNode | undefined = nodes[id];
  while (n) {
    out.push(n);
    n = n.parentId ? nodes[n.parentId] : undefined;
  }
  return out.reverse();
}

export function isMainline(nodes: Record<string, TreeNode>, id: string): boolean {
  let n = nodes[id];
  while (n.parentId) {
    const p = nodes[n.parentId];
    if (p.children[0] !== n.id) return false;
    n = p;
  }
  return true;
}

/** Fullmove number and side for the move that produced `node`, given the root FEN. */
export function moveNumber(rootFen: string, ply: number): { number: number; white: boolean } {
  const parts = rootFen.split(" ");
  const blackStarts = parts[1] === "b";
  const startFull = Number(parts[5] ?? 1) || 1;
  const offset = ply - 1 + (blackStarts ? 1 : 0); // half-moves since white's move of startFull
  return { number: startFull + Math.floor(offset / 2), white: offset % 2 === 0 };
}

export const useCurrentNode = () => useGameTree((s) => s.nodes[s.currentId]);
