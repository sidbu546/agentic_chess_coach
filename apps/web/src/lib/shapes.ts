import type { DrawShape } from "@lichess-org/chessground/draw";
import type { Key } from "@lichess-org/chessground/types";
import type { CandidateLine, ChessFact } from "@schema";
import type { BoardAnnotations } from "@/coach/types";
import { winChance } from "./chess";

const k = (s: string) => s as Key;

/** Board shapes that illustrate one fact from /v1/position (shown while hovering it). */
export function factShapes(fact: ChessFact): DrawShape[] {
  switch (fact.kind) {
    case "check":
      return [{ orig: k(fact.checker.square), dest: k(fact.king.square), brush: "red" }];
    case "pin":
      return [
        { orig: k(fact.pinner.square), dest: k(fact.shielded.square), brush: "red" },
        { orig: k(fact.pinned.square), brush: "yellow" },
      ];
    case "xray":
      return [
        { orig: k(fact.attacker.square), dest: k(fact.target.square), brush: "blue" },
        { orig: k(fact.blocker.square), brush: "yellow" },
      ];
    case "hanging":
      return [
        { orig: k(fact.piece.square), brush: "red" },
        ...fact.attackers.map((a) => ({ orig: k(a.square), dest: k(fact.piece.square), brush: "paleRed" })),
      ];
    case "open_file":
    case "semi_open_file":
      return [{ orig: k(`${fact.file}1`), dest: k(`${fact.file}8`), brush: "paleGreen" }];
    default:
      return []; // clients ignore fact kinds they don't know (contract rule)
  }
}

// Same palette order as En Croissant's best-move arrows.
const LINE_BRUSHES = [
  { strong: "blue", pale: "paleBlue" },
  { strong: "green", pale: "paleGreen" },
  { strong: "red", pale: "paleRed" },
  { strong: "yellow", pale: "paleGrey" },
  { strong: "yellow", pale: "paleGrey" },
];

/** First-move arrows for the engine's candidate lines, thicker for moves close to the best. */
export function engineShapes(candidates: CandidateLine[], sideToMove: "white" | "black"): DrawShape[] {
  if (!candidates.length) return [];
  const forMover = (c: CandidateLine) => {
    const w = winChance(c.score);
    return sideToMove === "white" ? w : 100 - w;
  };
  const best = forMover(candidates[0]);
  return candidates.slice(0, 4).map((c, i) => {
    const gap = best - forMover(c);
    const lineWidth = gap < 2.5 ? 11 : gap < 5 ? 7.5 : 4;
    return {
      orig: k(c.move.uci.slice(0, 2)),
      dest: k(c.move.uci.slice(2, 4)),
      brush: i === 0 ? LINE_BRUSHES[0].strong : LINE_BRUSHES[i].pale,
      modifiers: { lineWidth },
    };
  });
}

/** A whole principal variation as numbered arrows (hover preview of an engine line). */
export function lineShapes(ucis: string[], max = 6): DrawShape[] {
  return ucis.slice(0, max).map((u, i) => ({
    orig: k(u.slice(0, 2)),
    dest: k(u.slice(2, 4)),
    brush: i % 2 === 0 ? "blue" : "paleBlue",
    label: { text: String(i + 1) },
  }));
}

export function coachShapes(a: BoardAnnotations | undefined): DrawShape[] {
  if (!a) return [];
  return [
    ...a.arrows.map((x) => ({ orig: k(x.from), dest: k(x.to), brush: x.color })),
    ...a.highlights.map((x) => ({ orig: k(x.square), brush: x.color })),
  ];
}
