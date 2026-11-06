# Coach service — Person 2

Turns a player's question into calls to the chess truth service, builds the LLM context,
and returns a grounded, level-appropriate explanation.

## Components

| Component | What it does |
| --- | --- |
| Coach agent | Question → tool calls to the chess API → context → LLM → `/v1/verify` on every chess claim → answer |
| LLM adapter | One wrapper around the model provider with structured JSON output, so the model can be swapped |
| Player memory | Rating, level, preferred explanation depth, recurring mistakes, past sessions |
| Evaluation harness | Fixed test positions and questions; scores answers for correctness and level fit |

## Getting started

1. Run the mock: `python ../../packages/analysis-schema/mock/server.py` (http://localhost:8064).
2. Use the generated types: TypeScript in `../../packages/analysis-schema/types/typescript`,
   Python in `../../packages/analysis-schema/types/python/models.py`.
3. Keep the chess API base URL in config, so switching to the real service is one change.

Coach-side types (player profile, coach messages, board annotations) live here, not in the
shared contract, because they never cross the boundary.
