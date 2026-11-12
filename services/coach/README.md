# Coach service — Siddhanth

Turns a player's question into calls to the chess truth service, builds the LLM context,
and returns a grounded, level-appropriate explanation. Every chess claim in an answer is checked
by `/v1/verify` before the player sees it.

## Run it

```bash
# from the repo root, with the mock chess API already running on :8064
source .venv/bin/activate
pip install -r services/coach/requirements.txt
cd services/coach
export OPENAI_API_KEY=...            # optional: without it the coach runs in scripted mode
uvicorn coach.app:app --port 8065
```

The web app (`apps/web`) talks to it at `http://localhost:8065`. Settings are environment variables;
see [.env.example](.env.example).

```bash
pytest                                # 23 tests; starts the analysis-schema mock in-process
```

## How an answer is made

```
question ──► route: fast or deep tier
         ──► /v1/position → context (FEN, piece list, status, material, facts)
         ──► LLM with chess tools ─┬─ analyze_position  → /v1/analyze
                                   ├─ compare_moves     → /v1/compare
                                   ├─ explore_line      → /v1/move ×n, /v1/position, /v1/analyze
                                   └─ review_last_move  → /v1/compare on the previous position
         ──► answer + structured claims (SAN) ──► SAN→UCI by /v1/move ──► /v1/verify
                 refuted/unverifiable ──► one revision round with the verifier's reasons
                 still refuted        ──► safe answer from verified facts only (tier "fallback")
         ──► arrows: SAN moves converted to squares by the chess API
```

| Component | Files | Notes |
| --- | --- | --- |
| Coach agent | `coach/agent.py`, `coach/prompts.py`, `coach/tools.py` | Routing, context, tool loop, verify → revise → fallback |
| LLM adapter | `coach/llm/` | `openai_adapter.py` (Responses API, strict tools + JSON schema, `store=False`); `scripted.py` (no key needed) |
| Cost logging | `coach/pricing.py` | Real token usage per answer (incl. cached and reasoning tokens) → USD, logged and returned to the UI |
| Player memory | — | Next component. Until then every player is treated as `intermediate` (engine depth 16) |

## Models

Default: **GPT-6.1 Sol** for both tiers (chosen 2026-11-11 for strong chess reasoning at a stable
price: $2 / $0.10 cached / $10 per 1M tokens). The tiers differ in reasoning effort: `low` for
quick lookups, `high` for "why", plans, comparisons and multi-move questions, or when the player
turns on **Think harder**. Change a tier's model with `COACH_MODEL_FAST` / `COACH_MODEL_DEEP`.

Adding a provider means one new file in `coach/llm/` implementing `LLMAdapter.run`.

## Rules this service follows

- The LLM never decides chess truth. Moves, evaluations and facts come from the chess API; even
  arrow squares are derived from SAN by `/v1/move`.
- Engine data from the mock is labelled as fake in tool results, so the model doesn't present it.
- `unverifiable` claims are sent back for hedging; `refuted` claims never reach the player.
- A claim must test what its sentence says. A `legal_move`/`legal_line` claim attached to a
  statement about material, files, structure or evaluation is not counted as verified
  (`coach/verification.py`); the model has to use the matching claim type.
- Claims can be about the position after a line (`after`); they are verified in that position.
- Every claim returned carries `checked`, the coach's own description of what the verifier
  tested; the web app shows that next to the tick, not the model's wording.
- Structural claims (material, open files, bishop pair, doubled/isolated/passed pawns) need
  contract v0.2.0. Against an older chess service they come back `unverifiable`, not as errors.
- Coach-side types live here and in `apps/web/src/coach/types.ts`, not in the shared contract.
