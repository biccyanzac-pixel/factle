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
