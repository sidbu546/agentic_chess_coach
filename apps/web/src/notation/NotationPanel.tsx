import { ActionIcon, Group, Paper, ScrollArea, Text, Tooltip } from "@mantine/core";
import {
  IconChevronLeft,
  IconChevronRight,
  IconChevronsLeft,
  IconChevronsRight,
} from "@tabler/icons-react";
import { useGameTree } from "@/state/gameTree";
import { MoveTree } from "./MoveTree";

export function NotationPanel() {
  const { start, prev, next, end } = useGameTree.getState();
  const atStart = useGameTree((s) => s.nodes[s.currentId].parentId === null);
  const atEnd = useGameTree((s) => s.nodes[s.currentId].children.length === 0);
  const headers = useGameTree((s) => s.headers);
  const known = (v?: string) => !!v && v !== "?";
  const title = known(headers.White) && known(headers.Black) ? `${headers.White} – ${headers.Black}` : "Game notation";

  return (
    <Paper className="panel notation-panel" withBorder>
      <Group className="panel-header" justify="space-between" wrap="nowrap">
        <Text fw={600} size="sm" truncate>
          {title}
        </Text>
        {headers.Event && headers.Event !== "?" && (
          <Text size="xs" c="dimmed" truncate>
            {headers.Event}
          </Text>
        )}
      </Group>
      <ScrollArea className="notation-scroll" type="auto" offsetScrollbars>
        <MoveTree />
      </ScrollArea>
      <Group className="move-controls" grow gap={4}>
        <Control label="Start (↑)" onClick={start} disabled={atStart} icon={<IconChevronsLeft size={18} />} />
        <Control label="Previous (←)" onClick={prev} disabled={atStart} icon={<IconChevronLeft size={18} />} />
        <Control label="Next (→)" onClick={next} disabled={atEnd} icon={<IconChevronRight size={18} />} />
        <Control label="End (↓)" onClick={end} disabled={atEnd} icon={<IconChevronsRight size={18} />} />
      </Group>
    </Paper>
  );
}

function Control({ label, onClick, disabled, icon }: { label: string; onClick: () => void; disabled: boolean; icon: React.ReactNode }) {
  return (
    <Tooltip label={label} openDelay={400}>
      <ActionIcon variant="default" size="lg" onClick={onClick} disabled={disabled} aria-label={label}>
        {icon}
      </ActionIcon>
    </Tooltip>
  );
}
