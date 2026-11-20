import { Box, Menu, Text } from "@mantine/core";
import { IconArrowBigUpLines, IconTrash } from "@tabler/icons-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { isMainline, moveNumber, ROOT_ID, useGameTree, type TreeNode } from "@/state/gameTree";

// Standard NAG glyphs ($1..$6) with En Croissant-like colors.
const NAGS: Record<number, { glyph: string; color: string }> = {
  1: { glyph: "!", color: "var(--mantine-color-teal-5)" },
  2: { glyph: "?", color: "var(--mantine-color-orange-5)" },
  3: { glyph: "!!", color: "var(--mantine-color-cyan-5)" },
  4: { glyph: "??", color: "var(--mantine-color-red-6)" },
  5: { glyph: "!?", color: "var(--mantine-color-lime-5)" },
  6: { glyph: "?!", color: "var(--mantine-color-yellow-5)" },
};

interface MenuState {
  nodeId: string;
  x: number;
  y: number;
}

export function MoveTree() {
  const nodes = useGameTree((s) => s.nodes);
  const currentId = useGameTree((s) => s.currentId);
  const result = useGameTree((s) => s.result);
  const goTo = useGameTree((s) => s.goTo);
  const [menu, setMenu] = useState<MenuState | null>(null);
  const rootFen = nodes[ROOT_ID].fen;
  const activeRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [currentId]);

  const moveButton = (n: TreeNode, showNumber: boolean) => {
    const mn = moveNumber(rootFen, n.ply);
    const nag = n.nags.map((x) => NAGS[x]).find(Boolean);
    const active = n.id === currentId;
    return (
      <span key={n.id} className="move-wrap">
        {(showNumber || mn.white) && (
          <span className="move-number">
            {mn.number}
            {mn.white ? "." : "..."}
          </span>
        )}
        <button
          type="button"
          ref={active ? activeRef : undefined}
          className="move-btn"
          data-active={active || undefined}
          onClick={() => goTo(n.id)}
          onContextMenu={(e) => {
            e.preventDefault();
            setMenu({ nodeId: n.id, x: e.clientX, y: e.clientY });
          }}
        >
          {n.move!.san}
          {nag && <span style={{ color: nag.color, marginLeft: 1 }}>{nag.glyph}</span>}
        </button>
      </span>
    );
  };

  const line = (startId: string, depth: number): ReactNode[] => {
    const out: ReactNode[] = [];
    let id: string | undefined = startId;
    let forceNumber = true;
    while (id) {
      const n: TreeNode = nodes[id];
      out.push(moveButton(n, forceNumber));
      forceNumber = false;
      if (n.comment) {
        out.push(
          <span key={`c${n.id}`} className="move-comment">
            {n.comment}
          </span>,
        );
        forceNumber = true;
      }
      const parent = nodes[n.parentId!];
      if (parent.children[0] === n.id && parent.children.length > 1) {
        for (const alt of parent.children.slice(1)) {
          out.push(
            <Box key={`v${alt}`} className="variation" data-depth={Math.min(depth + 1, 4)}>
              {line(alt, depth + 1)}
            </Box>,
          );
        }
        forceNumber = true;
      }
      id = n.children[0];
    }
    return out;
  };

  const first = nodes[ROOT_ID].children[0];
  const menuNode = menu ? nodes[menu.nodeId] : undefined;
  const onMainline = menuNode ? isMainline(nodes, menuNode.id) : true;

  return (
    <Box className="move-tree">
      {first ? (
        <>
          {line(first, 0)}
          {result !== "*" && (
            <Text component="span" fw={700} ml={6} size="sm">
              {result}
            </Text>
          )}
        </>
      ) : (
        <Text c="dimmed" size="sm" p="xs">
          No moves yet. Play a move on the board, or import a PGN.
        </Text>
      )}

      <Menu opened={!!menu} onChange={(o) => !o && setMenu(null)} position="bottom-start" withinPortal shadow="md">
        <Menu.Target>
          <div style={{ position: "fixed", left: menu?.x ?? 0, top: menu?.y ?? 0, width: 1, height: 1 }} />
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Item
            leftSection={<IconArrowBigUpLines size={16} />}
            disabled={onMainline}
            onClick={() => menu && useGameTree.getState().promoteToMainline(menu.nodeId)}
          >
            Promote to main line
          </Menu.Item>
          <Menu.Item
            color="red"
            leftSection={<IconTrash size={16} />}
            onClick={() => menu && useGameTree.getState().deleteNode(menu.nodeId)}
          >
            Delete from here
          </Menu.Item>
        </Menu.Dropdown>
      </Menu>
    </Box>
  );
}

