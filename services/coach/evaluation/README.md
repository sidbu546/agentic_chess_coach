# Evaluation harness

Runs the coach on a fixed set of positions and questions, scores every answer, and compares models.

```bash
cd services/coach && source ../../.venv/bin/activate

python -m evaluation.run                                     # free: scripted stand-in, mock chess API
python -m evaluation.run --llm openai --models gpt-6.1-sol   # real model; asks before spending (~$0.025/answer)
python -m evaluation.run --llm openai --models gpt-6.1-sol,gpt-6.1-terra --judge gpt-6-luna --yes
python -m evaluation.run --only scholar-win-white,game-review-black          # a few cases
python -m evaluation.run --chess-url http://localhost:8064                   # against a running chess service
```

Without `--chess-url` the analysis-schema mock is started in-process. Results are written to
`evaluation/results/<time>.json` (every answer, claim and check) and `.md` (the table below plus
every failed check). That folder is not committed.

## What is scored

[cases.yaml](cases.yaml) has 18 cases: opening moves, pins, mate in one, a finished game, stalemate,
threefold repetition, checkmate in N moves (from the start and mid-game), "best 2 moves", a blunder
review, a whole-game review as Black, an illegal premise, material and pawn structure. Each case sets
the player's level and explanation depth, as player memory would.

| Category | Checks | Why |
| --- | --- | --- |
| **Chess** | No refuted claim reaches the player and no fallback answer; at least N claims verified as supported; the key facts are mentioned; a supported claim tests the right thing (e.g. "doubled c-pawns") | Correctness, grounded in `/v1/verify`, not in the model's say-so |
| **Task** | A verified line ending in mate by the right side in the asked range; a playable line with N moves; the right tool used (`review_game`, `review_last_move`); no disclaimers where the player asked for none | Did it do what was asked |
| **Level** | Length fits the explanation depth (short 90 / normal 230 / detailed 420 words); for beginners, no unexplained jargon ("tempo", "+0.35") and moves explained in words ("Nf3 (knight to f3)") | Level-appropriate explanation |
| **Judge** (optional) | An LLM grades "explains why", "level fit" and "clarity" from 1–5, given the verifier's verdicts so it never judges chess facts itself | What string checks can't see |

Each category is the share of its checks that passed; **Overall** is the mean of the categories.
Cost per answer is the coach's real token usage priced by `coach/pricing.py`; the judge's cost is
reported separately.

## Notes

- With the mock chess API, engine data is fake, so engine-backed claims come back unverifiable and
  "best move" can't be checked. Rules-based checks (legality, mate, pins, material, structure) are real.
  Run with `--chess-url` against the real service for full scores.
- The scripted stand-in is a template, not a reasoner: its score is a floor and a smoke test, not a
  model result.
- Adding a case: append to `cases.yaml`; unknown check names fail loudly.
