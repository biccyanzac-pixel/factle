"""Phase 1 orchestrator: hooks -> filtered, standalone facts.

Stages (a hook is rejected at the first stage it fails; the reason is recorded):
  1. parse            hook could not be converted to a statement (pipeline.parse_hooks)
  2. text filters     length, needs context, unsuitable topic, fast-changing (pipeline.filters_text)
  3. subject          the bold (subject) article is missing / has no Wikidata item
  4. living people    any linked article is a living person, recently dead person or a group of people
                      that may have living members (pipeline.entities)
  5. unlinked person  spaCy (en_core_web_lg) or a role pattern ("footballer Mark Bonner") finds a person's
                      name that is not a linked, verified-dead person; or the fact refers to an unnamed but
                      identifiable person ("the author of X", "its CEO") and isn't clearly pre-1921
  6. sensitive subject the subject article's categories match the unsuitable-topic list
  7. people check     every person's name must itself resolve to a dead person or a non-person
                      (pipeline.people_check; catches links like "X filmography" about living people)

Outputs:
  data/facts.jsonl       the usable facts (CC BY-SA 4.0, derived from Wikipedia)
  data/rejected.jsonl    every rejected hook with its stage and reason
  data/ingest_stats.json counts per stage/reason

Usage: python -m pipeline.ingest [--no-fetch]   (--no-fetch: only use cached lookups)
"""
import argparse
import collections
import json
import pathlib
import re
from urllib.parse import quote

from pipeline import filters_text as F
from pipeline.entities import Entities

HOOKS = pathlib.Path("data/hooks.jsonl")
OUT_FACTS = pathlib.Path("data/facts.jsonl")
OUT_REJECTED = pathlib.Path("data/rejected.jsonl")
OUT_STATS = pathlib.Path("data/ingest_stats.json")

BLOCKING_KINDS = {"living": "living_person", "recently_dead": "recently_dead_person",
                  "people_group": "group_with_living_members", "ambiguous": "ambiguous_link"}
# a role word followed by a capitalised name: "footballer Mark Bonner", "author Guillaume Prévost"
ROLE_NAME_RE = re.compile(
    r"\b(?:[Aa]uthor|[Ww]riter|[Nn]ovelist|[Pp]oet|[Ss]inger|[Ss]ongwriter|[Rr]apper|[Mm]usician|[Cc]omposer|"
    r"[Aa]ctor|[Aa]ctress|[Cc]omedian|[Dd]irector|[Pp]roducer|[Pp]layer|[Ff]ootballer|[Cc]ricketer|[Aa]thlete|"
    r"[Cc]oach|[Pp]olitician|[Jj]ournalist|[Pp]resenter|[Aa]rtist|[Pp]ainter|[Ss]culptor|[Pp]hotographer|"
    r"[Cc]hef|[Bb]usinessman|[Bb]usinesswoman|[Ee]ntrepreneur|CEO|[Ff]ounder|[Ss]cientist|[Pp]rofessor|"
    r"[Aa]rchitect|[Dd]esigner|[Mm]odel|YouTuber|[Bb]logger|[Ii]nfluencer|[Bb]oxer|[Ww]restler|[Jj]ockey|"
    r"[Dd]ancer|[Cc]horeographer|[Ll]awyer|[Jj]udge|[Mm]ayor|[Ss]enator|[Pp]rofessor|[Dd]octor|[Nn]urse|"
    r"[Ee]ngineer|[Ii]nventor|[Ee]xplorer|[Mm]ountaineer|[Ss]wimmer|[Cc]yclist|[Gg]olfer|[Pp]itcher|"
    r"[Gg]oalkeeper|[Dd]rummer|[Gg]uitarist|DJ|[Hh]istorian|[Aa]stronaut|[Pp]ilot)s?\s+"
    r"((?:[A-Z][\w'’.-]+\s+){0,3}[A-Z][\w'’.-]+)")
# category names that every dead person / every article has and that are not about the topic
BENIGN_CAT = re.compile(r"^Category:(?:\d+s?(?: BC| BCE)? (?:births|deaths)|.*\bestablishments\b.*|"
                        r".*\bdisestablishments\b.*)$")
NUMBER_RE = re.compile(r"\b\d[\d,.]*\b|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
                       r"twenty|thirty|forty|fifty|hundred|thousand|million|dozen)\b", re.I)


# "the author of the Alex novels", "Millennium's casting director", "its CEO": an unnamed but identifiable
# person. Allowed only when every year in the fact is <= 1920 (the person is then almost certainly dead).
_ROLE_WORDS = ROLE_NAME_RE.pattern.split(r"\b(?:", 1)[1].split(r")s?\s+", 1)[0]
UNNAMED_ROLE_RE = re.compile(r"(?:\b(?:[Tt]he|[Ii]ts|[Tt]heir|[Ww]hose|[Hh]is|[Hh]er)\s+|['’]s\s+)(?:[\w-]+\s+){0,3}"
                             r"(?:" + _ROLE_WORDS + r"|[Cc]reator|[Cc]asting director|[Ll]ead)s?\b")
YEAR_RE = re.compile(r"\b(1\d{3}|20\d{2})s?\b")


def unnamed_person(statement):
    m = UNNAMED_ROLE_RE.search(statement)
    if not m:
        return None
    years = [int(y) for y in YEAR_RE.findall(statement)]
    if years and max(years) <= 1920:
        return None
    return m.group(0)


def wiki_url(title):
    return "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_"), safe="_(),'-.:")


def tokens(s):
    return {t for t in re.findall(r"[^\W\d_]+", s.lower()) if len(t) > 2}


def unlinked_people(doc, links, ents):
    """PERSON spans not covered by a linked article that is a verified dead person or a non-person thing.

    A span is covered if it shares a word with the label/title of a link whose kind is 'dead' or 'other'
    (so "Ōno's" is covered by an earlier link to "Manami Ōno"). Spans that match a blocking link were
    already rejected in the living-people stage.
    """
    safe = [tokens(l["label"]) | tokens(l["title"]) for l in links if ents[l["title"]][0] in ("dead", "other")]
    missing = []
    names = [e.text for e in doc.ents if e.label_ == "PERSON"] + [m.group(1) for m in ROLE_NAME_RE.finditer(doc.text)]
    for name in names:
        t = tokens(name)
        if not t or not any(t <= s for s in safe):  # all words of the name, not just a shared surname
            missing.append(name)
    return missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    args = ap.parse_args()

    hooks = [json.loads(l) for l in HOOKS.open(encoding="utf-8")]
    stats = collections.Counter()
    rejected, survivors = [], []

    def reject(h, stage, reason, detail=None):
        stats[f"{stage}:{reason}"] += 1
        rejected.append({"id": h["id"], "ran": h["ran"], "stage": stage, "reason": reason, "detail": detail,
                         "text": h["statement"] or h["hook_text"]})

    # 1-2: parse + text filters
    for h in hooks:
        if h["problem"]:
            reject(h, "1_parse", h["problem"].split(":")[0], h["problem"])
            continue
        titles = [l["title"] for l in h["links"]]
        r = F.check(h["statement"], titles)
        if r:
            reject(h, "2_text", r, F.matched_term(h["statement"], titles) if r == "unsuitable_topic" else None)
            continue
        survivors.append(h)
    print(f"after text filters: {len(survivors)}")

    E = Entities()
    if not args.no_fetch:
        E.fetch({l["title"] for h in survivors for l in h["links"]},
                {l["title"] for h in survivors for l in h["links"] if l["bold"]})

    # 3-4: subject + living people
    stage4 = []
    for h in survivors:
        ents = {l["title"]: E.classify(l["title"]) for l in h["links"]}
        h["_ents"] = ents
        bold = [l for l in h["links"] if l["bold"]]
        if not bold:
            reject(h, "3_subject", "no_subject_link")
            continue
        if any(ents[l["title"]][0] == "unknown" for l in bold):
            reject(h, "3_subject", "subject_unverifiable", [l["title"] for l in bold])
            continue
        blocked = [(l["title"], ents[l["title"]][0]) for l in h["links"] if ents[l["title"]][0] in BLOCKING_KINDS]
        if blocked:
            reject(h, "4_living", BLOCKING_KINDS[blocked[0][1]], blocked)
            continue
        stage4.append(h)
    print(f"after living-people check: {len(stage4)}")

    # 5: unlinked people (spaCy NER)
    import spacy
    nlp = spacy.load("en_core_web_lg", disable=["lemmatizer"])
    stage5 = []
    for h, doc in zip(stage4, nlp.pipe((h["statement"] for h in stage4), batch_size=256)):
        missing = unlinked_people(doc, h["links"], h["_ents"])
        if missing:
            reject(h, "5_ner", "unlinked_person", missing)
            continue
        role = unnamed_person(h["statement"])
        if role:
            reject(h, "5_ner", "unnamed_identifiable_person", role)
            continue
        h["_ner"] = [{"text": e.text, "label": e.label_, "start": e.start_char, "end": e.end_char} for e in doc.ents]
        stage5.append(h)
    print(f"after unlinked-person check: {len(stage5)}")

    # 6: sensitive subject categories
    facts = []
    for h in stage5:
        cats = [c for l in h["links"] if l["bold"] for c in (E.pages.get(l["title"]) or {}).get("cats") or []]
        topical = [c for c in cats if not BENIGN_CAT.match(c)]
        hit = next((c for c in topical if F.UNSUITABLE.search(c.split(":", 1)[1]) or F.AIDS.search(c)), None)
        if hit:
            reject(h, "6_category", "sensitive_subject_category", hit)
            continue
        sources = []
        for l in h["links"]:
            page = h["_ents"][l["title"]][1].get("page") or l["title"]
            if page not in [s["title"] for s in sources]:
                sources.append({"title": page, "url": wiki_url(page), "subject": l["bold"],
                                "qid": h["_ents"][l["title"]][1].get("qid"), "kind": h["_ents"][l["title"]][0]})
        facts.append({
            "id": h["id"], "ran": h["ran"], "statement": h["statement"], "words": F.word_count(h["statement"]),
            "has_number": bool(NUMBER_RE.search(h["statement"])), "entities": h["_ner"],
            "sources": sources, "pictured_removed": h["pictured"],
        })

    with OUT_FACTS.open("w", encoding="utf-8", newline="\n") as fh:
        for f in facts:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")
    with OUT_REJECTED.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rejected:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    # second pass: every person's name must itself resolve to a dead person or a non-person (pipeline.people_check)
    from pipeline import people_check
    people_check.main()
    facts = [json.loads(l) for l in OUT_FACTS.open(encoding="utf-8")]
    summary = {"hooks": len(hooks), "facts": len(facts), "rejected": len(rejected),
               "by_reason": dict(sorted(stats.items()))}
    OUT_STATS.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
