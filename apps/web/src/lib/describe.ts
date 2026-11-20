import type { ChessFact, Piece } from "@schema";

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
export const pieceName = (p: Piece) => `${p.color} ${p.type} ${p.square}`;

/** Plain-language one-liner for a fact from /v1/position. Unknown kinds return null (contract: ignore them). */
export function describeFact(f: ChessFact): { title: string; detail: string } | null {
  switch (f.kind) {
    case "check":
      return { title: "Check", detail: `${cap(pieceName(f.checker))} checks the ${f.king.color} king on ${f.king.square}` };
    case "pin":
      return {
        title: f.absolute ? "Absolute pin" : "Relative pin",
        detail: `${cap(pieceName(f.pinned))} is pinned to the ${f.shielded.type} on ${f.shielded.square} by the ${f.pinner.type} on ${f.pinner.square}`,
      };
    case "xray":
      return {
        title: "X-ray",
        detail: `${cap(pieceName(f.attacker))} looks through its ${f.blocker.type} on ${f.blocker.square} at the ${f.target.color} ${f.target.type} on ${f.target.square}`,
      };
    case "hanging":
      return {
        title: "Hanging piece",
        detail: `${cap(pieceName(f.piece))} is undefended and attacked by ${f.attackers.map((a) => `${a.type} ${a.square}`).join(", ")}`,
      };
    case "open_file":
      return { title: "Open file", detail: `The ${f.file}-file has no pawns` };
    case "semi_open_file":
      return { title: "Semi-open file", detail: `The ${f.file}-file is semi-open for ${f.open_for}` };
    default:
      return null;
  }
}
