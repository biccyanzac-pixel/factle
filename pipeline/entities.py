"""Look up every linked article on Wikipedia + Wikidata, with an on-disk cache (resumable).

Per Wikipedia title  -> data/cache/pages.jsonl  {title, page, qid, living_cat, cats}
  page:       resolved article title after redirects (None if missing)
  living_cat: in Category:Living people / Possibly living people / Year of birth missing (living people)
  cats:       non-hidden categories (only fetched for bold, i.e. subject, articles)
Per Wikidata item    -> data/cache/wikidata.jsonl {qid, p31, born, died, dissolved}
Per P31 type item    -> data/cache/types.jsonl    {qid, label}

Classification (classify()):
  living          human with no date of death and born within the last 115 years (or birth unknown),
                  or in a Wikipedia "living people" category
  recently_dead   human who died in the last 2 years (Wikipedia's BLP policy covers them too)
  dead            human, died (or born more than 115 years ago, Wikipedia's presumed-dead rule)
  people_group    group of people (band, duo, family, siblings, ...) that ended <100 years ago or never
  ambiguous       a disambiguation / list / set-index page (old links whose target changed)
  other           anything else (place, work, organism, event, organisation, ...)
  unknown         no article or no Wikidata item
"""
import json
import pathlib
import re
from datetime import date

from pipeline.wiki import wd, wp

CACHE = pathlib.Path("data/cache")
LIVING_CATS = ["Category:Living people", "Category:Possibly living people",
               "Category:Year of birth missing (living people)"]
THIS_YEAR = date.today().year
PRESUMED_DEAD_AGE = 115
RECENT_DEATH_YEARS = 2

GROUP_TYPE_RE = re.compile(
    r"\b(duo|band|musical group|musical ensemble|music group|girl group|boy band|vocal group|family|families|"
    r"brothers|sisters|siblings|twins|married couple|couple|trio|quartet|quintet|comedy troupe|comedy group|"
    r"dance troupe|dance group|DJ|collective|art group|artist collective|YouTube channel|pseudonym|"
    r"group of humans|human group|duet|ensemble|choir|orchestra|crew|tag team|stable|performing arts group|"
    r"comedy duo|sibling duo|musical duo|musical trio|street artist)\b", re.I)


AMBIGUOUS_TYPE_RE = re.compile(r"disambiguation|Wikimedia list|set index|Wikimedia category|Wikimedia template", re.I)


class JsonlCache:
    def __init__(self, name, key):
        self.path = CACHE / name
        self.key = key
        self.data = {}
        if self.path.exists():
            for line in self.path.open(encoding="utf-8"):
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:  # a torn write; that row is simply fetched again
                    continue
                self.data[row[key]] = row

    def __contains__(self, k):
        return k in self.data

    def get(self, k):
        return self.data.get(k)

    def add(self, rows):
        with self.path.open("a", encoding="utf-8", newline="\n") as fh:
            for row in rows:
                self.data[row[self.key]] = row
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _query_all(params):
    """Run a query, following 'continue' and merging page props/categories."""
    pages, normalized, redirects, cont = {}, {}, {}, {}
    while True:
        d = wp({**params, **cont})
        q = d.get("query", {})
        for n in q.get("normalized", []):
            normalized[n["from"]] = n["to"]
        for r in q.get("redirects", []):
            redirects[r["from"]] = r["to"]
        for p in q.get("pages", []):
            cur = pages.setdefault(p["title"], {"missing": "missing" in p or "invalid" in p, "pageprops": {},
                                                "categories": []})
            cur["pageprops"].update(p.get("pageprops", {}))
            cur["categories"] += [c["title"] for c in p.get("categories", [])]
        if "continue" not in d:
            break
        cont = d["continue"]
    return pages, normalized, redirects


def _resolve(title, normalized, redirects):
    t = normalized.get(title, title)
    seen = set()
    while t in redirects and t not in seen:
        seen.add(t)
        t = redirects[t]
    return t.split("#")[0]


def fetch_pages(titles, cache, with_cats=False, label=""):
    todo = [t for t in titles if t not in cache or (with_cats and cache.get(t).get("cats") is None
                                                     and cache.get(t).get("page"))]
    print(f"{label}: {len(todo)} of {len(titles)} titles to fetch")
    for i in range(0, len(todo), 50):
        batch = todo[i:i + 50]
        params = {"action": "query", "titles": "|".join(batch), "redirects": "1", "prop": "pageprops|categories",
                  "ppprop": "wikibase_item", "cllimit": "max"}
        if with_cats:
            params["clshow"] = "!hidden"
        else:
            params["clcategories"] = "|".join(LIVING_CATS)
        pages, normalized, redirects = _query_all(params)
        rows = []
        for t in batch:
            r = _resolve(t, normalized, redirects)
            p = pages.get(r)
            prev = cache.get(t) or {}
            if not p or p["missing"]:
                rows.append({"title": t, "page": None, "qid": None, "living_cat": False, "cats": None})
                continue
            cats = p["categories"]
            row = {"title": t, "page": r, "qid": p["pageprops"].get("wikibase_item"),
                   "living_cat": any(c in LIVING_CATS for c in cats) if not with_cats else prev.get("living_cat", False),
                   "cats": cats if with_cats else prev.get("cats")}
            if with_cats:
                row["living_cat"] = row["living_cat"] or any(c in LIVING_CATS for c in cats)
            rows.append(row)
        cache.add(rows)
        if (i // 50) % 20 == 0:
            print(f"  {label}: {i + len(batch)}/{len(todo)}", flush=True)


def _year(claim):
    try:
        v = claim["mainsnak"]
        if v.get("snaktype") == "somevalue":
            return "unknown"
        t = v["datavalue"]["value"]["time"]
        return int(re.match(r"([+-]\d+)", t).group(1))
    except (KeyError, TypeError, AttributeError):
        return None


def fetch_wikidata(qids, cache):
    todo = [q for q in qids if q not in cache]
    print(f"wikidata: {len(todo)} of {len(qids)} items to fetch")
    for i in range(0, len(todo), 50):
        batch = todo[i:i + 50]
        d = wd({"action": "wbgetentities", "ids": "|".join(batch), "props": "claims"})
        rows = []
        for q in batch:
            e = d.get("entities", {}).get(q, {})
            claims = e.get("claims", {}) if "missing" not in e else {}
            p31 = [c["mainsnak"]["datavalue"]["value"]["id"] for c in claims.get("P31", [])
                   if c["mainsnak"].get("datavalue")]
            births = [y for y in (_year(c) for c in claims.get("P569", [])) if isinstance(y, int)]
            deaths = [_year(c) for c in claims.get("P570", [])]
            died = None
            if deaths:
                ints = [y for y in deaths if isinstance(y, int)]
                died = max(ints) if ints else "unknown"
            ends = [_year(c) for prop in ("P576", "P582", "P2032") for c in claims.get(prop, [])]
            dissolved = None
            if ends:
                ints = [y for y in ends if isinstance(y, int)]
                dissolved = max(ints) if ints else "unknown"
            rows.append({"qid": q, "p31": p31, "born": min(births) if births else None, "died": died,
                         "dissolved": dissolved})
        cache.add(rows)
        if (i // 50) % 20 == 0:
            print(f"  wikidata: {i + len(batch)}/{len(todo)}", flush=True)


def fetch_type_labels(qids, cache):
    todo = [q for q in qids if q not in cache]
    print(f"types: {len(todo)} of {len(qids)} type labels to fetch")
    for i in range(0, len(todo), 50):
        batch = todo[i:i + 50]
        d = wd({"action": "wbgetentities", "ids": "|".join(batch), "props": "labels", "languages": "en"})
        cache.add([{"qid": q, "label": d.get("entities", {}).get(q, {}).get("labels", {}).get("en", {}).get("value", "")}
                   for q in batch])


class Entities:
    def __init__(self):
        CACHE.mkdir(parents=True, exist_ok=True)
        self.pages = JsonlCache("pages.jsonl", "title")
        self.items = JsonlCache("wikidata.jsonl", "qid")
        self.types = JsonlCache("types.jsonl", "qid")

    def fetch(self, titles, bold_titles):
        fetch_pages(sorted(titles), self.pages, label="pages")
        fetch_pages(sorted(bold_titles), self.pages, with_cats=True, label="subject categories")
        qids = sorted({self.pages.get(t)["qid"] for t in titles if self.pages.get(t) and self.pages.get(t)["qid"]})
        fetch_wikidata(qids, self.items)
        types = sorted({p for q in qids if self.items.get(q) for p in self.items.get(q)["p31"]})
        fetch_type_labels(types, self.types)

    def type_labels(self, item):
        return [self.types.get(p)["label"] for p in item["p31"] if self.types.get(p)]

    def classify(self, title):
        """Return (kind, info) for a linked title. See module docstring for kinds."""
        p = self.pages.get(title)
        if not p or not p["page"]:
            return "unknown", {}
        item = self.items.get(p["qid"]) if p["qid"] else None
        info = {"page": p["page"], "qid": p["qid"]}
        if p["living_cat"]:
            return "living", info
        if not item:
            return "unknown", info
        if "Q5" in item["p31"]:
            died, born = item["died"], item["born"]
            if died == "unknown":
                return "dead", info
            if isinstance(died, int):
                return ("recently_dead" if died >= THIS_YEAR - RECENT_DEATH_YEARS else "dead"), info
            if born is not None and born < THIS_YEAR - PRESUMED_DEAD_AGE:
                return "dead", info
            return "living", info
        labels = self.type_labels(item)
        info["types"] = labels
        # an old link that now points at a disambiguation/list page: we can't tell who is meant
        if any(AMBIGUOUS_TYPE_RE.search(l) for l in labels):
            return "ambiguous", info
        # a group of people counts as possibly having living members unless it ended over 100 years ago
        # (the Beatles are dissolved, but a fake about them is still a claim about living people)
        if any(GROUP_TYPE_RE.search(l) for l in labels):
            d = item["dissolved"]
            if not (isinstance(d, int) and d < THIS_YEAR - 100):
                return "people_group", info
        return "other", info


def main():
    """Fetch lookups for every hook that passes the text filters."""
    from pipeline import filters_text as F
    hooks = [json.loads(l) for l in open("data/hooks.jsonl", encoding="utf-8")]
    keep = [h for h in hooks if not h["problem"] and not F.check(h["statement"], [l["title"] for l in h["links"]])]
    titles = {l["title"] for h in keep for l in h["links"]}
    bold = {l["title"] for h in keep for l in h["links"] if l["bold"]}
    Entities().fetch(titles, bold)


if __name__ == "__main__":
    main()
