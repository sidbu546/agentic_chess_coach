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

## Puzzle solving: Think64 vs a general-purpose model

**Results: [puzzles/RESULTS.md](puzzles/RESULTS.md)** (Think64 vs Claude Opus 5.5 on all 104 puzzles).

Answers "is the system better than just asking Claude (or Sol) with a picture of the board?"
on 104 Lichess puzzles (CC0): 4 rating bands (600–2600) × mate / other, 13 each, only well-tested
puzzles, at most 3 moves for the solver. The set is fixed in [puzzles/puzzles.json](puzzles/puzzles.json)
and can be rebuilt with `puzzles/build_set.py`.

```bash
python -m evaluation.puzzles.run --systems oracle,random            # free: checks the grader (100% / ~1%)
python -m evaluation.puzzles.run --limit 10                          # small paid pilot; asks first
python -m evaluation.puzzles.run                                     # all 104 puzzles, default systems
python -m evaluation.puzzles.run --systems think64,claude-image --only 1fx8b,0Ktzy
```

| System | What it gets |
| --- | --- |
| `think64` | The coach as the web app calls it: GPT-6.1 Sol deep tier, chess tools, claim checking |
| `claude-image` | Claude Opus 5.5 (high effort) and a picture of the board, as a player would upload it |
| `claude-fen` | Claude Opus 5.5 and the position as FEN text (so misreading the picture is not the only reason it fails) |
| `sol-fen`, `sol-image` | GPT-6.1 Sol alone, same effort: the same model as Think64 without the system around it |

Every system gets the same question and must end with `FINAL: <moves in SAN>`. **python-chess grades
it against the stored solution** — neither system nor any model judges:

- **Solved**: every one of the solver's moves matches the solution (another mating move also counts, as on Lichess)
- **First move**: the key move only, the usual one-move puzzle benchmark
- **Illegal move / Fake mate**: the FINAL line contains an illegal move / a `#` that is not checkmate

The report gives accuracy with a 95% confidence interval, the results by rating band and by type,
$/answer and $/solved, and a **head-to-head** for every pair of systems: the puzzles only one of the
two solved, with an exact McNemar test (p < 0.05 = the difference is unlikely to be luck).
Default run ≈ $25–30 (Claude ~$0.10, Think64 and Sol ~$0.03–0.04 per puzzle); `--limit` runs fewer.
Needs `OPENAI_API_KEY` (Think64, Sol) and `ANTHROPIC_API_KEY` (Claude) in your terminal.

Without Stockfish (today), Think64 can prove a line is legal and that a mate is a mate, but not that
a move is the best: expect the clearest gains on mate puzzles and on illegal / fake-mate answers.
Re-run with `--chess-url` once the real chess service is up to measure the full system.

## Notes

- With the mock chess API, engine data is fake, so engine-backed claims come back unverifiable and
  "best move" can't be checked. Rules-based checks (legality, mate, pins, material, structure) are real.
  Run with `--chess-url` against the real service for full scores.
- The scripted stand-in is a template, not a reasoner: its score is a floor and a smoke test, not a
  model result.
- Adding a case: append to `cases.yaml`; unknown check names fail loudly.
