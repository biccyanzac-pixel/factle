"""Second living-people check: every person's name in a fact must itself resolve to a dead person or a non-person.

Found 2026-10-10: hooks that link to an article *about* a person but not the person
("Charlize Theron filmography", "List of Amy Adams performances", "Meryl Streep on screen and stage",
"Dolly Parton as a gay icon") got through, because the name check in pipeline.ingest accepted a PERSON name
whenever it shared a word with any non-person link.

Now, for each fact:
  - names = spaCy PERSON spans + the person part of "derived" links (X filmography/discography/..., List of X ...)
  - a name is safe only if it shares a word with a linked article that is a verified dead person, or if the
    name itself, looked up on Wikipedia, resolves to a dead person or a non-person thing (a fictional character,
    a film named after someone). Living, recently dead, groups, ambiguous or unresolvable names reject the fact.

Usage: python -m pipeline.people_check   (filters data/facts.jsonl in place; rejections -> data/rejected_people.jsonl)
"""
import json
import pathlib
import re

from pipeline.entities import Entities

FACTS = pathlib.Path("data/facts.jsonl")
OUT_REJECTED = pathlib.Path("data/rejected_people.jsonl")
DERIVED_RE = re.compile(
    r"^(?:List of (?P<a>.+?)(?:'s)? (?:performances|songs|works|roles|awards|films|albums|books|paintings|compositions|"
    r"characters|appearances)|(?P<b>.+?)(?:'s)? (?:filmography|discography|bibliography|videography|on screen and stage|"
    r"on stage and screen|awards and nominations|as a gay icon|in popular culture|(?:acting|musical|political|"
    r"football|early) career|public image|legacy|honours|honors))$")


def tokens(s):
    return {t for t in re.findall(r"[^\W\d_]+", s.lower()) if len(t) > 2}


def candidate_names(fact):
    names = {e["text"].removesuffix("'s").removesuffix("’s") for e in fact["entities"] if e["label"] == "PERSON"}
    for s in fact["sources"]:
        m = DERIVED_RE.match(s["title"])
        if m:
            names.add(m.group("a") or m.group("b"))
    return sorted(n.strip() for n in names if n.strip())


def main():
    facts = [json.loads(l) for l in FACTS.open(encoding="utf-8")]
    ents = Entities()
    todo = {n for f in facts for n in candidate_names(f)}
    print(f"{len(todo)} distinct person names to resolve")
    ents.fetch(todo, set())

    kept, rejected = [], []
    for f in facts:
        dead_tokens = [tokens(s["title"]) for s in f["sources"] if s["kind"] == "dead"]
        bad = None
        for name in candidate_names(f):
            t = tokens(name)
            if t and any(t <= d for d in dead_tokens):  # every word of the name, not just a shared surname
                continue
            kind = ents.classify(name)[0]
            if kind in ("dead", "other"):
                continue
            bad = (name, kind)
            break
        if bad:
            rejected.append({"id": f["id"], "text": f["statement"], "name": bad[0], "kind": bad[1]})
        else:
            kept.append(f)
    with FACTS.open("w", encoding="utf-8", newline="\n") as fh:
        for f in kept:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")
    with OUT_REJECTED.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rejected:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    print(f"kept {len(kept)}, rejected {len(rejected)}: {Counter(r['kind'] for r in rejected)}")


if __name__ == "__main__":
    main()
