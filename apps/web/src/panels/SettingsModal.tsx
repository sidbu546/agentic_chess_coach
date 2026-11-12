import { Box, Group, Modal, SimpleGrid, Stack, Switch, Text, UnstyledButton } from "@mantine/core";
import { boardImage } from "@/board/boardApi";
import { BOARD_THEMES, PIECE_SETS, useSettings, type BoardTheme, type PieceSet } from "@/state/settings";
import { useUi } from "@/state/ui";

const TOGGLES = [
  ["showCoordinates", "Coordinates"],
  ["showDests", "Show legal moves"],
  ["highlightLastMove", "Highlight last move"],
  ["animation", "Piece animation"],
  ["showEvalBar", "Evaluation bar"],
  ["showEngineArrows", "Engine arrows"],
  ["scrollToNavigate", "Scroll on the board to move through the game"],
  ["autoQueen", "Always promote to a queen (Ctrl to choose)"],
] as const;

export function SettingsModal() {
  const opened = useUi((s) => s.settingsOpen);
  const s = useSettings();
  return (
    <Modal opened={opened} onClose={() => useUi.getState().set({ settingsOpen: false })} title="Board settings">
      <Stack gap="md">
        <Stack gap={6}>
          <Text size="sm" fw={600}>
            Board
          </Text>
          <SimpleGrid cols={5} spacing="xs">
            {(Object.keys(BOARD_THEMES) as BoardTheme[]).map((t) => (
              <UnstyledButton key={t} className="theme-swatch" data-active={s.boardTheme === t || undefined} onClick={() => s.set({ boardTheme: t })}>
                <Box className="theme-swatch-img" style={{ backgroundImage: boardImage(BOARD_THEMES[t].light, BOARD_THEMES[t].dark) }} />
                <Text size="xs" ta="center" mt={4}>
                  {BOARD_THEMES[t].label}
                </Text>
              </UnstyledButton>
            ))}
          </SimpleGrid>
        </Stack>
        <Stack gap={6}>
          <Text size="sm" fw={600}>
            Pieces
          </Text>
          <Group gap="xs">
            {(Object.keys(PIECE_SETS) as PieceSet[]).map((p) => (
              <UnstyledButton key={p} className="theme-swatch piece-swatch" data-active={s.pieceSet === p || undefined} onClick={() => s.set({ pieceSet: p })}>
                <Group gap={0} wrap="nowrap">
                  {["wN", "wQ", "bK", "bB"].map((f) => (
                    <img key={f} src={`/pieces/${p}/${f}.svg`} alt="" width={30} height={30} />
                  ))}
                </Group>
                <Text size="xs" ta="center">
                  {PIECE_SETS[p]}
                </Text>
              </UnstyledButton>
            ))}
          </Group>
        </Stack>
        <Stack gap={8}>
          {TOGGLES.map(([k, label]) => (
            <Switch key={k} label={label} checked={s[k]} onChange={(e) => s.set({ [k]: e.currentTarget.checked })} />
          ))}
        </Stack>
      </Stack>
    </Modal>
  );
}
