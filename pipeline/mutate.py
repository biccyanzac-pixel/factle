"""Rule-based fake generator: change exactly ONE detail of a true fact (no LLM).

Mutations:
  year     a 4-digit year (or "1880s" decade) shifted by a plausible amount, never after the hook ran,
           and keeping its order relative to every other year in the sentence
  count    a number >= 2 multiplied or divided by 2-5, rounded to look natural; keeps units, never
           negative, keeps order relative to other numbers, percentages stay <= 100
  word     a number word (two..twelve, twenty, ...) swapped for another
  place    a country / U.S. state / city swapped for another of the same kind, taken from other facts
  nation   a nationality adjective (Finnish, Polish, ...) swapped for another
Never: negations, swapping people (so no living person can be swapped in), numbers that are part of
a name (No. 9, BWV 109, 135 East 57th Street), or changes in sentences with two or more places/nationalities
(swapping one would make the fake inconsistent with the other, which gives it away).

Each mutation: {kind, start, end, old, new, fake, difficulty}
`difficulty` in [0, 1]: how small the change is (see docs/difficulty.md).
"""
import math
import random
import re

NUM_LABELS_OK = {"DATE", "CARDINAL", "QUANTITY", "MONEY", "PERCENT", "TIME", None}
NUM_RE = re.compile(r"(?<![\w.,/#–—-])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(s?)(?=$|[\s,.;:!?)\"'’”–—%]|-[a-z])")
NAME_BEFORE_RE = re.compile(r"(?:No\.|Nos\.|BWV|Op\.|K\.|Route|Highway|Interstate|Apollo|Flight|Act|Article|Chapter|"
                            r"Psalm|Symphony|Concerto|Sonata|Opus|Number|Unit|Station|Track|Platform|Gate|Room|"
                            r"Level|Volume|Vol\.|Book|Part|Episode|Season|Series|Mark|Mk\.?|Type|Class|Model|"
                            r"Version|v\.|Pier|Lot|Block|Building|Hall|Street|St\.|Avenue|Ave\.|Road|Rd\.|Lane|"
                            r"U|HMS|SS|USS|Section|Rule|Law|Bill|Resolution|Amendment|Amendments|Proposition)\s*$")
WORD_NUMS = ["two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"]
WORD_NUM_RE = re.compile(r"(?<![\w-])(" + "|".join(WORD_NUMS + [w.capitalize() for w in WORD_NUMS]) + r")(?![\w-])")
NEGATION_RE = re.compile(r"\b(not|never|no|none|nobody|nothing|neither|nor|n't)\b", re.I)


def _entity_at(entities, start, end):
    for e in entities:
        if e["start"] <= start and end <= e["end"]:
            return e
    return None


def _fmt_like(value, original):
    """Format a number like the original (commas, decimals)."""
    if "." in original:
        decimals = len(original.split(".")[1])
        return f"{value:.{decimals}f}"
    v = int(round(value))
    if "," in original or v >= 10000:
        return f"{v:,}"
    return str(v)


def _natural_round(v, original_digits):
    """Round so the new number looks like the original's style (e.g. 30,000 -> 90,000, 72 -> 216)."""
    if v < 20:
        return round(v)
    sig_orig = len(original_digits.rstrip("0")) or 1
    sig = max(1, min(sig_orig, len(str(int(v)))))
    if sig_orig == len(original_digits):  # not a round number: keep it unround but sane
        return int(round(v))
    mag = 10 ** (len(str(int(v))) - sig)
    return int(round(v / mag) * mag)


def _numbers(fact):
    """All mutable numeric tokens: (start, end, text, suffix, value, is_year, is_percent)."""
    s, out = fact["statement"], []
    for m in NUM_RE.finditer(s):
        start, end = m.start(1), m.end(1)
        ent = _entity_at(fact["entities"], start, end)
        if (ent["label"] if ent else None) not in NUM_LABELS_OK:
            continue
        if NAME_BEFORE_RE.search(s[:start]):
            continue
        txt, suffix = m.group(1), m.group(2)
        value = float(txt.replace(",", ""))
        after = s[m.end():m.end() + 9]
        label = ent["label"] if ent else None
        if re.match(r"[–—-]\d", after):  # a range like 1892–93
            continue
        if re.match(r"\s*[x×]\s*\d", after) or re.search(r"\d\s*[x×]\s*$", s[:start]):  # "4 x 10 km relay"
            continue
        if re.match(r"\s+[A-Z]", after) and label != "DATE":  # part of a name: "18 Broad Street"
            continue
        is_percent = after.startswith("%") or after.lstrip().startswith("percent") or after.lstrip().startswith("per cent")
        year_shaped = ("," not in txt and "." not in txt and 100 <= value <= 2099
                       and (len(txt) == 4 or label == "DATE")  # "in 968" is a year too
                       and not re.match(r"\s*-?\s*(?:years?|days?|weeks?|months?|decades?|centur|hours?|minutes?)", after))
        # a year only when spaCy calls it a date ("over 2000 horses" is a count)
        is_year = year_shaped and label == "DATE" and not after.startswith("-") and not is_percent
        if year_shaped and not is_year and label not in ("CARDINAL", "QUANTITY", "MONEY"):
            continue  # year-shaped but not tagged either way: leave it alone
        out.append((start, end + len(suffix), txt, suffix, value, is_year, is_percent))
    return out


def _keeps_order(new, old, others):
    return all((o > old) == (o > new) and (o < old) == (o < new) and o != new for o in others)


def mutate_year(fact, tok, rng, all_nums):
    start, end, txt, suffix, old, *_ = tok
    ran_year = int(fact["ran"][:4])
    years = [t[4] for t in all_nums if t[5] and t[0] != start]
    for _ in range(12):
        if suffix == "s":  # decade
            delta = rng.choice([-30, -20, -10, 10, 20, 30])
        else:
            delta = rng.choice([-1, 1]) * rng.choice([2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 25])
        new = int(old + delta)
        latest = ran_year - 10 if suffix == "s" else ran_year  # "the 2010s" for a 2012 hook reads oddly
        if new > latest or new < (1000 if old >= 1000 else 100) or not _keeps_order(new, old, years):
            continue
        new_txt = f"{new}{suffix}"
        diff = 1 - min(1.0, abs(delta) / 30)
        return {"kind": "year", "start": start, "end": end, "old": f"{txt}{suffix}", "new": new_txt, "difficulty": diff}
    return None


def mutate_count(fact, tok, rng, all_nums):
    start, end, txt, suffix, old, is_year, is_percent = tok
    if suffix or old < 2 or (old != int(old) and old < 1):
        return None
    others = [t[4] for t in all_nums if not t[5] and t[0] != start]
    digits = txt.replace(",", "").split(".")[0]
    for _ in range(12):
        f = rng.choice([2, 2.5, 3, 4, 5])
        new = old * f if (rng.random() < 0.5 or old / f < 2) else old / f
        if "." not in txt:
            new = _natural_round(new, digits)
        if is_percent and new > 100:
            continue
        if new < 2 or new == old or not _keeps_order(new, old, others):
            continue
        new_txt = _fmt_like(new, txt)
        if new_txt == txt:
            continue
        diff = 1 - min(1.0, abs(math.log(new / old)) / math.log(5))
        return {"kind": "count", "start": start, "end": end, "old": txt, "new": new_txt, "difficulty": diff}
    return None


def mutate_word_number(fact, rng):
    s = fact["statement"]
    ms = list(WORD_NUM_RE.finditer(s))
    if len(ms) != 1:
        return None
    m = ms[0]
    ent = _entity_at(fact["entities"], m.start(), m.end())
    if (ent["label"] if ent else None) not in NUM_LABELS_OK:
        return None
    old = m.group(1)
    i = WORD_NUMS.index(old.lower())
    choices = [w for j, w in enumerate(WORD_NUMS) if j != i and abs(j - i) >= 1]
    new = rng.choice(choices)
    if old[0].isupper():
        new = new.capitalize()
    diff = 1 - min(1.0, abs(WORD_NUMS.index(new.lower()) - i) / 8)
    return {"kind": "word", "start": m.start(), "end": m.end(), "old": old, "new": new, "difficulty": diff}


# --- entity swaps --------------------------------------------------------------------------------

# nationality adjectives that can be swapped for each other (spaCy's NORP also covers religions and regions)
NATIONALITIES = set("""Afghan Albanian Algerian American Argentine Argentinian Armenian Australian Austrian Bangladeshi
Belgian Bolivian Brazilian British Bulgarian Burmese Cambodian Cameroonian Canadian Chilean Chinese Colombian Croatian
Cuban Czech Danish Dutch Ecuadorian Egyptian English Estonian Ethiopian Filipino Finnish French Georgian German Ghanaian
Greek Guatemalan Hungarian Icelandic Indian Indonesian Iranian Iraqi Irish Israeli Italian Jamaican Japanese Jordanian
Kenyan Korean Latvian Lebanese Lithuanian Malaysian Maltese Mexican Mongolian Moroccan Nepali Nigerian Norwegian
Pakistani Peruvian Polish Portuguese Romanian Russian Saudi Scottish Serbian Singaporean Slovak Slovenian Somali
Spanish Swedish Swiss Syrian Taiwanese Thai Tunisian Turkish Ugandan Ukrainian Uruguayan Venezuelan Vietnamese Welsh
Zimbabwean""".split()) - {"Argentinian"}
# overlapping identities: an English showman is also British, so these never swap with each other
OVERLAPPING = [{"British", "English", "Scottish", "Welsh", "Irish"}]
PLACE_BEFORE_RE = re.compile(r"(?:\b(?:in|of|from|to|across|throughout|within|near|into|at|for)|,)\s+(?:the\s+)?$")
NATION_ADJ_RE = re.compile(r"^(?:" + "|".join(sorted(NATIONALITIES)) + r")$")


def build_pools(facts, place_kinds):
    """Swap pools from all facts: nationality adjectives and places by kind, with frequencies."""
    from collections import Counter
    nations, places = Counter(), {k: Counter() for k in ("country", "us_state", "city")}
    for f in facts:
        for e in f["entities"]:
            t = e["text"]
            if e["label"] == "NORP" and NATION_ADJ_RE.match(t):
                nations[t] += 1
            elif e["label"] == "GPE" and t in place_kinds:
                places[place_kinds[t]][t] += 1
    pools = {"nation": [w for w, n in nations.items() if n >= 15]}
    # cities are not swapped: without each city's country, swaps cross countries and look silly
    places.pop("city")
    for k, c in places.items():
        pools[k] = [w for w, n in c.items() if n >= 10]
    return pools


def mutate_entity(fact, rng, pools, place_kinds):
    places = [e for e in fact["entities"] if e["label"] in ("GPE", "LOC", "NORP")]
    if len(places) != 1:
        return None
    e = places[0]
    t = e["text"]
    if e["label"] == "NORP" and NATION_ADJ_RE.match(t) and t in pools["nation"]:
        pool, kind = pools["nation"], "nation"
    elif e["label"] == "GPE" and t in place_kinds and pools.get(place_kinds[t]):
        pool, kind = pools[place_kinds[t]], "place"
    else:
        return None
    s = fact["statement"]
    # a country only where it's used as a place ("in Peru"), not as an adjective ("its United States premiere")
    if kind == "place" and not PLACE_BEFORE_RE.search(s[:e["start"]]):
        return None
    overlap = next((g for g in OVERLAPPING if t in g), set())
    choices = [p for p in pool if p != t and p not in s and t not in p and p not in t and p not in overlap]
    if not choices:
        return None
    new = rng.choice(choices)
    return {"kind": kind, "start": e["start"], "end": e["end"], "old": t, "new": new, "difficulty": 0.55}


# --- grammar fixes -------------------------------------------------------------------------------

def _starts_with_vowel_sound(word):
    w = word.lower().lstrip("\"'“‘(")
    if re.match(r"\d", w):
        digits = re.match(r"[\d,]+", w).group(0).replace(",", "")
        return digits.startswith("8") or (digits[:2] in ("11", "18") and len(digits) % 3 == 2)
    if re.match(r"(uni|use|usu|uk|eu|one|once|ur)", w):
        return False
    if re.match(r"(hour|honest|honou?r|heir)", w):
        return True
    return w[:1] in "aeiou"


def apply(fact, m):
    """Apply a mutation and fix a/an in front of the changed word. Returns the fake sentence."""
    s = fact["statement"]
    new = m["new"]
    if m["start"] == 0 or s[:m["start"]].rstrip().endswith((".", "!", "?")):
        new = new[:1].upper() + new[1:]
    fake = s[:m["start"]] + new + s[m["end"]:]
    before = fake[:m["start"]]
    am = re.search(r"\b([Aa]n?)\s+$", before)
    if am:
        want = "an" if _starts_with_vowel_sound(new) else "a"
        if am.group(1)[0] == "A":
            want = want.capitalize()
        fake = before[:am.start(1)] + want + before[am.end(1):] + fake[m["start"]:]
    return fake


def grammar_ok(original, fake, m):
    if NEGATION_RE.search(fake) and not NEGATION_RE.search(original):
        return False
    if abs(len(fake) - len(original)) > 12:
        return False
    if re.search(r"\b(\w+)\s+\1\b", fake, re.I) and not re.search(r"\b(\w+)\s+\1\b", original, re.I):
        return False
    return True


def candidates(fact, rng, pools, place_kinds):
    """All valid single-detail mutations for a fact (at most one per detail)."""
    out = []
    nums = _numbers(fact)
    for tok in nums:
        mm = mutate_year(fact, tok, rng, nums) if tok[5] else mutate_count(fact, tok, rng, nums)
        if mm:
            out.append(mm)
    w = mutate_word_number(fact, rng)
    if w:
        out.append(w)
    e = mutate_entity(fact, rng, pools, place_kinds)
    if e:
        out.append(e)
    res = []
    for m in out:
        fake = apply(fact, m)
        if fake != fact["statement"] and grammar_ok(fact["statement"], fake, m):
            res.append({**m, "fake": fake})
    return res
