# Phase 2: rule-based fakes and the schedule (as built, 2026-10-10)

## The owner's decisions (2026-10-09)
- Puzzles may be public in the repo, so `site/data/days/` is committed.
- Keep facts about works by living creators, companies and neutral war history. Facts about **living people stay excluded**.
- The game is 5 rounds a day. Each round scores 0–100 for speed and 0 for a wrong pick, out of 500. The UI copies ridd-le, with a leaderboard.

## Result
- **366 days × 5 rounds** generated (10 Oct 2026 → 10 Oct 2027), using 1,830 fakes and 7,320 true facts. Each fact appears at most once.
- **Facts:** 38,019 after the war-history change. That leaves about 28.9k unused for future schedules (about 3.9 more years at 9,150 a year), plus about 1,100 new facts a year from DYK.

## How a fake is made (`pipeline/mutate.py`)
Exactly one detail changes:

| Kind | Rule | Candidates |
|---|---|---|
| year | shifted ±2–25 years (decades ±10–30), never after the hook ran, order kept relative to other years; 3-digit years ("in 968") count | 7,669 |
| count | ×/÷ 2–5, rounded to look like the original (30,000 → 90,000), ≥ 2, order kept relative to other numbers, % ≤ 100 | 3,682 |
| number word | two…twelve swapped for another | 2,082 |
| nationality | from a fixed list of 85 adjectives. UK identities never swap with each other ("English → British" would still be true) | 1,990 |
| country / U.S. state | another of the same kind, only where used as a place ("in Peru", not "its United States premiere") | 1,427 |

Never touched:
- people (so no living person can ever be swapped in)
- cities (without each city's country, swaps cross countries and look silly)
- numbers inside names: "No. 9", "BWV 109", "18 Broad Street", "4 x 10 km"
- ranges ("1892–93")
- sentences with two or more places or nationalities (swapping one would make the fake contradict the other)

Grammar: a/an is fixed after the change ("an 18-year-old" → "a 54-year-old"). No new negations, no length change over 12 characters, no doubled words.

## Checks every fake passed (`pipeline/checks.py`) and where candidates were lost
| Stage | In | Rejected | Notes |
|---|---|---|---|
| facts with a usable mutation | 38,019 | 21,169 have none | one random candidate per fact |
| contradiction (NLI ≥ 0.90) | 16,850 | **977 (5.8%)** | `cross-encoder/nli-MiniLM2-L6-H768`, Apache-2.0, local CPU |
| not true elsewhere | 2,056 checked | **226 (11%)** | the new value appears in the source article, or a Wikipedia search snippet, in a sentence sharing context words with the fake |
| used | 1,830 | | |

Only fakes the schedule actually chose were checked against Wikipedia, so the 11% applies to the 2,056 tried. Rejected facts are never retried, as fakes or as true facts. Per-stage counts are in `data/schedule_stats.json`.

**Model change:** the plan named DeBERTa-v3-base (MNLI). It gave the same verdicts on test pairs but ran at about 1 pair/s on this CPU (4.7 hours for all candidates). The MiniLM cross-encoder runs at about 60 pairs/s: real changes score ≥ 0.99 and an identical sentence 0.002.

## Rounds (`pipeline/schedule.py`)
- The fake comes from a different fact, whose original isn't shown that day.
- Parity: a number fake gets at least 3 number facts among the 4 true ones; a place fake gets at least 3 facts with places.
- True facts are within ±35% of the fake's word count.
- No two facts in a day share a source article.
- Difficulty rises from round 1 to round 5 and shifts by weekday (`docs/difficulty.md`).
- The order is shuffled with a seed (day:round), so it's deterministic.
- `--keep-until` keeps past days unchanged when regenerating.

## Tests
- `pytest`: 65 pass. Covers hook conversion, filters, living people, and mutations: ranges, names, untagged years, percentages, order, a/an, nationalities, people never swapped, no negations.
- `npm test`: UTC days and timezone edges (New York evening and UK after midnight), DST, leap years, scoring.
- `worker/test/e2e.mjs`: 16 checks against local D1. Covers the server judging picks, scoring, first pick counts, rounds in order, too-fast and future days rejected, board ranking, the late board, and the days summary.
- `tools/e2e-ui.mjs`: headless Chrome plays all 5 rounds at phone size. Checks scoring, reveal, leaderboard, reload, archive, no horizontal scroll, works with localStorage blocked, no page errors.

## Known gaps
- Fakes weren't reviewed by a person (as asked). Some read oddly, and a few can be spotted from inside the sentence (e.g. the film *13 Lakes* "consists of 32 shots"). The 🚩 button reports these.
- The "not true elsewhere" check is a heuristic: a common value (e.g. "10") can wrongly reject a good fake, and a fake that's true but worded differently elsewhere can slip through.
- **Not built from the original brief:** the Phase 3 LLM generator; confidence mode (replaced by speed scoring); share-link social picks (replaced by the leaderboard); the nightly job (the year is pre-generated, see `docs/architecture.md`).
