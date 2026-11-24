import { notifications } from "@mantine/notifications";
import { ChessApiError, chessApi } from "@/api/chessApi";
import { useGameTree } from "./gameTree";
import { useUi } from "./ui";

function apiErrorMessage(err: unknown): string {
  if (err instanceof ChessApiError) return err.message;
  return (err as Error)?.message ?? "Unknown error";
}

/**
 * Play `uci` from the current node. chess.js already let the drag through; the chess API now
 * decides. Returns false if the move was rejected, so the board can snap back.
 */
export async function playMove(uci: string): Promise<boolean> {
  const tree = useGameTree.getState();
  const node = tree.nodes[tree.currentId];

  // Already in the tree, so the API has confirmed it before: just navigate.
  const existing = node.children.find((c) => tree.nodes[c].move?.uci === uci);
  if (existing) {
    tree.goTo(existing);
    return true;
  }

  useUi.getState().set({ moveInFlight: true });
  try {
    const { data } = await chessApi.move({ position: node.position, move: uci, notation: "uci" });
    if (!data.legal || !data.move || !data.next || !data.position) {
      notifications.show({
        color: "red",
        title: "Illegal move",
        message: data.reason?.message ?? `${uci} is not legal here.`,
      });
      return false;
    }
    useGameTree.getState().addMove(node.id, data.move, data.next, data.position.fen);
    return true;
  } catch (err) {
    notifications.show({ color: "red", title: "Move not played", message: apiErrorMessage(err) });
    return false;
  } finally {
    useUi.getState().set({ moveInFlight: false });
  }
}

/** Play a sequence of moves from the current node (e.g. clicking into an engine line). */
export async function playLine(ucis: string[]): Promise<void> {
  for (const uci of ucis) {
    if (!(await playMove(uci))) return;
  }
}

/** Parse a PGN with /v1/game and load its move tree. Throws with a user-facing message. */
export async function loadPgn(pgn: string): Promise<void> {
  try {
    const { data } = await chessApi.game({ pgn });
    useGameTree.getState().loadGame(data);
  } catch (err) {
    throw new Error(apiErrorMessage(err));
  }
}

/** Validate a FEN with /v1/position and start a fresh game from it. Throws with a user-facing message. */
export async function loadFen(fen: string): Promise<void> {
  try {
    const { data } = await chessApi.position({
      position: { start_fen: fen.trim(), moves: [] },
      include: { legal_moves: false, facts: false, pieces: false },
    });
    useGameTree.getState().reset(data.position.fen);
  } catch (err) {
    throw new Error(apiErrorMessage(err));
  }
}
