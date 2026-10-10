"""How well-known each fact's topics are: Wikipedia pageviews of its linked articles (last 60 days).

Uses the PageViewInfo API (prop=pageviews), 50 titles per request, cached in data/cache/pageviews.jsonl.
Writes data/fame.json: {fact_id: {"subject": views/day of the best-known subject article,
                                  "max": views/day of the best-known linked article}}
Usage: python -m pipeline.fame
"""
import json
import pathlib

from pipeline.entities import JsonlCache
from pipeline.wiki import wp

FACTS = pathlib.Path("data/facts.jsonl")
OUT = pathlib.Path("data/fame.json")


def fetch(titles, cache):
    todo = [t for t in titles if t not in cache]
    print(f"pageviews: {len(todo)} of {len(titles)} titles to fetch")
    for i in range(0, len(todo), 50):
        batch = todo[i:i + 50]
        views, cont = {}, {}
        while True:
            d = wp({"action": "query", "prop": "pageviews", "pvipdays": "60", "titles": "|".join(batch), **cont})
            for p in d.get("query", {}).get("pages", []):
                pv = p.get("pageviews") or {}
                vals = [v for v in pv.values() if v is not None]
                if vals:
                    views[p["title"]] = round(sum(vals) / len(vals), 1)
            if "continue" not in d:
                break
            cont = d["continue"]
        cache.add([{"title": t, "views": views.get(t, 0)} for t in batch])
        if (i // 50) % 50 == 0:
            print(f"  {i + len(batch)}/{len(todo)}", flush=True)


def main():
    facts = [json.loads(l) for l in FACTS.open(encoding="utf-8")]
    cache = JsonlCache("pageviews.jsonl", "title")
    fetch(sorted({s["title"] for f in facts for s in f["sources"]}), cache)
    out = {}
    for f in facts:
        v = lambda s: (cache.get(s["title"]) or {}).get("views", 0)
        subj = [v(s) for s in f["sources"] if s["subject"]] or [0]
        out[f["id"]] = {"subject": max(subj), "max": max(v(s) for s in f["sources"])}
    OUT.write_text(json.dumps(out), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
