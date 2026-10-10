# Curated facts and fakes (from 2026-10-11)

## Why
Player feedback on day 1 (2026-10-10): the facts were "boring, about some random thing no one has heard of", and the fakes "always just change a random number". The rule-based generator (docs/fakes.md) can only nudge numbers, years and countries, and it picked facts at random from 38k, most of them obscure.

## How it works now
1. **Fame filter** (`pipeline/fame.py`): every fact gets the Wikipedia pageviews (average per day over 60 days) of its subject article and of its best-known linked article. Only facts about things people have heard of go forward for review.
2. **Review** (by Claude, in batches): from the fame-ranked shortlist, keep only facts that are genuinely surprising or fun and make sense without context. For about 1 in 5 kept facts, write a fake that changes **the interesting detail**:
   - *what*: the object, animal, food or invention ("three hearts" → "three stomachs")
   - *where*: the place, only where it matters to the surprise
   - *claim*: the action or property ("glows in the dark" → "changes colour")
   - *number*: allowed, but at most one number fake per day
   - **Never** swap in a person's name (no false claims about real people), never add a negation, keep the sentence otherwise identical. The fake must be plausible, not absurd, and must be **false**: never a detail that might also be true (e.g. octopuses do have three hearts AND blue blood, so "blue blood" is not a valid fake for "three hearts").
   - `level` 1–3 = how spottable it is (1 = a careful reader can tell, 3 = very plausible). Rounds go from level 1 to level 3.
3. **Automatic checks** (`pipeline/curated.py`), the same as before: the span must match the original exactly; the NLI model must say the fake contradicts the original (≥ 0.5; semantic swaps score lower than number changes); and the source article plus a Wikipedia search must not support the fake.
4. **Schedule**: `python -m pipeline.curated --start <first new day> --keep-until <today>`.

Files: `data/curated/picks-NNN.jsonl` (one line per reviewed fact; see the docstring in `pipeline/curated.py`), `data/curated_stats.json`.

## Extending
Each day needs 25 facts (20 true + 5 with fakes). To add days, review the next slice of the shortlist into a new `picks-NNN.jsonl`, then rerun `pipeline.curated` with `--keep-until <today>`, redeploy the worker (it bundles `index.json`) and publish the site.
