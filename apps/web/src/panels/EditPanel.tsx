import type { Color, Role } from "@lichess-org/chessground/types";
import { Alert, Button, Checkbox, Group, Paper, SegmentedControl, Stack, Text, TextInput, Tooltip, UnstyledButton } from "@mantine/core";
import { IconClick, IconEraser } from "@tabler/icons-react";
import { useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { boardApi } from "@/board/boardApi";
import { loadFen } from "@/state/actions";
import { editorFen, EMPTY_PLACEMENT, possibleCastling, START_PLACEMENT, useEditor, type EditTool } from "@/state/editor";
import { useSettings } from "@/state/settings";
import { useUi } from "@/state/ui";

const ROLES: { role: Role; file: string }[] = [
  { role: "king", file: "K" },
  { role: "queen", file: "Q" },
  { role: "rook", file: "R" },
  { role: "bishop", file: "B" },
  { role: "knight", file: "N" },
  { role: "pawn", file: "P" },
];

/** Position setup, shown in place of the tabs while the board is in edit mode (as in En Croissant). */
export function EditPanel() {
  const ed = useEditor(
    useShallow((s) => ({ placement: s.placement, turn: s.turn, castling: s.castling, tool: s.tool })),
  );
  const { setTurn, setCastling, setTool, setPlacement } = useEditor.getState();
  const pieceSet = useSettings((s) => s.pieceSet);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [fenDraft, setFenDraft] = useState<string | null>(null);
  const fen = editorFen(ed);
  const possible = possibleCastling(ed.placement);

  const same = (a: EditTool, b: EditTool) =>
    a === b || (typeof a === "object" && typeof b === "object" && a?.role === b?.role && a?.color === b?.color);

  const spare = (color: Color) => (
    <Group gap={4} wrap="nowrap">
      {ROLES.map(({ role, file }) => {
        const tool = { color, role };
        return (
          <UnstyledButton
            key={role}
            className="spare-piece"
            data-active={same(ed.tool, tool) || undefined}
            aria-label={`${color} ${role}`}
            style={{ backgroundImage: `url(/pieces/${pieceSet}/${color[0]}${file}.svg)` }}
            onClick={() => setTool(same(ed.tool, tool) ? null : tool)}
            onMouseDown={(e) => {
              // Drag a new piece straight onto the board.
              if (e.button === 0 && boardApi.current && !same(ed.tool, tool)) {
                setTool(null);
                boardApi.current.dragNewPiece({ color, role }, e.nativeEvent, true);
              }
            }}
            onTouchStart={(e) => boardApi.current?.dragNewPiece({ color, role }, e.nativeEvent, true)}
          />
        );
      })}
    </Group>
  );

  const finish = async () => {
    setSaving(true);
    setError(null);
    try {
      await loadFen(fen); // the chess API validates it (kings, side not to move in check, castling…)
      useUi.getState().set({ editing: false });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const applyFenDraft = () => {
    if (fenDraft === null) return;
    const [placement] = fenDraft.trim().split(/\s+/);
    if (/^([pnbrqkPNBRQK1-8]+\/){7}[pnbrqkPNBRQK1-8]+$/.test(placement)) {
      useEditor.getState().begin(fenDraft.trim().split(/\s+/).length > 1 ? fenDraft.trim() : `${placement} w - - 0 1`);
      setError(null);
    } else setError("That doesn't look like a FEN board.");
    setFenDraft(null);
  };

  return (
    <Paper className="panel edit-panel" withBorder p="sm">
      <Stack gap="sm">
        <Text fw={600}>Set up a position</Text>
        <Text size="xs" c="dimmed">
          Drag pieces on the board, drag them off to remove, or pick a piece below and click squares to place it.
        </Text>
        {spare("white")}
        {spare("black")}
        <Group gap={4}>
          <Tooltip label="Move pieces">
            <Button
              size="xs"
              variant={ed.tool === null ? "filled" : "default"}
              leftSection={<IconClick size={14} />}
              onClick={() => setTool(null)}
            >
              Move
            </Button>
          </Tooltip>
          <Tooltip label="Click squares to clear them">
            <Button
              size="xs"
              variant={ed.tool === "trash" ? "filled" : "default"}
              leftSection={<IconEraser size={14} />}
              onClick={() => setTool(ed.tool === "trash" ? null : "trash")}
            >
              Erase
            </Button>
          </Tooltip>
          <Button size="xs" variant="default" onClick={() => setPlacement(START_PLACEMENT)}>
            Start position
          </Button>
          <Button size="xs" variant="default" onClick={() => setPlacement(EMPTY_PLACEMENT)}>
            Clear
          </Button>
        </Group>

        <Group justify="space-between" align="center">
          <Text size="sm">Side to move</Text>
          <SegmentedControl
            size="xs"
            value={ed.turn}
            onChange={(v) => setTurn(v as "w" | "b")}
            data={[
              { value: "w", label: "White" },
              { value: "b", label: "Black" },
            ]}
          />
        </Group>

        <Stack gap={6}>
          <Text size="sm">Castling</Text>
          <Group gap="lg">
            {(
              [
                ["K", "White O-O"],
                ["Q", "White O-O-O"],
                ["k", "Black O-O"],
                ["q", "Black O-O-O"],
              ] as const
            ).map(([c, label]) => (
              <Checkbox
                key={c}
                size="xs"
                label={label}
                disabled={!possible[c]}
                checked={ed.castling[c] && possible[c]}
                onChange={(e) => setCastling({ [c]: e.currentTarget.checked })}
              />
            ))}
          </Group>
        </Stack>

        <TextInput
          label="FEN"
          size="xs"
          value={fenDraft ?? fen}
          onChange={(e) => setFenDraft(e.currentTarget.value)}
          onBlur={applyFenDraft}
          onKeyDown={(e) => e.key === "Enter" && applyFenDraft()}
          styles={{ input: { fontFamily: "var(--mantine-font-family-monospace)" } }}
        />

        {error && (
          <Alert color="red" variant="light" p="xs">
            <Text size="sm">{error}</Text>
          </Alert>
        )}

        <Group justify="flex-end" gap="xs">
          <Button variant="default" size="sm" onClick={() => useUi.getState().set({ editing: false })}>
            Cancel
          </Button>
          <Button size="sm" loading={saving} onClick={finish}>
            Analyse this position
          </Button>
        </Group>
      </Stack>
    </Paper>
  );
}
