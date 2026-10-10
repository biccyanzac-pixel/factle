# Factle: hosting (as built)

## The owner's decision (2026-10-09)
Puzzles may be publicly readable in the repo ("fine if people can technically see them if they dig around"). Factle therefore uses the same setup as Yogle and ridd-le:

```
public GitHub repo biccyanzac-pixel/factle
  site/  ── gh-pages branch ──► GitHub Pages  https://biccyanzac-pixel.github.io/factle/
           (game + site/data/days/YYYY-MM-DD.json, pre-generated a year ahead)
  worker/ ── wrangler deploy ─► Cloudflare Worker "factle-leaderboard" + D1 "factle-leaderboard"
                                https://factle-leaderboard.jacob-gg-leaderboard-worker.workers.dev
jacob.gg hub (biccyanzac-pixel/jacob.gg) links to /factle/
```

- **Same game for everyone:** each browser loads `data/days/<UTC date>.json`. Nothing is generated at midnight. The day switches at 00:00 UTC.
- **Leaderboard:** the browser sends `(day, round, pick, ms)` after each round. The worker checks the pick against its own bundled `site/data/index.json` and computes the points with `site/js/daily.js` (the same code as the site). Rounds are insert-only and in order, so the first pick counts. Archive replays go on a separate "played later" board.
- **What isn't defended:** the answer files are public, and the time taken is reported by the browser. Someone determined could read ahead or fake a fast time. That's the same trust model as Yogle and ridd-le, accepted for a free static game.

The earlier proposal (future puzzles kept only in D1, answers withheld until a pick) is still possible later. It would move `days/` into D1 and add a `/api/puzzle` endpoint.

## Free-tier limits (checked 2026-10-09 against the official docs)
| Service | Free limit | Factle's use |
|---|---|---|
| GitHub Pages | public repos on free accounts; 1 GB site, 100 GB/month soft bandwidth | about 15 MB of day files |
| Workers requests | 100,000/day | about 7 per player per day (session, 5 rounds, board), so about 14k players/day |
| Workers CPU | 10 ms per request | simple JSON handlers |
| D1 | 5 GB storage, 5M rows read/day, 100k rows written/day | a board view reads about 20 rows (a `totals` table, not every pick); about 4 writes per round, so about 5k players/day before the write limit |
| Cron Triggers | 5 per account | none used |

Sources: developers.cloudflare.com/workers/platform/limits, /d1/platform/limits, /d1/platform/pricing; docs.github.com (Actions billing, schedule events).

## Not done (yet)
- **The nightly job (Phase 4).** The schedule is pre-generated for a year (10 Oct 2026 to 10 Oct 2027), so nothing needs to run nightly yet. A GitHub Actions workflow can't be pushed from this machine: the stored token lacks the `workflow` scope (same as Yogle). Before October 2027, run `python -m pipeline.fetch_archive --refresh-recent 2 && python -m pipeline.parse_hooks && python -m pipeline.ingest && python -m pipeline.schedule --start <next day> --days 366 --keep-until <last day>`, or add the workflow with a token that has that scope.
- **Reported fakes:** the 🚩 button opens a GitHub issue labelled `reported-fake`. To exclude a fact from future schedules, add its id to `data/reported.json`.
