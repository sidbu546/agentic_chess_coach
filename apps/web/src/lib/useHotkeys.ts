import { useEffect } from "react";
import { useGameTree } from "@/state/gameTree";
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
