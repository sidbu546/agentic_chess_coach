import { Alert, Button, FileButton, Group, Modal, Stack, Tabs, Text, Textarea, TextInput } from "@mantine/core";
import { IconFileUpload } from "@tabler/icons-react";
import { useState } from "react";
import { loadFen, loadPgn } from "@/state/actions";
import { useUi } from "@/state/ui";

const SAMPLE_PGN = `[Event "Think64 sample"]
[White "Student"]
[Black "Opponent"]
[Result "1-0"]

1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6? (3... g6 {defends f7 and attacks the queen} 4. Qf3) 4. Qxf7# 1-0`;

/** PGN and FEN import. Parsing happens in the chess API (/v1/game, /v1/position), never here. */
export function ImportModal() {
  const opened = useUi((s) => s.importOpen);
  const close = () => useUi.getState().set({ importOpen: false });
  const [tab, setTab] = useState<string | null>("pgn");
  const [pgn, setPgn] = useState("");
  const [fen, setFen] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      close();
      setPgn("");
      setFen("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal opened={opened} onClose={close} title="Import a game or position" size="lg">
      <Tabs value={tab} onChange={(t) => (setTab(t), setError(null))}>
        <Tabs.List mb="sm">
          <Tabs.Tab value="pgn">PGN</Tabs.Tab>
          <Tabs.Tab value="fen">FEN</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="pgn">
          <Stack gap="sm">
            <Textarea
              placeholder="Paste a PGN — variations and comments are kept"
              autosize
              minRows={8}
              maxRows={16}
              value={pgn}
              onChange={(e) => setPgn(e.currentTarget.value)}
              styles={{ input: { fontFamily: "var(--mantine-font-family-monospace)", fontSize: 13 } }}
            />
            <Group justify="space-between">
              <Group gap="xs">
                <FileButton accept=".pgn,text/plain,application/x-chess-pgn" onChange={async (f) => f && setPgn(await f.text())}>
                  {(props) => (
                    <Button {...props} variant="default" size="xs" leftSection={<IconFileUpload size={14} />}>
                      Upload .pgn
                    </Button>
                  )}
                </FileButton>
                <Button variant="subtle" size="xs" onClick={() => setPgn(SAMPLE_PGN)}>
                  Use sample game
                </Button>
              </Group>
              <Button loading={busy} disabled={!pgn.trim()} onClick={() => run(() => loadPgn(pgn))}>
                Load game
              </Button>
            </Group>
          </Stack>
        </Tabs.Panel>
        <Tabs.Panel value="fen">
          <Stack gap="sm">
            <TextInput
              placeholder="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
              value={fen}
              onChange={(e) => setFen(e.currentTarget.value)}
              styles={{ input: { fontFamily: "var(--mantine-font-family-monospace)" } }}
            />
            <Text size="xs" c="dimmed">
              A FEN has no history, so repetition can't be detected from it alone.
            </Text>
            <Group justify="flex-end">
              <Button loading={busy} disabled={!fen.trim()} onClick={() => run(() => loadFen(fen))}>
                Load position
              </Button>
            </Group>
          </Stack>
        </Tabs.Panel>
      </Tabs>
      {error && (
        <Alert color="red" variant="light" mt="sm" p="xs">
          <Text size="sm">{error}</Text>
        </Alert>
      )}
    </Modal>
  );
}
