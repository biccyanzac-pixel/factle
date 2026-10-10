"""Build the daily schedule: 5 rounds per UTC day, each 4 true facts + 1 fake.

Rules (see docs/difficulty.md for the difficulty proxy):
  - the fake is made from a DIFFERENT fact, whose original is never shown that day
  - parity: number fake -> >= 3 of the 4 true facts contain numbers; place/nationality fake -> >= 3 of the
    4 contain a place or nationality, so the fake can't be spotted by structure alone
  - similar length: true facts within +-35% of the fake's word count
  - no two facts in a day share a source article (mixed topics)
  - a fact is used at most once in the whole schedule (true or as a fake's source), which is stricter than
    "not within 2 years" while the schedule is < 2 years long; reported fakes (data/reported.json) never used
  - difficulty: round 1 easiest -> round 5 hardest; the whole day shifts by weekday (Mon easiest ... Sat hardest,
    Sun about like Thursday)
  - past days are never changed: days up to --keep-until are copied from the existing files

Outputs: site/data/days/YYYY-MM-DD.json and site/data/index.json, plus data/schedule_stats.json
(rejection counts at each check stage).

Usage: python -m pipeline.schedule --start 2026-10-10 --days 366 [--keep-until YYYY-MM-DD] [--dry-run]
"""
import argparse
import collections
import json
import pathlib
import random
import re
from datetime import date, timedelta

from pipeline import mutate
from pipeline.checks import NLI, NLI_MIN, Support
from pipeline.entities import Entities

FACTS = pathlib.Path("data/facts.jsonl")
REPORTED = pathlib.Path("data/reported.json")
SITE_DATA = pathlib.Path("site/data")
DAYS_DIR = SITE_DATA / "days"
STATS = pathlib.Path("data/schedule_stats.json")
EPOCH = "2026-10-10"   # puzzle #1. Never change once live (renumbers every day).
ROUNDS = 5
ROUND_TARGET = [0.15, 0.32, 0.5, 0.66, 0.82]
WEEKDAY_SHIFT = [-0.12, -0.06, 0.0, 0.04, 0.08, 0.12, 0.05]  # Mon..Sun
SEED = 20261009

COUNTRY_T = {"country", "sovereign state", "island country", "island nation"}
STATE_T = {"U.S. state", "state of the United States"}
CITY_RE = re.compile(r"\b(city|town|municipality|capital|metropolis|human settlement|county seat|village|borough)\b",
                     re.I)


def place_kinds(facts, ents):
    kinds = {}
    for f in facts:
        for s in f["sources"]:
            if s["kind"] != "other":
                continue
            p = ents.pages.get(s["title"])
            info = ents.classify(s["title"])[1] if p else {}
            types = set(info.get("types") or [])
            name = s["title"].split(",")[0].split(" (")[0]
            if types & COUNTRY_T:
                kinds[name] = "country"
            elif types & STATE_T:
                kinds[name] = "us_state"
            elif any(CITY_RE.search(t) for t in types):
                kinds.setdefault(name, "city")
    return kinds


def has_place(f):
    return any(e["label"] in ("GPE", "LOC", "NORP") for e in f["entities"])


def subjects(f):
    return {s["title"] for s in f["sources"] if s["subject"]} | {s["title"] for s in f["sources"]}


def day_target(d, r):
    return min(0.95, max(0.05, ROUND_TARGET[r] + WEEKDAY_SHIFT[d.weekday()]))


def load_existing(keep_until):
    kept = {}
    if keep_until and DAYS_DIR.exists():
        for p in sorted(DAYS_DIR.glob("*.json")):
            if p.stem <= keep_until:
                kept[p.stem] = json.loads(p.read_text(encoding="utf-8"))
    return kept


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=EPOCH)
    ap.add_argument("--days", type=int, default=366)
    ap.add_argument("--keep-until", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-candidates", type=int, default=100000,
                    help="how many candidate fakes go through the (slow, CPU) contradiction model")
    a = ap.parse_args()

    facts = [json.loads(l) for l in FACTS.open(encoding="utf-8")]
    by_id = {f["id"]: f for f in facts}
    reported = set(json.loads(REPORTED.read_text())) if REPORTED.exists() else set()
    ents = Entities()
    kinds = place_kinds(facts, ents)
    pools = mutate.build_pools(facts, kinds)
    print(f"{len(facts)} facts; pools: " + ", ".join(f"{k}={len(v)}" for k, v in pools.items()))

    stats = collections.Counter()
    rng = random.Random(SEED)

    # 1. candidate fakes: one random mutation per fact that has any
    cands = []
    for f in facts:
        if f["id"] in reported:
            continue
        cs = mutate.candidates(f, rng, pools, kinds)
        stats["facts_with_a_mutation"] += bool(cs)
        if cs:
            m = rng.choice(cs)
            cands.append((f, m))
    rng.shuffle(cands)
    cands = cands[:a.max_candidates]
    stats["candidates"] = len(cands)
    for _, m in cands:
        stats[f"candidates_{m['kind']}"] += 1
    print(f"{len(cands)} candidate fakes")

    # 2. contradiction check (batched, local model)
    nli = NLI()
    scores = nli.contradiction([(f["statement"], m["fake"]) for f, m in cands])
    passed = []
    for (f, m), p in zip(cands, scores):
        m["nli"] = round(p, 4)
        if p >= NLI_MIN:
            passed.append((f, m))
        else:
            stats["rejected_contradiction"] += 1
    print(f"{len(passed)} pass the contradiction check")

    support = Support()
    kept = load_existing(a.keep_until)
    used = set()
    for day in kept.values():
        for r in day["rounds"]:
            used.update(r["fact_ids"])
    numbered = [f for f in facts if f["has_number"]]
    placed = [f for f in facts if has_place(f)]
    days_out = dict(kept)
    start = date.fromisoformat(a.start)
    fake_pool = passed[:]
    rng.shuffle(fake_pool)

    for i in range(a.days):
        d = start + timedelta(days=i)
        key = d.isoformat()
        if key in days_out:
            continue
        day_subjects, rounds = set(), []
        for r in range(ROUNDS):
            target = day_target(d, r)
            # pick the closest-difficulty unused fake whose source shares no article with today's facts
            fake_pool.sort(key=lambda fm: abs(fm[1]["difficulty"] - target) + rng.random() * 0.05)
            chosen = None
            for idx, (f, m) in enumerate(fake_pool):
                if f["id"] in used or subjects(f) & day_subjects:
                    continue
                ev = support.true_elsewhere(f, m)
                if ev:
                    stats["rejected_true_elsewhere"] += 1
                    m["evidence"] = ev
                    used.add(f["id"])  # never retry this fact as a fake
                    continue
                chosen = (f, m)
                fake_pool.pop(idx)
                break
            if not chosen:
                raise SystemExit(f"ran out of fakes on {key}")
            f, m = chosen
            used.add(f["id"])
            day_subjects |= subjects(f)
            numeric = m["kind"] in ("year", "count", "word")
            pool = numbered if numeric else placed
            lo, hi = f["words"] * 0.65, f["words"] * 1.35
            trues = []
            for _ in range(4000):
                t = rng.choice(pool if len(trues) < 3 else facts)
                if (t["id"] in used or t["id"] in reported or not lo <= t["words"] <= hi
                        or subjects(t) & day_subjects):
                    continue
                trues.append(t)
                used.add(t["id"])
                day_subjects |= subjects(t)
                if len(trues) == 4:
                    break
            if len(trues) < 4:
                raise SystemExit(f"couldn't find true facts for {key} round {r + 1}")
            items = [{"text": t["statement"], "sources": [{"title": s["title"], "url": s["url"]} for s in t["sources"]],
                      "id": t["id"]} for t in trues]
            fake_item = {"text": m["fake"], "sources": [{"title": s["title"], "url": s["url"]} for s in f["sources"]],
                         "id": f["id"]}
            order = items + [fake_item]
            random.Random(f"{key}:{r}").shuffle(order)
            fake_index = order.index(fake_item)
            rounds.append({
                "facts": [{"text": o["text"], "sources": o["sources"]} for o in order],
                "fake": fake_index,
                "original": f["statement"],
                "change": {"kind": m["kind"], "old": m["old"], "new": m["new"], "start": m["start"],
                           "end": m["end"]},
                "difficulty": round(m["difficulty"], 3),
                "nli": m["nli"],
                "fact_ids": [o["id"] for o in order],
            })
        n = (d - date.fromisoformat(EPOCH)).days + 1
        days_out[key] = {"day": key, "number": n, "rounds": rounds}
        stats["days_built"] += 1
        if stats["days_built"] % 30 == 0:
            print(f"  built {stats['days_built']} days (up to {key}); rejected as maybe true so far: "
                  f"{stats['rejected_true_elsewhere']}", flush=True)

    stats["fakes_used"] = sum(len(v["rounds"]) for v in days_out.values())
    STATS.write_text(json.dumps(dict(stats), indent=2), encoding="utf-8")
    print(json.dumps(dict(stats), indent=2))
    if a.dry_run:
        print("dry run: nothing written")
        return
    DAYS_DIR.mkdir(parents=True, exist_ok=True)
    for key, day in days_out.items():
        (DAYS_DIR / f"{key}.json").write_text(json.dumps(day, ensure_ascii=False, separators=(",", ":")),
                                              encoding="utf-8", newline="\n")
    keys = sorted(days_out)
    index = {"epoch": EPOCH, "first": keys[0], "last": keys[-1], "rounds": ROUNDS,
             "answers": {k: [r["fake"] for r in days_out[k]["rounds"]] for k in keys}}
    (SITE_DATA / "index.json").write_text(json.dumps(index, separators=(",", ":")), encoding="utf-8", newline="\n")
    print(f"wrote {len(keys)} days to {DAYS_DIR}")


if __name__ == "__main__":
    main()
