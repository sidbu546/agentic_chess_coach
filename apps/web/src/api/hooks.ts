import { useDebouncedValue } from "@mantine/hooks";
import type { AnalyzeResponse, PositionRef, PositionResponse } from "@schema";
import { useUi } from "@/state/ui";
import { chessApi, positionKey, type WithSource } from "./chessApi";
import { useQuery } from "./useQuery";

/** Status, legal moves, material and facts for a position (rules endpoint: fast, no engine). */
export function usePositionInfo(position: PositionRef) {
  const key = `position:${positionKey(position)}`;
  return useQuery<WithSource<PositionResponse>>(key, () => chessApi.position({ position, include: { legal_moves: true, facts: true, pieces: false } }),
  );
}

/** Engine analysis for a position, debounced so scrubbing through a game doesn't queue searches. */
export function useAnalysis(position: PositionRef) {
  const engineOn = useUi((s) => s.engineOn);
  const multipv = useUi((s) => s.multipv);
  const depth = useUi((s) => s.depth);
  const raw = engineOn ? `analyze:${multipv}:${depth}:${positionKey(position)}` : null;
  const [key] = useDebouncedValue(raw, 200);
  const settledKey = key === raw ? key : null;
  const q = useQuery<WithSource<AnalyzeResponse>>(settledKey, () =>
    chessApi.analyze({ position, limits: { depth, multipv } }),
  );
  return { ...q, loading: q.loading || (raw !== null && settledKey === null) };
}
