# Difficulty

## Proxy: how small the change is
Every fake gets a `difficulty` between 0 (easy) and 1 (hard), computed when it's made (`pipeline/mutate.py`). The idea: a small change is harder to spot than a big one.

| Change | Difficulty | Examples |
|---|---|---|
| year | `1 − min(1, |Δyears| / 30)` | 1953 → 1956 is 0.90 (hard); 1918 → 1893 is 0.17 (easy) |
| decade | same, in 10-year steps | 1880s → 1900s is 0.33 |
| count | `1 − min(1, |ln(new/old)| / ln 5)` | 72 → 144 is 0.57; 13 → 4 is 0.27; ×5 is 0 |
| number word | `1 − |steps| / 8` | five → four is 0.88; five → twelve is 0.12 |
| country / U.S. state / nationality swap | 0.55 (fixed) | Finnish → Swedish |

It can be measured and reproduced, and it needs no model. Its limits: it ignores how surprising the four true facts are, and how much a reader already knows about the topic. Once there's play data, the better measure is the leaderboard's real accuracy per round (picks per round are stored in D1). The proxy can then be recalibrated against it.

## Schedule
Each round has a target difficulty. The generator picks the unused fake closest to that target (plus a little randomness).

- **Within a day:** round 1 targets 0.15, then 0.32, 0.50, 0.66, and round 5 targets 0.82.
- **Across the week:** the whole day shifts by Mon −0.12, Tue −0.06, Wed 0, Thu +0.04, Fri +0.08, Sat +0.12, Sun +0.18.

This is the jacob.gg house curve (see jacob.gg/PLAYBOOK.md): Monday is the easiest day, it rises to Saturday, and Sunday is the super-hard special. Days up to 2026-10-23 were generated with Sunday at +0.05 (about Thursday's level) and are left as they are; the +0.18 applies to days generated after that.
