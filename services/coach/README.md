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
pytest                                # 68 tests; starts the analysis-schema mock in-process
```

## How an answer is made

```
question ──► player memory: level, explanation depth, recurring mistakes, earlier questions
         ──► route: fast or deep tier
         ──► /v1/position → context (FEN, piece list, status, material, facts)
             + the game so far in SAN (replayed with /v1/move, cached) and the player's side
         ──► LLM with chess tools ─┬─ analyze_position  → /v1/analyze
                                   ├─ compare_moves     → /v1/compare
                                   ├─ explore_line      → /v1/move ×n, /v1/position, /v1/analyze
                                   ├─ review_last_move  → /v1/compare on the previous position
                                   └─ review_game       → /v1/position for every ply (+ /v1/compare with a real engine)
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
| Player memory | `coach/memory.py` | SQLite (`COACH_DB_PATH`). Level, rating, explanation depth, recurring mistakes, past sessions |

## Player memory

Keyed by the `player_id` the web app keeps in the browser (no accounts yet). `p_anonymous` is never stored.

| Endpoint | |
| --- | --- |
| `GET /v1/players/{id}` | Profile: level (chosen, else from rating, else intermediate), rating, explanation depth, recurring mistakes, stats |
| `PATCH /v1/players/{id}` | Change `rating`, `level` (null = use the rating) or `explanation_depth` (`short` / `normal` / `detailed`) |
| `DELETE /v1/players/{id}` | Forget everything stored about the player |
| `GET /v1/players/{id}/sessions` | Past sessions with their first questions |

What it changes in an answer:
- **Level** picks the prompt's level guide and the engine depth (beginner 12, intermediate 16, advanced 20).
  Beginners also get moves explained in words the first time ("Nf3 (knight to f3)").
- **Explanation depth** sets the answer length.
- **Recurring mistakes** (2+ times) and up to four questions from earlier sessions go into the context, so the
  coach can say "this is the hanging-piece pattern again".

Mistakes are recorded when the player asks about a move (`review_last_move`) or about their game or habits
(`review_game`, which goes through every move of the player's side). They come only from the rules engine's
facts before and after each move: a piece left undefended and attacked, an undefended enemy piece not taken,
or a new pin on one of the mover's pieces (pawns only if pinned to the king). Pawns, even trades and moves
that give check are left out. `review_game` also notes opening habits: a knight to the a/h-file in the first
10 moves, the queen out in the first 3, and two or more knights/bishops still at home on move 10.
It also counts material given away (pawns included): material the player had before a move and no longer
has after the reply and their own next move, so an immediate recapture is not counted.

The player's side is the board orientation the web app sends (`player_color`), unless the question says
otherwise ("I am Black"): the model then passes `side` to `review_game`. Only that side's moves are judged. Chat-history turns carry the FEN they were about, and turns about another position are labelled as
such for the model.
With a real engine connected, a pattern counts only if the engine rates the move a mistake (loss > 100 cp).
Asking about the same move twice counts once.

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
- `lines` in the response are the answer's `legal_line`, `legal_move` and `best_move` claims that `/v1/verify` supported
  (a move that only starts a longer line is dropped), with the
  UCI, SAN, FEN and game status after every move (from `/v1/move`). The web app plays them back on
  the board; refuted or unverifiable lines are never playable.
- Every claim returned carries `checked`, the coach's own description of what the verifier
  tested; the web app shows that next to the tick, not the model's wording.
- Structural claims (material, open files, bishop pair, doubled/isolated/passed pawns) need
  contract v0.2.0. Against an older chess service they come back `unverifiable`, not as errors.
- `checkmate` claims are checked by the coach from `/v1/position`'s game status after the line
  (rules engine only, no contract change). Ticks show the chess API's SAN, so a `#` or `+` is never
  the model's own notation.
- "How can White/Black checkmate / win in N moves?" (from any position) gets a direct answer: "I can see
  a win for White: …" with a line that ends with the mating move, no disclaimers. The coach reads the
  range from the question ("4-5 moves" = mate on the winner's 4th or 5th move; "in 11 moves" = 10th or
  11th) and only accepts a line that `/v1/move` confirms ends in checkmate inside it; otherwise the
  model gets the reason and another round (one extra for these requests). Such questions use the deep tier.
  Only "checkmate/mate/win in|within N moves" counts; "no need for checkmate" does not.
- The coach never tells the player about engines, tools or what is connected.
- Coach-side types live here and in `apps/web/src/coach/types.ts`, not in the shared contract.
