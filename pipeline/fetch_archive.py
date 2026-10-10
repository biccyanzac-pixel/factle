"""Download every Did You Know archive page as wikitext into data/raw/dyk/.

The archive moved in 2026: it is now "Wikipedia:Did you know archive/YYYY/Month" (the old
"Wikipedia:Recent additions/..." pages redirect there). The current month lives on the root page
"Wikipedia:Did you know archive" until it is archived.

Usage: python -m pipeline.fetch_archive [--refresh-recent N]   (re-download the newest N months + root)
"""
import argparse
import json
import pathlib

from pipeline.wiki import wp

RAW = pathlib.Path("data/raw/dyk")
ROOT_TITLE = "Wikipedia:Did you know archive"


def list_archive_pages():
    titles, cont = [], {}
    while True:
        d = wp({"action": "query", "list": "allpages", "apnamespace": "4", "apprefix": "Did you know archive/",
                "aplimit": "max", **cont})
        titles += [p["title"] for p in d["query"]["allpages"]]
        if "continue" not in d:
            break
        cont = d["continue"]
    # keep only YYYY/Month pages
    return [t for t in titles if len(t.split("/")) == 3 and t.split("/")[1].isdigit()] + [ROOT_TITLE]


def fname(title):
    return RAW / (title.split(":", 1)[1].replace("/", "_").replace(" ", "_") + ".json")


def fetch(titles):
    """prop=revisions with content works for up to 50 titles per request."""
    for i in range(0, len(titles), 50):
        batch = titles[i:i + 50]
        d = wp({"action": "query", "prop": "revisions", "rvprop": "content|ids|timestamp", "rvslots": "main",
                "titles": "|".join(batch)})
        for p in d["query"]["pages"]:
            rev = p["revisions"][0]
            fname(p["title"]).write_text(json.dumps({
                "title": p["title"], "revid": rev["revid"], "timestamp": rev["timestamp"],
                "wikitext": rev["slots"]["main"]["content"],
            }, ensure_ascii=False), encoding="utf-8")
        print(f"fetched {i + len(batch)}/{len(titles)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh-recent", type=int, default=0)
    a = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    titles = list_archive_pages()
    todo = [t for t in titles if not fname(t).exists()]
    if a.refresh_recent:
        months = sorted((t for t in titles if t != ROOT_TITLE), key=_month_key)
        todo = sorted(set(todo) | set(months[-a.refresh_recent:]) | {ROOT_TITLE})
    print(f"{len(titles)} archive pages, downloading {len(todo)}")
    fetch(todo)


MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]


def _month_key(t):
    _, y, m = t.split("/")
    return int(y), MONTHS.index(m)


if __name__ == "__main__":
    main()
