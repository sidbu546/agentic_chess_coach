# Web app — Siddhanth

The Think64 board, coach chat, analysis panel, position setup and PGN viewer. The board is
modelled on [En Croissant](https://encroissant.org/): lichess's chessground, Mantine dark UI, an
eval bar beside the board, player bars with material, and a notation panel with variations.

## Run it

```bash
# 1. the chess API (mock until Person 1's service is ready)
cd packages/analysis-schema && pip install -r requirements.txt && python mock/server.py   # :8064

# 2. the web app
cd apps/web
npm install
npm run dev            # http://localhost:5173
```

Copy `.env.example` to `.env.local` to point at other services. Switching from the mock to the real
chess service is only `VITE_CHESS_API_URL`.

```bash
npm test               # unit tests (tree, move numbers, editor, scores)
npm run typecheck
npm run build
```

## What's here

| Area | Files | Notes |
| --- | --- | --- |
| Board | `src/board/` | chessground wrapper, eval bar, player bars + material, promotion picker, toolbar |
| Move tree | `src/state/gameTree.ts`, `src/notation/` | Mainline + variations, comments, NAGs; right-click to promote or delete |
| Analysis | `src/panels/AnalysisPanel.tsx` | `/v1/analyze` lines (hover to preview, click to play), facts from `/v1/position` (hover to draw) |
| Coach chat | `src/panels/CoachPanel.tsx`, `src/coach/` | Talks to `services/coach`; shows each claim's `/v1/verify` verdict and draws the coach's arrows |
| Setup | `src/panels/EditPanel.tsx`, `src/state/editor.ts` | Drag/drop or click-to-place pieces, side to move, castling; validated by `/v1/position` |
| Import | `src/panels/ImportModal.tsx` | PGN paste/upload → `/v1/game`; FEN → `/v1/position` |

Board interaction: drag or click to move, right-click drag to draw arrows (Shift/Alt/Ctrl for
colours), right-click a square for a circle. Keys: ← → to step, ↑ ↓ for start/end, `f` to flip.
Scroll on the board to step through the game.

## Ownership rules this app follows

- **Legality is Person 1's.** chess.js only gives instant drag feedback (legal-move dots, check
  highlight). Every move goes to `/v1/move`; if the service rejects it, the piece snaps back.
- **PGN is Person 1's.** The app never parses PGN; it displays the tree `/v1/game` returns. Moves
  played on the board are added to that tree from `/v1/move` responses.
- **History travels with every request.** Each tree node stores the API's `PositionRef`
  (start FEN + moves), so repetition can be detected.
- **Coach types live here, not in the shared contract** (`src/coach/types.ts`); `services/coach`
  implements the other end at `POST /v1/coach/ask`.

## Known gap in the shared contract

`openapi-typescript` marks request fields that have defaults (`notation`, `include.*`,
`start_fen`) as required, so the app sends them explicitly. Fixing it means regenerating the types
with default-handling turned off: a contract PR for both owners, not a web-app change.

Asset credits: see [ASSETS.md](ASSETS.md).
