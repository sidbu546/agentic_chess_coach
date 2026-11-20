import { describe, expect, it } from "vitest";
import type { CoachLine, LineStep } from "@/coach/types";
import { lineText, moveLabel } from "./linePlayer";

const step = (san: string): LineStep => ({ uci: "", san, fen: "", state: "ongoing", in_check: false, winner: null });
const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

describe("line numbering", () => {
  it("numbers a line from the start position", () => {
    const line: CoachLine = { title: "", start_fen: START, steps: ["e4", "e5", "Bc4", "Nc6", "Qh5", "Nf6", "Qxf7#"].map(step) };
    expect(lineText(line)).toBe("1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7#");
  });

  it("numbers a line that starts with Black to move", () => {
    const fen = "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2";
    const line: CoachLine = { title: "", start_fen: fen, steps: ["Nc6", "Bc4", "Nf6"].map(step) };
    expect(lineText(line)).toBe("2... Nc6 3. Bc4 Nf6");
    expect(moveLabel(fen, 1, "Bc4")).toBe("3. Bc4");
  });
});
