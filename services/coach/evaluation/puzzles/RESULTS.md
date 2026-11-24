# Puzzle solving: Think64 vs Claude Opus 5.5

**Question:** is Think64 better at solving chess puzzles than a general-purpose model given a picture
of the board, the way a player would ask Claude?

**Answer:** overall they tie, but Think64 costs a quarter as much, wins clearly on checkmate puzzles,
and never showed an illegal move. Claude is ahead on non-mate puzzles, the gap that connecting
Stockfish is meant to close.

## Setup

- **104 Lichess puzzles** (CC0), fixed in [puzzles.json](puzzles.json): 4 rating bands from 600 to 2600,
  each with 13 checkmate and 13 non-mate ("win material") puzzles. Only well-tested puzzles
  (1,000+ plays, stable rating), at most 3 moves for the solver.
- **Think64**: the coach as the web app calls it, using GPT-6.1 Sol (deep tier), chess tools and claim
  checking. It ran against the mock chess service, so the rules engine was real but there was no Stockfish.
- **Claude**: Claude Opus 5.5, high effort, given a picture of the board drawn from the solver's side
  with the last move highlighted.
- Both get the **same question** and must end with `FINAL: <moves>`. **python-chess grades every
  answer against the known Lichess solution**, so neither system nor any model judges the answers.

## Results

| | **Think64** | **Claude Opus 5.5 (picture)** | Real difference? |
| --- | ---: | ---: | --- |
| **Solved, all 104** | **63 (61%)** | 62 (60%) | Tie (p = 1.0) |
| **Checkmate puzzles (52)** | **47 (90%)** | 36 (69%) | ✅ **Think64** (p = 0.003) |
| **Non-mate puzzles (52)** | 16 (31%) | **26 (50%)** | Claude ahead, borderline (p = 0.05) |
| First move right | **84%** | 79% | |
| **Answers with an illegal move** | **1\*** | 12 | ✅ **Think64** (p = 0.003) |
| False "checkmate" claims | **0** | 4 | Too few cases to prove |
| **Cost per answer** | **$0.030** | $0.123 | **4× cheaper** |
| Cost per solved puzzle | **$0.050** | $0.206 | |

\* The one Think64 "illegal" answer was the word "undetermined" in its final line: a non-answer, not an impossible move.

95% confidence intervals for solved: Think64 51–69%, Claude 50–68%. p-values are exact McNemar tests
on the puzzles only one of the two solved: on checkmates, Think64 solved 12 that Claude missed, and
Claude solved 1 that Think64 missed.

### By difficulty (Lichess rating)

| | 600–1200 | 1200–1600 | 1600–2000 | 2000–2600 |
| --- | ---: | ---: | ---: | ---: |
| Think64 | 18/26 | 18/26 | **16/26** | 11/26 |
| Claude | **21/26** | **19/26** | 11/26 | 11/26 |

## Example: where the general-purpose model fails

Puzzle `1fx8b` (rating 2093, Black to move, mate in 3; solution `Rh3+ gxh3 Qf3+ Kh2 Qxh3#`):

- **Claude:** `FINAL: Qh4#`. It claims checkmate with a move that is **not legal**, because it misread the picture.
- **Think64:** `Rh3+ gxh3 Qf3+ Kh2`, the right line read from the real board (it stopped one move short of the mate).

## What we learned

1. **Checking beats a stronger model where the answer can be checked.** A mate is a mate: the rules
   engine refutes a "mating" line that doesn't mate, and the model must fix it. Hence 90% vs 69% on
   checkmates, with a cheaper model.
2. **Without an engine, "best move" can't be checked.** On non-mate puzzles Think64 is only as good as
   GPT-6.1 Sol, and Claude Opus 5.5 is the stronger model alone. Stockfish's best-move check is the next step.
3. **Pictures cause errors that a real board doesn't.** 12 of Claude's answers had an illegal move and
   4 claimed a false mate. For a coach, one confident wrong "checkmate" teaches the player something false.
4. **Same accuracy at a quarter of the cost** ($0.030 vs $0.123 per answer).

## Reproduce

```bash
cd services/coach && source ../../.venv/bin/activate
export OPENAI_API_KEY=... ANTHROPIC_API_KEY=...
python -m evaluation.puzzles.run --systems think64,claude-image      # ≈ $16; asks before spending
```

Run on 2026-11-24. Model answers vary between runs, so expect a few points of difference on a re-run.
