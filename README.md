# Factle

A daily "spot the fake fact" game. Every day has 5 rounds. Each round shows 5 surprising facts from Wikipedia's "Did you know…?": 4 are true, and 1 is a fake made by changing one detail of a real fact (a number, a year, a country or a nationality). Pick the fake as fast as you can: up to 100 points a round for speed, 0 for a wrong pick, out of 500 a day. Everyone gets the same rounds each UTC day, and there's a shared leaderboard.

**Play:** https://biccyanzac-pixel.github.io/factle/ (also on the [jacob.gg](https://biccyanzac-pixel.github.io/jacob.gg/) hub)

## How it works
```
pipeline/   Python: Wikipedia DYK archive -> facts -> fakes -> daily schedule (runs offline, free)
site/       the static game (GitHub Pages, gh-pages branch = site/)
worker/     leaderboard API (Cloudflare Worker + D1), https://factle-leaderboard.jacob-gg-leaderboard-worker.workers.dev
docs/       decisions: ingest.md (Phase 1), fakes.md (Phase 2), difficulty.md, architecture.md
```
- **Facts** (`pipeline/ingest.py`): 121k DYK hooks are converted to statements and filtered. Facts about living people are excluded using Wikipedia + Wikidata, as are unsuitable topics and fast-changing claims. About 38k facts remain. See `docs/ingest.md`.
- **Fakes** (`pipeline/mutate.py`, `pipeline/checks.py`) are rule-based, with no LLM. Each fake must pass a local contradiction model (MiniLM NLI cross-encoder), a "not true elsewhere" check against the source article and Wikipedia search, and grammar rules. See `docs/fakes.md`.
- **Schedule** (`pipeline/schedule.py`) writes `site/data/days/YYYY-MM-DD.json` and `site/data/index.json`. Days are pre-generated a year ahead. They're public: anyone can read ahead in the repo, which the owner accepted.
- **Leaderboard**: the browser sends only (day, round, pick, time taken). The worker judges the pick and computes the points with the same code the site uses (`site/js/daily.js`).

## Develop
```
python -m venv .venv && .venv/Scripts/pip install requests mwparserfromhell spacy pytest torch transformers sentencepiece protobuf
.venv/Scripts/python -m spacy download en_core_web_lg
node tools/serve.mjs 8081                  # http://localhost:8081/   (?api=http://127.0.0.1:8811 for a local worker)
npm test                                   # JS: dates, timezones, scoring
.venv/Scripts/python -m pytest             # Python: hook parsing, filters, living people, mutations
cd worker && npm install && npm run db:init:local && npm run dev:local   # then: npm test
```
Rebuild the data: `python -m pipeline.fetch_archive && python -m pipeline.parse_hooks && python -m pipeline.ingest`, then
`python -m pipeline.schedule --start <tomorrow> --days N --keep-until <today>`. **Never regenerate past days**: `--keep-until` keeps them.

## Deploy
- Site: `git subtree split --prefix site -b gh-pages && git push -f origin gh-pages`
- Worker: `cd worker && npx wrangler deploy`. **Redeploy whenever `site/data/index.json` or `site/js/daily.js` changes**; the worker bundles them.

## Credits and licences
Facts come from English Wikipedia (CC BY-SA 4.0). Every fact links to its source articles, and the derived dataset (`data/facts.jsonl`, `site/data/days/`) is CC BY-SA 4.0 (`data/README.md`). Wikidata is CC0. The NLI model is cross-encoder/nli-MiniLM2-L6-H768 (Apache-2.0). Game code: no licence chosen yet.
