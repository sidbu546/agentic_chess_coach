import { useEffect } from "react";
import { useGameTree } from "@/state/gameTree";
import { useLinePlayer } from "@/state/linePlayer";
import { useSettings } from "@/state/settings";
import { useUi } from "@/state/ui";

/** En Croissant's board shortcuts: arrows to navigate, f to flip. Ignored while typing. */
export function useBoardHotkeys() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName))) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (useUi.getState().editing) return;
      const player = useLinePlayer.getState();
      if (player.line) {
        // While a coach line plays back, the keys step through the line.
        const n = player.line.steps.length;
        const lineActions: Record<string, () => void> = {
          ArrowLeft: () => player.step(-1),
          ArrowRight: () => player.step(1),
          ArrowUp: () => player.go(0),
          Home: () => player.go(0),
          ArrowDown: () => player.go(n),
          End: () => player.go(n),
          " ": () => player.setPlaying(!player.playing),
          Escape: player.close,
        };
        const act = lineActions[e.key];
        if (act) {
          e.preventDefault();
          act();
        }
        return;
      }
      const tree = useGameTree.getState();
      const actions: Record<string, () => void> = {
        ArrowLeft: tree.prev,
        ArrowRight: tree.next,
        ArrowUp: tree.start,
        ArrowDown: tree.end,
        Home: tree.start,
        End: tree.end,
        f: () => {
          const s = useSettings.getState();
          s.set({ orientation: s.orientation === "white" ? "black" : "white" });
        },
      };
      const action = actions[e.key];
      if (action) {
        e.preventDefault();
        action();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
