import type { Api } from "@lichess-org/chessground/api";
import type { Config } from "@lichess-org/chessground/config";
import type { DrawShape } from "@lichess-org/chessground/draw";
import type { Key } from "@lichess-org/chessground/types";
import { Badge, Box } from "@mantine/core";
import { useElementSize } from "@mantine/hooks";
import { useCallback, useMemo, useRef, useState, type CSSProperties } from "react";
import { useShallow } from "zustand/react/shallow";
import type { GameStatus, Score } from "@schema";
import { positionKey } from "@/api/chessApi";
import { useAnalysis, usePositionInfo } from "@/api/hooks";
import { useCoach } from "@/coach/coachStore";
import { isPromotion, localPosition } from "@/lib/chess";
import { coachShapes, engineShapes } from "@/lib/shapes";
import { playMove } from "@/state/actions";
import { useEditor } from "@/state/editor";
import { useCurrentNode, useGameTree } from "@/state/gameTree";
import { BOARD_THEMES, useSettings } from "@/state/settings";
import { useUi } from "@/state/ui";
import { BoardBar, MaterialStrip } from "./BoardBar";
import { boardApi, boardImage } from "./boardApi";
import { Chessground } from "./Chessground";
import { EvalBar } from "./EvalBar";
import { PromotionPicker } from "./PromotionPicker";

const BAR_HEIGHT = 32;
const EVAL_WIDTH = 25;
const GAP = 8;

/** Arrows and circles the player drew, kept per tree node like En Croissant does. */
const userShapes = new Map<string, DrawShape[]>();

function statusLabel(s: GameStatus): string | null {
  switch (s.state) {
    case "checkmate":
      return `Checkmate · ${s.winner === "white" ? "White" : "Black"} wins`;
    case "stalemate":
      return "Stalemate · draw";
    case "insufficient_material":
      return "Insufficient material · draw";
    case "fivefold_repetition":
      return "Fivefold repetition · draw";
    case "seventyfive_moves":
      return "75-move rule · draw";
    default:
      if (s.claimable_draws.includes("threefold_repetition")) return "Threefold repetition · draw claimable";
      if (s.claimable_draws.includes("fifty_moves")) return "50-move rule · draw claimable";
      return null;
  }
}

export function Board() {
  const node = useCurrentNode();
  const gameVersion = useGameTree((s) => s.gameVersion);
  const headers = useGameTree((s) => s.headers);
  const st = useSettings(
    useShallow((s) => ({
      boardTheme: s.boardTheme,
      pieceSet: s.pieceSet,
      showCoordinates: s.showCoordinates,
      showDests: s.showDests,
      highlightLastMove: s.highlightLastMove,
      animation: s.animation,
      scrollToNavigate: s.scrollToNavigate,
      showEvalBar: s.showEvalBar,
      showEngineArrows: s.showEngineArrows,
      autoQueen: s.autoQueen,
      orientation: s.orientation,
    })),
  );
  const ui = useUi(
    useShallow((s) => ({ editing: s.editing, moveInFlight: s.moveInFlight, hoverShapes: s.hoverShapes, engineOn: s.engineOn })),
  );
  const editor = useEditor(useShallow((s) => ({ placement: s.placement, tool: s.tool, turn: s.turn })));
  const shownCoach = useCoach((s) => s.messages.find((m) => m.id === s.shownId));

  const local = useMemo(() => localPosition(node.fen), [node.fen]);
  const analysis = useAnalysis(node.position);
  const info = usePositionInfo(node.position);
  const status = info.data?.data.status;

  const apiRef = useRef<Api | null>(null);
  const [promo, setPromo] = useState<{ from: Key; to: Key } | null>(null);
  const [resetNonce, setResetNonce] = useState(0);
  const { ref: areaRef, width, height } = useElementSize();

  const orientation = st.orientation;
  const turn = local.turn;
  const nodeKey = `${gameVersion}:${node.id}`;

  const submit = useCallback(async (uci: string) => {
    const ok = await playMove(uci);
    if (!ok) setResetNonce((n) => n + 1); // snap the piece back to the confirmed position
  }, []);

  const onAfterMove = (orig: Key, dest: Key, meta: { ctrlKey?: boolean }) => {
    if (isPromotion(node.fen, orig, dest)) {
      if (st.autoQueen && !meta.ctrlKey) submit(`${orig}${dest}q`);
      else setPromo({ from: orig, to: dest });
      return;
    }
    submit(`${orig}${dest}`);
  };

  const syncEditor = () => {
    const cg = apiRef.current;
    if (cg) useEditor.getState().setPlacement(cg.getFen());
  };

  const placeWithTool = (key: Key) => {
    const cg = apiRef.current;
    const tool = useEditor.getState().tool;
    if (!cg || !tool) return;
    cg.setPieces(new Map([[key, tool === "trash" ? undefined : { role: tool.role, color: tool.color }]]));
    cg.selectSquare(null);
    syncEditor();
  };

  // ----- shapes: hover preview wins; otherwise the shown coach answer, else engine arrows -----
  const candidates = analysis.data?.data.analysis.candidates ?? [];
  const coachHere = shownCoach && shownCoach.positionKey === positionKey(node.position) ? shownCoach : undefined;
  let autoShapes: DrawShape[] = [];
  if (!ui.editing) {
    if (ui.hoverShapes.length) autoShapes = ui.hoverShapes;
    else if (coachHere) autoShapes = coachShapes(coachHere.annotations);
    else if (st.showEngineArrows && ui.engineOn) autoShapes = engineShapes(candidates, turn);
  }

  const gameOver = status?.is_game_over ?? false;
  const lastMove = node.move ? ([node.move.uci.slice(0, 2), node.move.uci.slice(2, 4)] as Key[]) : undefined;
  const toolActive = ui.editing && editor.tool !== null;

  const config: Config = ui.editing
    ? {
        fen: editor.placement,
        orientation,
        turnColor: editor.turn === "w" ? "white" : "black",
        lastMove: undefined,
        check: false,
        coordinates: st.showCoordinates,
        animation: { enabled: false },
        movable: { free: true, color: toolActive ? undefined : "both", dests: undefined, showDests: false, events: { after: syncEditor } },
        draggable: { enabled: !toolActive, deleteOnDropOff: true, showGhost: true },
        selectable: { enabled: !toolActive },
        events: { change: syncEditor, select: toolActive ? placeWithTool : undefined },
        drawable: { enabled: false, shapes: [], autoShapes: [] },
      }
    : {
        fen: node.fen,
        orientation,
        turnColor: turn,
        lastMove: st.highlightLastMove ? lastMove : undefined,
        check: local.inCheck ? turn : false,
        coordinates: st.showCoordinates,
        animation: { enabled: st.animation, duration: 200 },
        movable: {
          // If chess.js can't read the FEN, let the API alone judge the move.
          free: !local.ok,
          color: gameOver || ui.moveInFlight ? undefined : turn,
          dests: local.ok ? local.dests : undefined,
          showDests: st.showDests,
          events: { after: onAfterMove },
        },
        draggable: { enabled: true, deleteOnDropOff: false, showGhost: true },
        selectable: { enabled: true },
        events: { change: undefined, select: undefined },
        drawable: {
          enabled: true,
          visible: true,
          defaultSnapToValidMove: true,
          eraseOnMovablePieceClick: false,
          shapes: userShapes.get(nodeKey) ?? [],
          autoShapes,
          onChange: (shapes) => userShapes.set(nodeKey, shapes),
        },
      };

  // ----- sizing: the largest square that fits beside the eval bar and between the player bars -----
  const evalSpace = st.showEvalBar ? EVAL_WIDTH + GAP : 0;
  const size = Math.max(160, Math.floor(Math.min(width - evalSpace, height - 2 * BAR_HEIGHT - 2 * GAP)));
  const ready = width > 0 && height > 0;

  const theme = BOARD_THEMES[st.boardTheme];
  const boardVars = {
    "--board-image": boardImage(theme.light, theme.dark),
    "--board-light": theme.light,
    "--board-dark": theme.dark,
    "--coord-size": `${Math.max(9, Math.round(size / 52))}px`,
  } as CSSProperties;

  // ----- eval bar -----
  let score: Score | null = candidates[0]?.score ?? null;
  if (status?.state === "checkmate") score = { type: "mate", value: status.winner === "white" ? 1 : -1, pov: "white" };
  else if (gameOver) score = { type: "cp", value: 0, pov: "white" };
  const engine = analysis.data?.data.analysis.engine;
  const evalNote = engine ? (engine.name === "mock" ? "mock engine" : `depth ${analysis.data?.data.analysis.depth}`) : undefined;

  const topColor = orientation === "white" ? "black" : "white";
  const bottomColor = orientation;
  const tag = (k: string) => (headers[k] && headers[k] !== "?" ? headers[k] : undefined); // PGN uses "?" for unknown
  const name = (c: "white" | "black") => tag(c === "white" ? "White" : "Black") ?? (c === "white" ? "White" : "Black");
  const elo = (c: "white" | "black") => tag(c === "white" ? "WhiteElo" : "BlackElo");
  const label = status ? statusLabel(status) : null;
  const editTurn = editor.turn === "w" ? "white" : "black";

  return (
    <Box ref={areaRef} className="board-area">
      {ready && (
        <Box className="board-column" style={{ width: size + evalSpace }}>
          <Box style={{ marginLeft: evalSpace, height: BAR_HEIGHT }}>
            <BoardBar
              name={name(topColor)}
              rating={elo(topColor)}
              colorDot={topColor}
              toMove={(ui.editing ? editTurn : turn) === topColor}
            >
              {!ui.editing && <MaterialStrip fen={node.fen} color={topColor} pieceSet={st.pieceSet} />}
            </BoardBar>
          </Box>
          <Box className="board-row" style={{ height: size, gap: GAP }}>
            {st.showEvalBar && (
              <Box style={{ width: EVAL_WIDTH, height: size, flexShrink: 0 }}>
                <EvalBar
                  score={ui.engineOn || gameOver ? score : null}
                  orientation={orientation}
                  note={evalNote}
                  result={gameOver ? (status?.winner === "white" ? "1-0" : status?.winner === "black" ? "0-1" : "½-½") : undefined}
                />
              </Box>
            )}
            <Box
              className={`board-square pieces-${st.pieceSet}${ui.editing ? " is-editing" : ""}`}
              style={{ width: size, height: size, ...boardVars }}
              onWheel={(e) => {
                if (!st.scrollToNavigate || ui.editing || promo) return;
                const tree = useGameTree.getState();
                if (e.deltaY > 0) tree.next();
                else if (e.deltaY < 0) tree.prev();
              }}
            >
              <Chessground
                className="cg-host"
                config={config}
                positionId={ui.editing ? "editor" : `${nodeKey}:${resetNonce}`}
                onApi={(v) => {
                  apiRef.current = v;
                  boardApi.current = v;
                }}
              />
              {promo && (
                <PromotionPicker
                  dest={promo.to}
                  color={turn}
                  orientation={orientation}
                  pieceSet={st.pieceSet}
                  onPick={(role) => {
                    const m = promo;
                    setPromo(null);
                    submit(`${m.from}${m.to}${role}`);
                  }}
                  onCancel={() => {
                    setPromo(null);
                    setResetNonce((n) => n + 1);
                  }}
                />
              )}
            </Box>
          </Box>
          <Box style={{ marginLeft: evalSpace, height: BAR_HEIGHT }}>
            <BoardBar
              name={name(bottomColor)}
              rating={elo(bottomColor)}
              colorDot={bottomColor}
              toMove={(ui.editing ? editTurn : turn) === bottomColor}
            >
              {label && !ui.editing && (
                <Badge color={gameOver ? "red" : "yellow"} variant="light" radius="sm">
                  {label}
                </Badge>
              )}
              {!ui.editing && <MaterialStrip fen={node.fen} color={bottomColor} pieceSet={st.pieceSet} />}
            </BoardBar>
          </Box>
        </Box>
      )}
    </Box>
  );
}
