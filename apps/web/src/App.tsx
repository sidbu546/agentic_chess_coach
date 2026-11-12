import { Box, Paper, Stack, Tabs, Tooltip } from "@mantine/core";
import { IconChartLine, IconChess, IconInfoCircle, IconMessageCircle, IconSettings } from "@tabler/icons-react";
import { useState } from "react";
import { Board } from "@/board/Board";
import { BoardControls } from "@/board/BoardControls";
import { useBoardHotkeys } from "@/lib/useHotkeys";
import { NotationPanel } from "@/notation/NotationPanel";
import { AnalysisPanel } from "@/panels/AnalysisPanel";
import { CoachPanel } from "@/panels/CoachPanel";
import { EditPanel } from "@/panels/EditPanel";
import { ImportModal } from "@/panels/ImportModal";
import { InfoPanel, useHealth } from "@/panels/InfoPanel";
import { SettingsModal } from "@/panels/SettingsModal";
import { useUi } from "@/state/ui";

export default function App() {
  useBoardHotkeys();
  const editing = useUi((s) => s.editing);
  const [tab, setTab] = useState<string | null>("coach");

  return (
    <Box className="app-shell">
      <Rail />
      <main className="workspace">
        <section className="board-pane" aria-label="Board">
          <Board />
          <BoardControls />
        </section>
        <section className="side-pane" aria-label="Panels">
          {editing ? (
            <EditPanel />
          ) : (
            <Paper className="panel tabs-panel" withBorder>
              <Tabs value={tab} onChange={setTab} keepMounted={false} className="side-tabs">
                <Tabs.List>
                  <Tabs.Tab value="coach" leftSection={<IconMessageCircle size={16} />}>
                    Coach
                  </Tabs.Tab>
                  <Tabs.Tab value="analysis" leftSection={<IconChartLine size={16} />}>
                    Analysis
                  </Tabs.Tab>
                  <Tabs.Tab value="info" leftSection={<IconInfoCircle size={16} />}>
                    Info
                  </Tabs.Tab>
                </Tabs.List>
                <Tabs.Panel value="coach" className="tab-body">
                  <CoachPanel />
                </Tabs.Panel>
                <Tabs.Panel value="analysis" className="tab-body">
                  <AnalysisPanel />
                </Tabs.Panel>
                <Tabs.Panel value="info" className="tab-body">
                  <InfoPanel />
                </Tabs.Panel>
              </Tabs>
            </Paper>
          )}
          <NotationPanel />
        </section>
      </main>
      <ImportModal />
      <SettingsModal />
    </Box>
  );
}

function Rail() {
  const health = useHealth();
  const status = health.loading ? "checking" : health.data ? (health.data.data.engine?.name === "mock" ? "mock" : "ok") : "offline";
  const label = { checking: "Checking chess API…", mock: "Chess API: mock server", ok: "Chess API connected", offline: "Chess API offline" }[status];
  return (
    <nav className="rail" aria-label="App">
      <Stack gap="md" align="center">
        <Tooltip label="Think64" position="right">
          <Box className="rail-logo" aria-label="Think64">
            <IconChess size={22} />
          </Box>
        </Tooltip>
      </Stack>
      <Stack gap="md" align="center">
        <Tooltip label={label} position="right">
          <Box className="status-dot" data-status={status} aria-label={label} />
        </Tooltip>
        <Tooltip label="Board settings" position="right">
          <Box component="button" type="button" className="rail-btn" aria-label="Board settings" onClick={() => useUi.getState().set({ settingsOpen: true })}>
            <IconSettings size={20} />
          </Box>
        </Tooltip>
      </Stack>
    </nav>
  );
}
