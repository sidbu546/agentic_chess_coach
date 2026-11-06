# Chess truth service — Person 1

Implements the seven endpoints in `../../packages/analysis-schema/openapi.yaml`.
It must work fully without any LLM.

## Components

| Component | What it does |
| --- | --- |
| Chess API | HTTP server for `/v1/health`, `position`, `move`, `game`, `analyze`, `compare`, `verify` |
| Rules core | Legal moves, FEN and PGN parsing, move tree, check, mate, stalemate and draw detection |
| Engine service | Stockfish with depth/time/node limits and MultiPV; results cached |
| Facts and verifier | Pins, x-rays, hanging pieces, checks, open files; checks coach claims |
| Line comparison | Structured differences between candidate lines |

## Getting started

1. Install Stockfish and set `STOCKFISH_PATH`.
2. `../../packages/analysis-schema/tools/chessref.py` is the reference logic that produced the
   examples. Start from it, restructure it, or replace it.
3. Serve on port 8064 (any port works; the tests take a URL).

## Done when

```bash
cd ../../packages/analysis-schema
CONTRACT_BASE_URL=http://localhost:8064 pytest tests/
```

passes against this service.
