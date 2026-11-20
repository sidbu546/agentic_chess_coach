import { ActionIcon, Badge, CopyButton, Group, ScrollArea, Stack, Table, Text, TextInput, Tooltip } from "@mantine/core";
import { IconCheck, IconCopy, IconRefresh } from "@tabler/icons-react";
import { useState } from "react";
import { CHESS_API_URL, chessApi } from "@/api/chessApi";
import { useQuery } from "@/api/useQuery";
import { COACH_API_URL } from "@/coach/coachApi";
import { useCurrentNode, useGameTree } from "@/state/gameTree";

export function useHealth(nonce = 0) {
  return useQuery(`health:${nonce}`, () => chessApi.health());
}

export function InfoPanel() {
  const node = useCurrentNode();
  const headers = useGameTree((s) => s.headers);
  const [nonce, setNonce] = useState(0);
  const health = useHealth(nonce);
  const tags = Object.entries(headers).filter(([, v]) => v && v !== "?" && v !== "????.??.??");

  return (
    <ScrollArea className="tab-scroll" type="auto" offsetScrollbars>
      <Stack gap="md" p="xs">
        <Stack gap={4}>
          <Text fw={600} size="sm">
            Position
          </Text>
          <TextInput
            readOnly
            value={node.fen}
            size="xs"
            styles={{ input: { fontFamily: "var(--mantine-font-family-monospace)" } }}
            rightSection={
              <CopyButton value={node.fen}>
                {({ copied, copy }) => (
                  <ActionIcon variant="subtle" color={copied ? "teal" : "gray"} onClick={copy} aria-label="Copy FEN">
                    {copied ? <IconCheck size={14} /> : <IconCopy size={14} />}
                  </ActionIcon>
                )}
              </CopyButton>
            }
          />
          <Text size="xs" c="dimmed">
            Sent to the API as start FEN + {node.position.moves.length} move{node.position.moves.length === 1 ? "" : "s"}, so repetition
            can be detected.
          </Text>
        </Stack>

        {tags.length > 0 && (
          <Stack gap={4}>
            <Text fw={600} size="sm">
              Game
            </Text>
            <Table withRowBorders={false} verticalSpacing={2} fz="sm">
              <Table.Tbody>
                {tags.map(([k, v]) => (
                  <Table.Tr key={k}>
                    <Table.Td c="dimmed" w={110}>
                      {k}
                    </Table.Td>
                    <Table.Td>{v}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Stack>
        )}

        <Stack gap={4}>
          <Group justify="space-between">
            <Text fw={600} size="sm">
              Services
            </Text>
            <Tooltip label="Check again">
              <ActionIcon variant="subtle" color="gray" size="sm" onClick={() => setNonce((n) => n + 1)} aria-label="Re-check services">
                <IconRefresh size={14} />
              </ActionIcon>
            </Tooltip>
          </Group>
          <Group gap="xs">
            <Text size="sm" w={110} c="dimmed">
              Chess API
            </Text>
            {health.loading ? (
              <Badge variant="light" color="gray">
                checking
              </Badge>
            ) : health.data ? (
              <Badge variant="light" color={health.data.data.engine?.name === "mock" ? "orange" : "teal"}>
                {health.data.data.engine?.name === "mock" ? "mock" : health.data.data.status} · schema {health.data.data.schema_version}
              </Badge>
            ) : (
              <Badge variant="light" color="red">
                offline
              </Badge>
            )}
          </Group>
          <Text size="xs" c="dimmed" ff="monospace">
            {CHESS_API_URL}
          </Text>
          <Group gap="xs" mt={4}>
            <Text size="sm" w={110} c="dimmed">
              Coach
            </Text>
            <Text size="xs" c="dimmed" ff="monospace">
              {COACH_API_URL}
            </Text>
          </Group>
        </Stack>
      </Stack>
    </ScrollArea>
  );
}
