# Agentic chess coach (Think64)

An AI chess coach that explains positions the way a human coach would. A deterministic
chess service (rules + Stockfish) establishes what is true on the board; an LLM agent
turns that verified evidence into explanations fitted to the player.

## How the repo is split

```
agentic_chess_coach/
├── packages/analysis-schema/   shared contract — both of us, changed only by reviewed PR
├── services/chess-engine/      Person 1: chess truth service (rules, Stockfish, facts, verify)
├── services/coach/             Person 2: coach agent, LLM adapter, player memory, evaluation
├── apps/web/                   Person 2: board, chat, PGN viewer
└── docs/                       architecture and decisions
```

The two halves only meet at `packages/analysis-schema`. Person 2 builds against its mock
server; Person 1 builds the real service and proves it with the contract tests. Connecting
them later means changing one base URL.

| Area | Owner | Done when |
| --- | --- | --- |
| `packages/analysis-schema` | Both | Reviewed by both; CI green |
| `services/chess-engine` | Person 1 | `CONTRACT_BASE_URL=<service> pytest packages/analysis-schema/tests` passes |
| `services/coach`, `apps/web` | Person 2 | Works end to end against the mock, then against the real service |

## Getting started

```bash
cd packages/analysis-schema
pip install -r requirements.txt
pytest tests/                 # checks the contract
python mock/server.py         # mock chess API on http://localhost:8064
```

See [docs/architecture.md](docs/architecture.md) for the full design and
[packages/analysis-schema/README.md](packages/analysis-schema/README.md) for the nine
contract decisions.

## Working rules

- Work on branches and merge through pull requests.
- Any change to `packages/analysis-schema` is its own PR, reviewed by the other person.
- CI runs the contract tests on every push; keep it green.
