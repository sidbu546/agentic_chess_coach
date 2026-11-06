# Architecture

Full write-up with the block diagram: [Think64 system design: who builds what](https://claude.ai/artifact/XB5vuPD6Mhvb57V5HwA8Nc)

```
┌──────────────── Person 2: coach and product ────────────────┐
│  apps/web            services/coach                         │
│  board, chat,        coach agent · LLM adapter ·            │
│  PGN viewer          player memory · evaluation harness     │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP + JSON (mock until ready)
┌──────────────────────────────▼──────────────────────────────┐
│  packages/analysis-schema — shared contract                 │
│  openapi.yaml · examples · mock server · tests · types      │
└──────────────────────────────▲──────────────────────────────┘
                               │ implements
┌──────────────────────────────┴──────────────────────────────┐
│  services/chess-engine — Person 1: chess truth service      │
│  chess API · rules core · engine service ·                  │
│  facts and verifier · line comparison                       │
└─────────────────────────────────────────────────────────────┘
        later, together: concept attribution
```

## One owner for every overlap

| Overlap | Owner | Rule |
| --- | --- | --- |
| Move legality | Person 1 | The web board may use chess.js for instant drag feedback; the chess service is the final authority |
| Move tree and PGN | Person 1 | `/v1/game` parses games; the web app only displays and navigates them |
| Claim verification | Person 1 builds, Person 2 calls | The coach sends every chess claim to `/v1/verify` before the user sees it |
| Line comparison | Person 1 computes, Person 2 explains | `/v1/compare` returns structured differences |
| Concept attribution | Both, later | Joint milestone |

## Milestones

1. Week 1, together: shared contract (done, `packages/analysis-schema` v0.1.0).
2. Weeks 2–3, separately: Person 1 gets FEN → Stockfish → top 3 moves; Person 2 gets board → chat → mock analysis → LLM explanation.
3. First joint demo: swap the mock for the real service; load a position, analyze it, get a grounded explanation.
4. Then weekly: what-if moves, PGN review, verification.
5. Later, together: concept attribution.
