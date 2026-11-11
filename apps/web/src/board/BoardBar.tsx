import { Box, Group, Text } from "@mantine/core";
import type { ReactNode } from "react";
import { materialDiff, ROLE_ORDER } from "@/lib/chess";
import type { PieceSet } from "@/state/settings";

const ROLE_UPPER = { q: "Q", r: "R", b: "B", n: "N", p: "P" } as const;

/** Captured-material strip: the pieces this side is up, drawn with the board's piece set. */
export function MaterialStrip({ fen, color, pieceSet }: { fen: string; color: "white" | "black"; pieceSet: PieceSet }) {
  const { surplus, points } = materialDiff(fen);
  const sign = color === "white" ? 1 : -1;
  // Show the opponent's pieces this side has captured beyond equality, like lichess/En Croissant.
  const prefix = color === "white" ? "b" : "w";
  const icons: ReactNode[] = [];
  for (const role of ROLE_ORDER) {
    const n = surplus[role] * sign;
    for (let i = 0; i < n; i++) {
      icons.push(
        <img
          key={`${role}${i}`}
          src={`/pieces/${pieceSet}/${prefix}${ROLE_UPPER[role]}.svg`}
          alt=""
          className="captured-piece"
        />,
      );
    }
  }
  const lead = points * sign;
  return (
    <Group gap={0} wrap="nowrap" align="center">
      {icons}
      {lead > 0 && (
        <Text fz="sm" c="dimmed" ml={6} lh={1}>
          +{lead}
        </Text>
      )}
    </Group>
  );
}

interface BoardBarProps {
  name: string;
  rating?: string;
  toMove: boolean;
  colorDot: "white" | "black";
  children?: ReactNode;
}

export function BoardBar({ name, rating, toMove, colorDot, children }: BoardBarProps) {
  return (
    <Group className="board-bar" justify="space-between" wrap="nowrap" gap="xs">
      <Group gap={8} wrap="nowrap" style={{ minWidth: 0 }}>
        <Box className={`turn-dot turn-dot-${colorDot}`} data-active={toMove || undefined} />
        <Text fw={700} size="md" truncate>
          {name}
        </Text>
        {rating && (
          <Text size="xs" c="dimmed">
            ({rating})
          </Text>
        )}
      </Group>
      <Group gap="sm" wrap="nowrap">
        {children}
      </Group>
    </Group>
  );
}
