"""Helper: turn a compact review list into data/curated/picks-NNN.jsonl (fills in the fake sentence and checks spans).
Usage: python data/curated/write_picks.py NNN < review.txt
review.txt lines:  keep <id>      or      fake <id> | <kind> | <level> | <old> | <new>
"""
import json, sys
facts = {json.loads(l)["id"]: json.loads(l) for l in open("data/facts.jsonl", encoding="utf-8")}
out, bad = [], 0
for line in sys.stdin.read().splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    if line.startswith("keep "):
        fid = line.split()[1]
        if fid not in facts:
            print("unknown", fid); bad += 1; continue
        out.append({"id": fid, "keep": True})
        continue
    head, kind, level, old, new = [x.strip() for x in line[5:].split("|")]
    s = facts[head]["statement"]
    if s.count(old) != 1:
        print(f"span not found once in {head}: {old!r}\n   {s}"); bad += 1; continue
    out.append({"id": head, "keep": True, "fake": s.replace(old, new), "old": old, "new": new, "kind": kind,
                "level": int(level)})
with open(f"data/curated/picks-{sys.argv[1]}.jsonl", "w", encoding="utf-8", newline="\n") as fh:
    for r in out:
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"{len(out)} picks ({sum('fake' in r for r in out)} fakes), {bad} problems")
