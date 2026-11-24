import { Box, Text, Tooltip } from "@mantine/core";
import type { Score } from "@schema";
import { formatScore, winChance } from "@/lib/chess";
import type { Orientation } from "@/state/settings";

interface Props {
  score: Score | null;
  orientation: Orientation;
  /** Shown in the tooltip, e.g. "mock engine" or "depth 18". */
  note?: string;
  /** Replaces the score text, e.g. "1-0" once the game is decided on the board. */
  result?: string;
}

/** Vertical evaluation bar (White's point of view), styled after En Croissant's. */
export function EvalBar({ score, orientation, note, result }: Props) {
  const white = score ? winChance(score) : 50;
  const label = result ?? (score ? formatScore(score, 1).replace(/^[+-]/, "") : "");
  const whiteAhead = score ? (score.type === "mate" ? score.value > 0 : score.value >= 0) : true;

  const blackPart = (
    <Box key="b" className="eval-part eval-black" style={{ height: `${100 - white}%` }}>
      {score && !whiteAhead && (
        <Text fz={10} fw={600} ta="center" py={3} mt={orientation === "black" ? "auto" : undefined} c="gray.2">
          {label}
        </Text>
      )}
    </Box>
  );
  const whitePart = (
    <Box key="w" className="eval-part eval-white" style={{ height: `${white}%` }}>
      {score && whiteAhead && (
        <Text fz={10} fw={600} ta="center" py={3} mt={orientation === "white" ? "auto" : undefined} c="dark.8">
          {label}
        </Text>
      )}
    </Box>
  );
  const parts = orientation === "white" ? [blackPart, whitePart] : [whitePart, blackPart];

  return (
    <Tooltip
      position="right"
      disabled={!score}
      label={result ?? (score ? `${formatScore(score)}${note ? ` · ${note}` : ""}` : undefined)}
    >
      <Box className="eval-bar" aria-label={score ? `Evaluation ${formatScore(score)}` : "No evaluation"}>
        {parts}
      </Box>
    </Tooltip>
  );
}
