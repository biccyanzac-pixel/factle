"""Schedule from hand-curated facts and fakes (replaces the rule-based fakes from 2026-10-11).

Inputs (written in review batches, see docs/curation.md):
  data/curated/picks-*.jsonl   one line per reviewed fact:
      {"id": fact id, "keep": true}                       an interesting true fact
      {"id": ..., "keep": true, "fake": "...", "old": "span in the original", "new": "replacement",
       "kind": "who|what|where|when|number|claim", "level": 1|2|3}   ... that also has a fake
  level: 1 = a careful reader can spot it, 2 = medium, 3 = very plausible.

Every fake is checked automatically before use:
  - the original contains `old` exactly once and fake == original with old -> new
  - NLI: the fake contradicts the original with p >= NLI_MIN_CURATED (semantic swaps score lower than numbers,
    so the bar is lower than the rule-based 0.90; the Wikipedia check below still applies)
  - not true elsewhere (source article + Wikipedia search), as in pipeline.checks
Rounds: 4 true facts + 1 fake from a different fact; no fact used twice; no two facts from one article per day;
at most one number fake per day; rounds ordered by level (round 1 easiest). Days up to --keep-until are kept.

Usage: python -m pipeline.curated --start 2026-10-11 --keep-until 2026-10-10
"""
import argparse
import collections
import json
import pathlib
import random
from datetime import date, timedelta

from pipeline.checks import NLI, Support
from pipeline.schedule import DAYS_DIR, EPOCH, ROUNDS, SITE_DATA, subjects

FACTS = pathlib.Path("data/facts.jsonl")
CURATED = pathlib.Path("data/curated")
STATS = pathlib.Path("data/curated_stats.json")
NLI_MIN_CURATED = 0.5
SEED = 20261011


def load_picks():
    picks = {}
    for p in sorted(CURATED.glob("picks-*.jsonl")):
        for line in p.open(encoding="utf-8"):
            line = line.strip()
            if line:
                row = json.loads(line)
                picks[row["id"]] = row
    return picks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--keep-until", required=True)
    ap.add_argument("--max-days", type=int, default=366)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    facts = {json.loads(l)["id"]: json.loads(l) for l in FACTS.open(encoding="utf-8")}
    picks = load_picks()
    stats = collections.Counter()

    # days we keep (today and earlier) and the facts they already used
    kept, used = {}, set()
    for p in sorted(DAYS_DIR.glob("*.json")):
        if p.stem <= a.keep_until:
            kept[p.stem] = json.loads(p.read_text(encoding="utf-8"))
            for r in kept[p.stem]["rounds"]:
                used.update(r["fact_ids"])

    # validate fakes
    fakes = []
    for pid, row in picks.items():
        if "fake" not in row or pid in used:
            continue
        f = facts.get(pid)
        if not f:
            stats["fake_unknown_fact"] += 1
            continue
        s = f["statement"]
        if s.count(row["old"]) != 1 or s.replace(row["old"], row["new"]) != row["fake"]:
            stats["fake_bad_span"] += 1
            print(f"  bad span {pid}: {row['old']!r} -> {row['new']!r}")
            continue
        fakes.append((f, row))
    stats["fakes_written"] = len(fakes)

    nli = NLI()
    scores = nli.contradiction([(f["statement"], r["fake"]) for f, r in fakes])
    support = Support()
    ok = []
    for (f, r), p in zip(fakes, scores):
        r["nli"] = round(p, 4)
        if p < NLI_MIN_CURATED:
            stats["rejected_contradiction"] += 1
            print(f"  NLI {p:.2f} rejects: {r['fake']}")
            continue
        m = {"fake": r["fake"], "new": r["new"]}
        ev = support.true_elsewhere(f, m)
        if ev:
            stats["rejected_true_elsewhere"] += 1
            print(f"  maybe true ({ev[:100]}): {r['fake']}")
            continue
        ok.append((f, r))
    stats["fakes_passed"] = len(ok)

    trues = [facts[pid] for pid, row in picks.items() if row.get("keep") and pid not in used and pid in facts
             and "fake" not in row]
    rng = random.Random(SEED)
    rng.shuffle(ok)
    rng.shuffle(trues)
    numbers = [x for x in ok if x[1]["kind"] == "number"]
    others = [x for x in ok if x[1]["kind"] != "number"]

    days_out = dict(kept)
    start = date.fromisoformat(a.start)
    built = 0
    for i in range(a.max_days):
        d = start + timedelta(days=i)
        key = d.isoformat()
        need_fakes = ROUNDS
        if len(others) + min(1, len(numbers)) < need_fakes or len(trues) < 4 * ROUNDS:
            break
        chosen = [numbers.pop()] if numbers and rng.random() < 0.6 else []
        while len(chosen) < need_fakes:
            chosen.append(others.pop())
        chosen.sort(key=lambda x: x[1]["level"])  # round 1 = most spottable
        day_subjects = set()
        for f, _ in chosen:
            day_subjects |= subjects(f)
        rounds = []
        for r_i, (f, r) in enumerate(chosen):
            picked = []
            for t in list(trues):
                if subjects(t) & day_subjects:
                    continue
                picked.append(t)
                trues.remove(t)
                day_subjects |= subjects(t)
                if len(picked) == 4:
                    break
            if len(picked) < 4:
                break
            items = [{"text": t["statement"], "sources": [{"title": s["title"], "url": s["url"]} for s in t["sources"]],
                      "id": t["id"]} for t in picked]
            fake_item = {"text": r["fake"], "sources": [{"title": s["title"], "url": s["url"]} for s in f["sources"]],
                         "id": f["id"]}
            order = items + [fake_item]
            random.Random(f"{key}:{r_i}").shuffle(order)
            st = f["statement"].index(r["old"])
            rounds.append({
                "facts": [{"text": o["text"], "sources": o["sources"]} for o in order],
                "fake": order.index(fake_item),
                "original": f["statement"],
                "change": {"kind": r["kind"], "old": r["old"], "new": r["new"], "start": st, "end": st + len(r["old"])},
                "difficulty": r["level"] / 3,
                "nli": r["nli"],
                "fact_ids": [o["id"] for o in order],
            })
        if len(rounds) < ROUNDS:
            break
        days_out[key] = {"day": key, "number": (d - date.fromisoformat(EPOCH)).days + 1, "rounds": rounds}
        built += 1
    stats["days_built"] = built
    stats["true_facts_left"] = len(trues)
    stats["fakes_left"] = len(others) + len(numbers)
    STATS.write_text(json.dumps(dict(stats), indent=2), encoding="utf-8")
    print(json.dumps(dict(stats), indent=2))
    if a.dry_run or not built:
        print("nothing written" if not built else "dry run: nothing written")
        return
    # remove generated days after the new range so the old rule-based ones can't linger
    last = (start + timedelta(days=built - 1)).isoformat()
    for p in DAYS_DIR.glob("*.json"):
        if p.stem > last:
            p.unlink()
    for key, day in days_out.items():
        if key > a.keep_until:
            (DAYS_DIR / f"{key}.json").write_text(json.dumps(day, ensure_ascii=False, separators=(",", ":")),
                                                  encoding="utf-8", newline="\n")
    keys = sorted(k for k in days_out if k <= last)
    index = {"epoch": EPOCH, "first": keys[0], "last": keys[-1], "rounds": ROUNDS,
             "answers": {k: [r["fake"] for r in days_out[k]["rounds"]] for k in keys}}
    (SITE_DATA / "index.json").write_text(json.dumps(index, separators=(",", ":")), encoding="utf-8", newline="\n")
    print(f"wrote days {a.start} .. {last}")


if __name__ == "__main__":
    main()
