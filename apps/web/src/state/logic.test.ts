import { beforeEach, describe, expect, it } from "vitest";
import type { GameResponse } from "@schema";
import gameExample from "../../../../packages/analysis-schema/examples/22-game-with-variation.json";
import { formatScore, localPosition, materialDiff, winChance } from "@/lib/chess";
import { editorFen, pieceAt, possibleCastling } from "./editor";
import { isMainline, moveNumber, pathTo, ROOT_ID, useGameTree } from "./gameTree";

const game = gameExample.response as unknown as GameResponse;

describe("game tree from /v1/game (contract example 22)", () => {
  beforeEach(() => useGameTree.getState().loadGame(game));

  it("keeps the mainline first and the variation as a sibling", () => {
    const { nodes } = useGameTree.getState();
    const sans: string[] = [];
    let id = nodes[ROOT_ID].children[0];
    while (id) {
      sans.push(nodes[id].move!.san);
      id = nodes[id].children[0];
    }
    expect(sans).toEqual(["e4", "e5", "Bc4", "Nc6", "Qh5", "Nf6", "Qxf7#"]);
    const g6 = Object.values(nodes).find((n) => n.move?.san === "g6")!;
    expect(isMainline(nodes, g6.id)).toBe(false);
    expect(nodes[g6.parentId!].children[0]).not.toBe(g6.id);
    expect(g6.comment).toMatch(/defends f7/);
  });

  it("navigates and promotes a variation to the main line", () => {
    const s = useGameTree.getState();
    s.end();
    expect(useGameTree.getState().nodes[useGameTree.getState().currentId].move!.san).toBe("Qxf7#");
    const g6 = Object.values(s.nodes).find((n) => n.move?.san === "g6")!;
    s.promoteToMainline(g6.id);
    const { nodes } = useGameTree.getState();
    expect(isMainline(nodes, g6.id)).toBe(true);
    expect(pathTo(nodes, g6.id).map((n) => n.move?.san ?? "root")).toEqual(["root", "e4", "e5", "Bc4", "Nc6", "Qh5", "g6"]);
  });

  it("deletes a subtree and moves the cursor out of it", () => {
    const s = useGameTree.getState();
    s.end();
    const nf6 = Object.values(s.nodes).find((n) => n.move?.san === "Nf6")!;
    s.deleteNode(nf6.id);
    const { nodes, currentId } = useGameTree.getState();
    expect(Object.values(nodes).some((n) => n.move?.san === "Qxf7#")).toBe(false);
    expect(nodes[currentId].move!.san).toBe("Qh5");
  });

  it("reuses an existing child instead of duplicating a move", () => {
    const s = useGameTree.getState();
    const e4 = s.nodes[ROOT_ID].children[0];
    const before = Object.keys(s.nodes).length;
    const id = s.addMove(ROOT_ID, { uci: "e2e4", san: "e4" }, s.nodes[e4].position, s.nodes[e4].fen);
    expect(id).toBe(e4);
    expect(Object.keys(useGameTree.getState().nodes).length).toBe(before);
  });
});

describe("move numbers", () => {
  const start = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
  it("counts from the start FEN", () => {
    expect(moveNumber(start, 1)).toEqual({ number: 1, white: true });
    expect(moveNumber(start, 2)).toEqual({ number: 1, white: false });
    expect(moveNumber(start, 3)).toEqual({ number: 2, white: true });
  });
  it("handles a set-up position with Black to move", () => {
    const fen = "4k3/8/8/8/8/8/8/4K3 b - - 0 40";
    expect(moveNumber(fen, 1)).toEqual({ number: 40, white: false });
    expect(moveNumber(fen, 2)).toEqual({ number: 41, white: true });
  });
});

describe("position editor", () => {
  const start = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR";
  it("reads pieces from a placement", () => {
    expect(pieceAt(start, "e1")).toBe("K");
    expect(pieceAt(start, "d8")).toBe("q");
    expect(pieceAt(start, "e4")).toBeNull();
  });
  it("only offers castling rights the placement allows", () => {
    const noRookH1 = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBN1";
    expect(possibleCastling(noRookH1)).toEqual({ K: false, Q: true, k: true, q: true });
    expect(editorFen({ placement: noRookH1, turn: "w", castling: { K: true, Q: true, k: true, q: true } })).toBe(
      `${noRookH1} w Qkq - 0 1`,
    );
    expect(editorFen({ placement: "4k3/8/8/8/8/8/8/4K3", turn: "b", castling: { K: true, Q: true, k: true, q: true } })).toBe(
      "4k3/8/8/8/8/8/8/4K3 b - - 0 1",
    );
  });
});

describe("local helpers", () => {
  it("gives chess.js drag destinations and check state", () => {
    const p = localPosition("rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3");
    expect(p.ok).toBe(true);
    expect(p.inCheck).toBe(true);
    expect(p.dests.size).toBe(0); // fool's mate
  });
  it("computes the material difference", () => {
    expect(materialDiff("4k3/8/8/8/8/8/8/3QK3 w - - 0 1")).toEqual({ surplus: { q: 1, r: 0, b: 0, n: 0, p: 0 }, points: 9 });
  });
  it("formats White-POV scores", () => {
    expect(formatScore({ type: "cp", value: 35, pov: "white" })).toBe("+0.35");
    expect(formatScore({ type: "mate", value: -3, pov: "white" })).toBe("-M3");
    expect(winChance({ type: "cp", value: 0, pov: "white" })).toBeCloseTo(50);
    expect(winChance({ type: "mate", value: 2, pov: "white" })).toBe(100);
  });
});
