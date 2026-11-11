import { Alert, Badge, Box, Group, Loader, ScrollArea, SegmentedControl, Select, Stack, Switch, Text, Tooltip } from "@mantine/core";
import { IconAlertTriangle, IconFlask } from "@tabler/icons-react";
import type { CandidateLine } from "@schema";
import { ChessApiError } from "@/api/chessApi";
import { useAnalysis, usePositionInfo } from "@/api/hooks";
import { formatScore } from "@/lib/chess";
import { describeFact } from "@/lib/describe";
import { factShapes, lineShapes } from "@/lib/shapes";
import { playLine } from "@/state/actions";
import { moveNumber, ROOT_ID, useCurrentNode, useGameTree } from "@/state/gameTree";
import { useUi } from "@/state/ui";

export function AnalysisPanel() {
  const node = useCurrentNode();
  const rootFen = useGameTree((s) => s.nodes[ROOT_ID].fen);
  const { engineOn, multipv, depth, set } = useUi();
  const analysis = useAnalysis(node.position);
  const info = usePositionInfo(node.position);

  const result = analysis.data?.data;
  const engine = result?.analysis.engine;
  const isMock = engine?.name === "mock" || analysis.data?.source === "fake";
  const hover = (shapes: ReturnType<typeof lineShapes>) => set({ hoverShapes: shapes });
  const unhover = () => set({ hoverShapes: [] });

  return (
    <ScrollArea className="tab-scroll" type="auto" offsetScrollbars>
      <Stack gap="sm" p="xs">
        <Group justify="space-between" wrap="nowrap">
          <Group gap="xs" wrap="nowrap">
            <Switch checked={engineOn} onChange={(e) => set({ engineOn: e.currentTarget.checked })} label="Engine" size="sm" />
            {engine && (
              <Tooltip
                label={isMock ? "Mock server: scores are placeholders until the real chess service is connected" : `${engine.name} ${engine.version}`}
              >
                <Badge variant="light" color={isMock ? "orange" : "blue"} leftSection={isMock ? <IconFlask size={12} /> : undefined}>
                  {isMock ? "mock engine" : engine.name}
                </Badge>
              </Tooltip>
            )}
            {analysis.loading && engineOn && <Loader size="xs" />}
          </Group>
          <Group gap="xs" wrap="nowrap">
            <Select
              aria-label="Search depth"
              size="xs"
              w={90}
              data={["10", "14", "16", "18", "22"].map((d) => ({ value: d, label: `depth ${d}` }))}
              value={String(depth)}
              onChange={(v) => v && set({ depth: Number(v) })}
              allowDeselect={false}
            />
            <SegmentedControl
              aria-label="Number of lines"
              size="xs"
              data={["1", "2", "3", "4", "5"]}
              value={String(multipv)}
              onChange={(v) => set({ multipv: Number(v) })}
            />
          </Group>
        </Group>

        {engineOn && analysis.error != null && <ApiErrorAlert error={analysis.error} />}

        {engineOn && result && (
          <Box className="engine-lines">
            {result.analysis.candidates.length === 0 && (
              <Text size="sm" c="dimmed">
                No moves: the game is over.
              </Text>
            )}
            {result.analysis.candidates.map((c) => (
              <EngineLine
                key={c.rank}
                line={c}
                startPly={node.ply}
                rootFen={rootFen}
                onHover={() => hover(lineShapes(c.pv.map((m) => m.uci)))}
                onLeave={unhover}
              />
            ))}
            {result && (
              <Text size="xs" c="dimmed" mt={4}>
                depth {result.analysis.depth} · {result.analysis.nodes.toLocaleString()} nodes · {result.analysis.time_ms} ms
              </Text>
            )}
          </Box>
        )}

        <Text fw={600} size="sm" mt="xs">
          On the board
        </Text>
        {info.error != null && <ApiErrorAlert error={info.error} />}
        {info.data && (
          <Stack gap={4}>
            {info.data.data.facts.length === 0 && (
              <Text size="sm" c="dimmed">
                No pins, checks, x-rays, hanging pieces or open files.
              </Text>
            )}
            {info.data.data.facts.map((f, i) => {
              const d = describeFact(f);
              if (!d) return null;
              return (
                <Box key={i} className="fact-row" onMouseEnter={() => hover(factShapes(f))} onMouseLeave={unhover}>
                  <Badge size="xs" variant="light" color={factColor(f.kind)} mr={8}>
                    {d.title}
                  </Badge>
                  <Text span size="sm">
                    {d.detail}
                  </Text>
                </Box>
              );
            })}
            <Text size="xs" c="dimmed" mt={4}>
              Material {info.data.data.material.balance_cp >= 0 ? "+" : ""}
              {(info.data.data.material.balance_cp / 100).toFixed(0)} for White · {info.data.data.legal_moves.length} legal moves
            </Text>
          </Stack>
        )}
      </Stack>
    </ScrollArea>
  );
}

function factColor(kind: string) {
  return kind === "check" || kind === "hanging" ? "red" : kind === "pin" ? "yellow" : kind === "xray" ? "blue" : "green";
}

function EngineLine({
  line,
  startPly,
  rootFen,
  onHover,
  onLeave,
}: {
  line: CandidateLine;
  startPly: number;
  rootFen: string;
  onHover: () => void;
  onLeave: () => void;
}) {
  const white = line.score.type === "mate" ? line.score.value > 0 : line.score.value >= 0;
  return (
    <Group className="engine-line" gap={8} wrap="nowrap" onMouseEnter={onHover} onMouseLeave={onLeave}>
      <Box className={`score-chip ${white ? "score-white" : "score-black"}`}>{formatScore(line.score)}</Box>
      <Text size="sm" className="pv" lineClamp={1}>
        {line.pv.map((m, i) => {
          const mn = moveNumber(rootFen, startPly + i + 1);
          return (
            <span key={i}>
              {(mn.white || i === 0) && (
                <span className="move-number">
                  {mn.number}
                  {mn.white ? "." : "..."}
                </span>
              )}
              <button type="button" className="pv-move" onClick={() => playLine(line.pv.slice(0, i + 1).map((x) => x.uci))}>
                {m.san}
              </button>{" "}
            </span>
          );
        })}
      </Text>
    </Group>
  );
}

export function ApiErrorAlert({ error }: { error: unknown }) {
  const e = error as ChessApiError;
  return (
    <Alert color="red" variant="light" icon={<IconAlertTriangle size={16} />} p="xs">
      <Text size="sm">{e?.message ?? "Request failed"}</Text>
      {e?.code === "network" && (
        <Text size="xs" c="dimmed" mt={4}>
          Start the mock: <code>python packages/analysis-schema/mock/server.py</code>
        </Text>
      )}
    </Alert>
  );
}
