import type { Key } from "@lichess-org/chessground/types";
import type { Orientation, PieceSet } from "@/state/settings";

const CHOICES = [
  { role: "q", name: "Queen", file: "Q" },
  { role: "n", name: "Knight", file: "N" },
  { role: "r", name: "Rook", file: "R" },
  { role: "b", name: "Bishop", file: "B" },
] as const;

interface Props {
  dest: Key;
  color: "white" | "black";
  orientation: Orientation;
  pieceSet: PieceSet;
  onPick: (role: "q" | "n" | "r" | "b") => void;
  onCancel: () => void;
}

/** Lichess-style promotion column dropped over the promotion square. */
export function PromotionPicker({ dest, color, orientation, pieceSet, onPick, onCancel }: Props) {
  const file = dest.charCodeAt(0) - 97;
  const col = orientation === "white" ? file : 7 - file;
  // The promotion rank is at the top of the screen when the promoting side is at the bottom.
  const fromTop = color === orientation;
  const prefix = color === "white" ? "w" : "b";

  return (
    <div className="promotion-overlay" onClick={onCancel} onContextMenu={(e) => (e.preventDefault(), onCancel())}>
      {CHOICES.map((c, i) => (
        <button
          key={c.role}
          type="button"
          className="promotion-choice"
          aria-label={`Promote to ${c.name}`}
          style={{
            left: `${col * 12.5}%`,
            [fromTop ? "top" : "bottom"]: `${i * 12.5}%`,
            backgroundImage: `url(/pieces/${pieceSet}/${prefix}${c.file}.svg)`,
          }}
          onClick={(e) => {
            e.stopPropagation();
            onPick(c.role);
          }}
        />
      ))}
    </div>
  );
}
