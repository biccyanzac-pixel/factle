"""Automatic checks every fake must pass (no human review).

1. contradiction  a local NLI model (MiniLM2-L6 cross-encoder trained on SNLI+MultiNLI, Apache-2.0) must say
                  the fake contradicts the original with probability >= NLI_MIN.
2. not true elsewhere
                  a) the source (subject) article's full text must not contain the new value in a sentence
                     that shares context words with the fake;
                  b) a Wikipedia search for the new value + the fake's key words must not return a snippet
                     that supports it.
3. grammar        handled in pipeline.mutate (a/an fixed, no new negations, length within 12 characters,
                  no doubled words).
Network results are cached in data/cache/ so reruns are cheap.
"""
import html
import json
import pathlib
import re

from pipeline.entities import JsonlCache
from pipeline.wiki import wp

# DeBERTa-v3-base (MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli) gave the same verdicts but ran at ~1 pair/s on this
# CPU; this MiniLM cross-encoder (Apache-2.0) runs ~60 pairs/s.
NLI_MODEL = "cross-encoder/nli-MiniLM2-L6-H768"
NLI_MIN = 0.90
STOP = set("""a an the of in on at to for from by with and or as is was were are be been being that this which who
whom its it his her their they he she after before during over under into than then also only one two three
first new old not but has had have more most about between while when where""".split())


class NLI:
    def __init__(self):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        self.torch = torch
        torch.set_num_threads(max(1, (torch.get_num_threads() or 4)))
        self.tok = AutoTokenizer.from_pretrained(NLI_MODEL)
        self.model = AutoModelForSequenceClassification.from_pretrained(NLI_MODEL).eval()
        labels = {v.lower(): k for k, v in self.model.config.id2label.items()}
        self.ci = labels["contradiction"]

    def contradiction(self, pairs, batch=32):
        out = []
        for i in range(0, len(pairs), batch):
            chunk = pairs[i:i + batch]
            enc = self.tok([p for p, _ in chunk], [h for _, h in chunk], return_tensors="pt", padding=True,
                           truncation=True, max_length=192)
            with self.torch.no_grad():
                probs = self.model(**enc).logits.softmax(-1)
            out += probs[:, self.ci].tolist()
        return out


def content_words(s):
    return {w for w in re.findall(r"[^\W_]+", s.lower()) if w not in STOP and len(w) > 2}


def context_words(fake, m):
    """Content words of the fake excluding the changed value."""
    return content_words(fake) - content_words(m["new"])


def _supports(text, new, ctx, need=2):
    """Does some sentence in text contain `new` (as a whole token) and >= need context words?"""
    pat = re.compile(r"(?<![\w])" + re.escape(new) + r"(?![\w])", re.I)
    for sent in re.split(r"(?<=[.!?])\s+|\n+", text):
        if pat.search(sent) and len(content_words(sent) & ctx) >= need:
            return sent.strip()
    return None


class Support:
    def __init__(self):
        self.extracts = JsonlCache("extracts.jsonl", "title")
        self.searches = JsonlCache("searches.jsonl", "q")

    def extract(self, title):
        if title not in self.extracts:
            d = wp({"action": "query", "prop": "extracts", "explaintext": "1", "titles": title, "redirects": "1"})
            pages = d.get("query", {}).get("pages", [])
            self.extracts.add([{"title": title, "text": pages[0].get("extract", "") if pages else ""}])
        return self.extracts.get(title)["text"]

    def search(self, q):
        if q not in self.searches:
            d = wp({"action": "query", "list": "search", "srsearch": q, "srlimit": "5", "srprop": "snippet"})
            hits = [{"title": h["title"], "snippet": re.sub(r"<[^>]+>", "", html.unescape(h["snippet"]))}
                    for h in d.get("query", {}).get("search", [])]
            self.searches.add([{"q": q, "hits": hits}])
        return self.searches.get(q)["hits"]

    def true_elsewhere(self, fact, m):
        """Return evidence text if the fake might actually be true, else None."""
        ctx = context_words(m["fake"], m)
        new = m["new"]
        for s in fact["sources"]:
            if s["subject"]:
                ev = _supports(self.extract(s["title"]), new, ctx)
                if ev:
                    return f"article {s['title']}: {ev[:200]}"
        keys = sorted(ctx, key=len, reverse=True)[:4]
        q = f'"{new}" ' + " ".join(keys)
        for h in self.search(q)[:5]:
            ev = _supports(h["snippet"], new, ctx, need=3)
            if ev:
                return f"search {h['title']}: {ev[:200]}"
        return None
