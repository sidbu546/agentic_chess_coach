import { ActionIcon, CopyButton, Group, Tooltip } from "@mantine/core";
import {
  IconCheck,
  IconCopy,
  IconEdit,
  IconFileImport,
  IconPlus,
  IconSettings,
  IconSwitchVertical,
} from "@tabler/icons-react";
import { useEditor } from "@/state/editor";
import { useCurrentNode, useGameTree } from "@/state/gameTree";
import { useSettings } from "@/state/settings";
import { useUi } from "@/state/ui";
import { useCoach } from "@/coach/coachStore";

/** Toolbar under the board, like En Croissant's board controls. */
export function BoardControls() {
  const node = useCurrentNode();
  const editing = useUi((s) => s.editing);
  const orientation = useSettings((s) => s.orientation);
  const setSettings = useSettings((s) => s.set);
  const setUi = useUi((s) => s.set);

  return (
    <Group className="board-controls" gap={6} justify="center">
      <Btn label="Flip board (f)" onClick={() => setSettings({ orientation: orientation === "white" ? "black" : "white" })}>
        <IconSwitchVertical size={18} />
      </Btn>
      <Btn
        label={editing ? "Stop editing" : "Set up position"}
        active={editing}
        onClick={() => {
          if (!editing) useEditor.getState().begin(node.fen);
          setUi({ editing: !editing });
        }}
      >
        <IconEdit size={18} />
      </Btn>
      <Btn label="Import PGN or FEN" onClick={() => setUi({ importOpen: true })} disabled={editing}>
        <IconFileImport size={18} />
      </Btn>
      <CopyButton value={node.fen}>
        {({ copied, copy }) => (
          <Btn label={copied ? "Copied" : "Copy FEN"} onClick={copy}>
            {copied ? <IconCheck size={18} /> : <IconCopy size={18} />}
          </Btn>
        )}
      </CopyButton>
      <Btn
        label="New game"
        disabled={editing}
        onClick={() => {
          useGameTree.getState().reset();
          useCoach.getState().show(null);
        }}
      >
        <IconPlus size={18} />
      </Btn>
      <Btn label="Board settings" onClick={() => setUi({ settingsOpen: true })}>
        <IconSettings size={18} />
      </Btn>
    </Group>
  );
}

function Btn({
  label,
  onClick,
  children,
  active,
  disabled,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
  active?: boolean;
  disabled?: boolean;
}) {
  return (
    <Tooltip label={label} openDelay={300}>
      <ActionIcon size="lg" variant={active ? "filled" : "default"} onClick={onClick} disabled={disabled} aria-label={label}>
        {children}
      </ActionIcon>
    </Tooltip>
  );
}
