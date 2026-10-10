# Factle: notes for coding agents

Start with README.md, then docs/ (ingest.md, fakes.md, difficulty.md, architecture.md).

Critical rules:
- Never change a past day: regenerate only future days with `python -m pipeline.schedule --start <tomorrow> --days N --keep-until <today>`. Never change `EPOCH` (site/js/daily.js and pipeline/schedule.py).
- After changing `site/data/index.json` or `site/js/daily.js`, redeploy the worker (`cd worker && npx wrangler deploy`). It bundles both to judge picks.
- Never let a fact about a living person in. Don't loosen pipeline/entities.py, the ingest stages 4–5 or the mutation rule "never swap people" without asking the owner.
- Free project: ask the owner before adding any paid service (e.g. LLM API calls), and give a cost estimate first.
- Commit as `biccyanzac-pixel <285977456+biccyanzac-pixel@users.noreply.github.com>` (repo-local config). Deploy the site with `git subtree split --prefix site -b gh-pages && git push -f origin gh-pages`.
- Local worker port is 8811 (8787/8797/8798 are taken by the other games' workers). Don't touch other games' workers or databases.
- Tests: `.venv/Scripts/python -m pytest`, `npm test`, `cd worker && npm run dev:local` + `npm test`, `node tools/e2e-ui.mjs`.
