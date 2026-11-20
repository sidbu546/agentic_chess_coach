import { ActionIcon, Badge, Box, Button, Group, SegmentedControl, Switch, Text, Tooltip, UnstyledButton } from "@mantine/core";
import {
  IconPlayerPauseFilled,
  IconPlayerPlayFilled,
  IconPlayerSkipBackFilled,
  IconPlayerSkipForwardFilled,
  IconPlayerTrackNextFilled,
  IconPlayerTrackPrevFilled,
  IconPlus,
  IconX,
} from "@tabler/icons-react";
import { useEffect, useRef } from "react";
import { useHealth } from "@/panels/InfoPanel";
import { useGameTree } from "@/state/gameTree";
import { moveLabel, useLinePlayer } from "@/state/linePlayer";

const SPEEDS = [
  { value: "2", label: "Slow" },
  { value: "1.2", label: "Normal" },
  { value: "0.6", label: "Fast" },
];

/** Playback controls for a coach line, shown under the board in place of the board toolbar. */
export function LinePlayerBar() {
  const { line, startNodeId, index, playing, speed, ideas } = useLinePlayer();
  const { go, step, setPlaying, setSpeed, setIdeas, close, addToGame } = useLinePlayer.getState();
  const currentId = useGameTree((s) => s.currentId);
  const health = useHealth();
  const engineReal = !!health.data && health.data.data.engine?.name !== "mock";
  const movesRef = useRef<HTMLDivElement>(null);

  // Autoplay: one move every `speed` seconds, stop at the end.
  useEffect(() => {
    if (!playing || !line) return;
    if (index >= line.steps.length) {
      setPlaying(false);
      return;
    }
    const t = setTimeout(() => go(index + 1), speed * 1000);
    return () => clearTimeout(t);
  }, [playing, index, speed, line, go, setPlaying]);

  // Navigating the game elsewhere (notation, arrows) ends the playback.
  useEffect(() => {
    if (line && startNodeId && currentId !== startNodeId) close();
  }, [currentId, line, startNodeId, close]);

  useEffect(() => {
    movesRef.current?.querySelector("[data-current]")?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [index]);

  if (!line) return null;
  const n = line.steps.length;
  const last = line.steps[n - 1];
  const result =
    last.state === "checkmate"
      ? `Checkmate · ${last.winner === "white" ? "White" : "Black"} wins`
      : last.state !== "ongoing"
        ? "Draw"
        : null;

  return (
    <Box className="line-player">
      <Group gap={6} wrap="nowrap" className="line-moves" ref={movesRef}>
        {line.steps.map((s, i) => {
          const label = moveLabel(line.start_fen, i, s.san);
          const showNumber = i === 0 || !label.includes("...");
          return (
            <UnstyledButton
              key={i}
              className="line-move"
              data-current={index === i + 1 || undefined}
              data-done={index > i + 1 || undefined}
              onClick={() => {
                go(i + 1);
                setPlaying(false);
              }}
            >
              {showNumber ? label : s.san}
            </UnstyledButton>
          );
        })}
        {result && (
          <Badge size="sm" color={last.state === "checkmate" ? "red" : "gray"} variant="light" style={{ flexShrink: 0 }}>
            {result}
          </Badge>
        )}
      </Group>

      <Group justify="space-between" gap={6} mt={6} wrap="wrap">
        <Group gap={2} wrap="nowrap">
          <Ctl label="Start (↑)" onClick={() => go(0)} disabled={index === 0}>
            <IconPlayerSkipBackFilled size={14} />
          </Ctl>
          <Ctl label="Back (←)" onClick={() => step(-1)} disabled={index === 0}>
            <IconPlayerTrackPrevFilled size={14} />
          </Ctl>
          <Ctl label={playing ? "Pause (space)" : "Play (space)"} onClick={() => setPlaying(!playing)} filled>
            {playing ? <IconPlayerPauseFilled size={16} /> : <IconPlayerPlayFilled size={16} />}
          </Ctl>
          <Ctl label="Forward (→)" onClick={() => step(1)} disabled={index >= n}>
            <IconPlayerTrackNextFilled size={14} />
          </Ctl>
          <Ctl label="End (↓)" onClick={() => go(n)} disabled={index >= n}>
            <IconPlayerSkipForwardFilled size={14} />
          </Ctl>
          <Text size="xs" c="dimmed" ml={6}>
            {index}/{n}
          </Text>
        </Group>
        <SegmentedControl size="xs" value={String(speed)} onChange={(v) => setSpeed(Number(v))} data={SPEEDS} />
        <Group gap={8} wrap="nowrap">
          <Tooltip
            label={engineReal ? "Show the engine's top moves in each position" : "Needs a real engine (the chess API is running the mock)"}
            multiline
            maw={220}
          >
            <span>
              <Switch size="xs" label="Engine ideas" checked={ideas && engineReal} disabled={!engineReal} onChange={(e) => setIdeas(e.currentTarget.checked)} />
            </span>
          </Tooltip>
          <Tooltip label="Add the moves shown so far to your game">
            <Button size="compact-xs" variant="light" leftSection={<IconPlus size={12} />} onClick={() => addToGame(index || n)}>
              Add to game
            </Button>
          </Tooltip>
          <Tooltip label="Close (Esc)">
            <ActionIcon size="sm" variant="subtle" color="gray" onClick={close} aria-label="Close line">
              <IconX size={14} />
            </ActionIcon>
          </Tooltip>
        </Group>
      </Group>
      <Text size="xs" c="dimmed" mt={4}>
        Pause anywhere and move a piece to try your own idea from that position.
      </Text>
    </Box>
  );
}

function Ctl({
  label,
  onClick,
  disabled,
  filled,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  filled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <Tooltip label={label}>
      <ActionIcon size="md" variant={filled ? "filled" : "subtle"} onClick={onClick} disabled={disabled} aria-label={label}>
        {children}
      </ActionIcon>
    </Tooltip>
  );
}
