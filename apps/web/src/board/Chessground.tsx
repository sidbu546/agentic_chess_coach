import { Chessground as createChessground } from "@lichess-org/chessground";
import type { Api } from "@lichess-org/chessground/api";
import type { Config } from "@lichess-org/chessground/config";
import { useEffect, useRef } from "react";

interface Props {
  config: Config;
  /**
   * Identifies the position being shown (e.g. the tree node id). The FEN and the user-drawn
   * shapes are only pushed to chessground when this or the FEN changes, so unrelated
   * re-renders never interrupt a drag or wipe the player's arrows.
   */
  positionId: string;
  /** Called with the chessground API once created, and with null on unmount. */
  onApi?: (api: Api | null) => void;
  className?: string;
}

export function Chessground({ config, positionId, onApi, className }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const api = useRef<Api | null>(null);
  const applied = useRef<{ id: string; fen?: string }>({ id: positionId, fen: config.fen });

  useEffect(() => {
    api.current = createChessground(el.current!, config);
    onApi?.(api.current);
    return () => {
      api.current?.destroy();
      api.current = null;
      onApi?.(null);
    };
    // created once; later changes go through api.set below
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const cg = api.current;
    if (!cg) return;
    const changed = applied.current.id !== positionId || applied.current.fen !== config.fen;
    if (changed) {
      applied.current = { id: positionId, fen: config.fen };
      cg.set(config);
    } else {
      const { fen: _fen, drawable, ...rest } = config;
      const { shapes: _shapes, ...drawRest } = drawable ?? {};
      cg.set({ ...rest, drawable: drawRest });
    }
  });

  return <div ref={el} className={className} />;
}
