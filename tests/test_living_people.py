"""Pipeline test: known living people / groups never reach data/facts.jsonl.

Needs data/facts.jsonl and the lookup cache (run `python -m pipeline.ingest` first); skipped otherwise.
"""
import json
import pathlib

import pytest

from pipeline.entities import Entities

FACTS = pathlib.Path("data/facts.jsonl")
pytestmark = pytest.mark.skipif(not FACTS.exists(), reason="run pipeline.ingest first")

# (linked title, expected kind) - checked against live Wikidata when written (2026-10-09)
KNOWN = [
    ("Zayn Malik", "living"),
    ("Sunjeev Sahota", "living"),
    ("Coen brothers", "people_group"),
    ("The Rolling Stones", "people_group"),
    ("ABBA", "people_group"),          # disbanded, but members are alive
    ("Teodor Mazilu", "dead"),
    ("Wyatt Earp", "dead"),
    ("Octopus", "other"),
    ("Mark Bonner", "ambiguous"),       # now a disambiguation page; the hook meant a footballer
]


@pytest.fixture(scope="module")
def ents():
    return Entities()


@pytest.fixture(scope="module")
def facts():
    return [json.loads(l) for l in FACTS.open(encoding="utf-8")]


@pytest.mark.parametrize("title,kind", KNOWN)
def test_known_classification(ents, title, kind):
    if title not in ents.pages:
        pytest.skip(f"{title} not in lookup cache")
    assert ents.classify(title)[0] == kind


def test_no_living_or_group_source_in_facts(facts):
    bad = [(f["id"], s["title"], s["kind"]) for f in facts for s in f["sources"]
           if s["kind"] in ("living", "recently_dead", "people_group", "unknown") and s["subject"]]
    bad += [(f["id"], s["title"], s["kind"]) for f in facts for s in f["sources"]
            if s["kind"] in ("living", "recently_dead", "people_group")]
    assert bad == []


def test_known_living_names_absent(facts):
    text = "\n".join(f["statement"] for f in facts)
    for name in ("Zayn Malik", "Sunjeev Sahota", "Coen brothers", "Rolling Stones"):
        assert name not in text


def test_articles_about_living_people_caught(facts):
    # found 2026-10-10: links to "X filmography" / "List of X performances" / "X as a gay icon" got through
    text = "\n".join(f["statement"] for f in facts)
    for name in ("Charlize Theron", "Amy Adams", "Meryl Streep", "Ranbir Kapoor", "Miley Cyrus", "Mitt Romney"):
        assert name not in text, name


def test_derived_link_titles():
    from pipeline.people_check import DERIVED_RE
    for title, person in [("Charlize Theron filmography", "Charlize Theron"), ("List of Amy Adams performances", "Amy Adams"),
                          ("Meryl Streep on screen and stage", "Meryl Streep"), ("Dolly Parton as a gay icon", "Dolly Parton")]:
        m = DERIVED_RE.match(title)
        assert m and (m.group("a") or m.group("b")) == person
