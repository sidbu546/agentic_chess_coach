# analysis-schema — the Think64 shared contract (v0.1.0)

This package is the only thing the two halves of Think64 share. Person 1 (chess truth
service) implements it; Person 2 (coach and product) calls it. Once both of you sign off
on it, you can build separately and connect at any point by changing one URL.

```
analysis-schema/
├── openapi.yaml              ← the contract. Everything else is derived from this file.
├── examples/                 ← 24 real request/response pairs (python-chess + Stockfish 17.1)
├── mock/server.py            ← a fake chess truth service for Person 2 to build against
├── tests/test_contract.py    ← contract tests both of you run
├── types/
│   ├── typescript/           ← generated TS types (import from types/typescript/index.ts)
│   └── python/models.py      ← generated Pydantic v2 models
├── tools/
│   ├── chessref.py           ← reference logic that produced the examples
│   ├── generate_examples.py  ← regenerates examples/
│   ├── gen_types.sh          ← regenerates types/
│   └── schema.py             ← loads openapi.yaml for validation
```

## Quick start

```bash
pip install -r requirements.txt
pytest tests/                          # 50 checks on the spec and examples
python mock/server.py                  # mock API on http://localhost:8064
CONTRACT_BASE_URL=http://localhost:8064 pytest tests/   # check a running server
```

## The endpoints

| Endpoint | Kind | What it's for |
| --- | --- | --- |
| `GET /v1/health` | rules | Status, schema version, engine name |
| `POST /v1/position` | rules | Status, legal moves, material, facts (pins, x-rays, hanging pieces, checks, open files); optional per-piece view |
| `POST /v1/move` | rules | Is this move legal? Returns the next position, or why not (e.g. the pin) |
| `POST /v1/game` | rules | PGN → move tree with variations, a ready `PositionRef` on every node |
| `POST /v1/analyze` | engine | MultiPV candidate lines with scores and PVs |
| `POST /v1/compare` | engine | Specific moves vs the best move: loss in cp + structured differences |
| `POST /v1/verify` | engine | Check the coach's claims before the user sees them |

## Decisions this contract makes

These were the open questions from the design review. Changing any of them is a version bump.

1. **Positions carry history.** Every request sends `{start_fen, moves}`, never a bare FEN, so
   threefold repetition can be detected. Examples 15 and 16 show the same board with and
   without history.
2. **Moves in UCI, answers in both.** Send `e2e4`; every returned move has `uci` and `san`.
   `/v1/move` also accepts SAN (`notation: "san"`) because LLMs write SAN.
3. **Scores are always from White's view.** `{type: "cp" | "mate", value, pov: "white"}`.
   Mate values are moves to mate: positive means White mates.
4. **Wrong chess is not an HTTP error.** An illegal move or a false claim is a 200 with
   `legal: false` or `verdict: "refuted"`. HTTP 422 is only for malformed requests
   (bad FEN, illegal move inside the history, bad PGN); 503 is for engine failure.
5. **Geometry and legality are separate.** In the per-piece view, `attacks` ignores pins and
   `legal_moves` does not. A pinned knight still attacks its squares but has no legal moves
   (example 06).
6. **Pins are facts, not advice.** A relative pin is reported, but nothing says the piece
   must not move. Whether breaking it works is the engine's call.
7. **Synchronous calls with limits.** Engine endpoints block until done. The caller chooses
   `depth`, `movetime_ms` or `nodes`, and `multipv` (1-5). Default is depth 16.
   Person 2 can pick limits per player level.
8. **Verification is required.** The coach sends every chess claim to `/v1/verify`.
   `unverifiable` must never be stated as fact.
9. **Ownership.** The move tree, PGN parsing, legality, facts and line comparison belong to
   Person 1. Coach-side types (player profile, coach messages, board annotations) live in
   Person 2's code, not here — they never cross the boundary.

## Person 2: building against the mock

```bash
python mock/server.py
curl -s localhost:8064/v1/position -d '{"position": {"moves": ["e2e4"]}}'
```

- **Rules endpoints are real** for any position (computed with python-chess).
- **Engine endpoints** return the matching example when your request matches one, and
  otherwise obvious fake data: engine name `"mock"`, every score 0. Engine-backed claims
  come back `unverifiable`. The `X-Mock-Source` header says `fixture`, `live` or `fake`.
- **Every request is validated** against the spec; mistakes return 422 with the exact field.
- Import types from `types/typescript/index.ts`, e.g.
  `import type { AnalyzeResponse, Claim } from "../../packages/analysis-schema/types/typescript"`.
- Switching to the real service later = changing the base URL.

## Person 1: building the real service

- Implement the seven endpoints so that `CONTRACT_BASE_URL=<your server> pytest tests/` passes.
- Rules endpoints must match the examples exactly (facts in any order). Engine endpoints
  are checked for schema, legal PVs, ranks and objective verdicts, not exact scores.
- `tools/chessref.py` is the reference that produced the examples. You can start from it,
  restructure it, or replace it — the tests are the contract, not that file.
- To run the generator you need Stockfish: `STOCKFISH_PATH=/path/to/stockfish python tools/generate_examples.py`.

## Changing the contract

CI (`.github/workflows/contract.yml` at the repo root) runs these tests on every push.


1. Edit `openapi.yaml` and bump `info.version` (and `SCHEMA_VERSION` in `tools/chessref.py`).
2. Regenerate: `python tools/generate_examples.py` and `./tools/gen_types.sh`.
3. Run `pytest tests/`. Open one pull request with all of it, and the other person reviews.

Adding a field or a new fact kind is a minor bump (0.1 → 0.2). Clients must ignore fact
kinds they don't know. Renaming or removing anything is a breaking change; agree first.

## Not in v0.1 (planned)

- Game review: critical positions and evaluation swings across a PGN (milestone 3).
- More fact kinds: forks, skewers, overloaded defenders, passed pawns.
- Concept attribution (joint milestone 4).
