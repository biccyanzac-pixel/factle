"""Parse DYK archive wikitext into hooks: plain-text statement, linked articles, run date.

Input:  data/raw/dyk/*.json (from fetch_archive)
Output: data/hooks.jsonl, one hook per line:
  {id, ran, statement, hook_text, links: [{title, label, bold}], pictured, problem}
`problem` is null for a cleanly parsed hook, otherwise the reason it could not be converted
(those hooks are kept in the file so the rejection report can count them).
"""
import hashlib
import html
import json
import pathlib
import re
from datetime import datetime

import mwparserfromhell as mw
from mwparserfromhell.nodes import Comment, ExternalLink, HTMLEntity, Tag, Template, Text, Wikilink

RAW = pathlib.Path("data/raw/dyk")
OUT = pathlib.Path("data/hooks.jsonl")

HOOK_RE = re.compile(r"^\*\s*(?:\.\s*\.\s*\.|…)\s*")
SET_TIME_RE = re.compile(r"^\*\s*'''''\s*(\d{1,2}:\d{2}),\s*(\d{1,2} \w+ \d{4})\s*\(UTC\)")
HEADER_RE = re.compile(r"^===\s*(\d{1,2} \w+ \d{4})\s*===\s*$")

# --- template rendering -------------------------------------------------------------------------

LITERAL = {
    "`s": "'s", "'s": "'s", "-?": "?", "?": "?", "'": "'", "`": "'", '-"': '"', "'\"": "'\"", "' \"": "' \"",
    "nbsp": " ", "shy": "", "mdashb": "—", "mdash": "—", "ndash": "–", "snd": " – ", "spaced ndash": " – ",
    "dollarsign": "$", "circa": "c.", "okina": "ʻ", "sic": "", "-": "", "' \"'": "'\"", "\" '": "\"'",
    "-'": "'", "zwsp": "", "wbr": "", "colon": ":", "pipe": "|", "=": "=", "hair space": "",
}
LAST_ARG = {"nowrap", "nobreak", "nowrap begin", "cuegloss", "nrut", "lang", "transliteration", "transl",
            "noitalic", "small", "smaller", "nowiki", "mlby", "by", "sortname", "angbr", "abbr"}
FIRST_ARG = {"abbr", "abbrlink"}
SHIP_PREFIX = {"hms", "ss", "uss", "sms", "mv", "rms", "hmas", "ms", "usrc", "gs", "smu", "hmcs", "hmnzs", "ins",
               "uscgc", "hmt", "hmy", "ps", "hnlms", "fs", "kms", "jds", "hnoms", "hswms", "sts", "ns", "rv", "usat",
               "ussr", "pns", "bns", "sv", "hmhs", "hmsas", "mt", "hsc", "tsms", "ts"}
# convert/cvt unit codes we render (value + unit name, original unit only so there is one number)
UNITS = {
    "m": "metres", "km": "kilometres", "cm": "centimetres", "mm": "millimetres", "ft": "feet", "in": "inches",
    "mi": "miles", "yd": "yards", "nmi": "nautical miles", "kg": "kilograms", "g": "grams", "lb": "pounds",
    "oz": "ounces", "t": "tonnes", "LT": "long tons", "ST": "short tons", "ha": "hectares", "acre": "acres",
    "km2": "square kilometres", "sqmi": "square miles", "m2": "square metres", "sqft": "square feet",
    "mph": "mph", "km/h": "km/h", "kn": "knots", "°F": "°F", "F": "°F", "°C": "°C", "C": "°C", "L": "litres",
    "l": "litres", "USgal": "US gallons", "impgal": "imperial gallons", "hp": "horsepower", "kW": "kW",
    "m3": "cubic metres", "cuft": "cubic feet", "ly": "light-years", "AU": "AU", "ftin": "feet", "mi2": "square miles",
    "sqkm": "square kilometres", "acres": "acres", "foot": "feet", "feet": "feet", "metre": "metres", "inch": "inches",
}
RANGE_WORDS = {"to", "-", "–", "and", "or", "by", "x", "×", "to(-)", "+/-"}


class Unrenderable(Exception):
    pass


def _arg(t, i):
    """Positional parameter i (1-based) as wikicode, or None."""
    p = [x for x in t.params if not x.showkey]
    return p[i - 1].value if len(p) >= i else None


def _positional(t):
    return [x.value for x in t.params if not x.showkey]


def render_convert(t, ctx):
    vals = [render(v, ctx).strip() for v in _positional(t)]
    if not vals:
        raise Unrenderable("convert")
    out, i = [vals[0]], 1
    while i + 1 < len(vals) and vals[i] in RANGE_WORDS:  # 8|to|9|cm
        out += [vals[i], vals[i + 1]]
        i += 2
    if i >= len(vals) or vals[i] not in UNITS:
        raise Unrenderable(f"convert unit {vals[i] if i < len(vals) else '?'}")
    sing = any(str(p.name).strip() in ("adj", "sing") and str(p.value).strip() in ("on", "yes") for p in t.params)
    unit = UNITS[vals[i]]
    if sing:  # "a 200-metre tower"
        unit = unit.rstrip("s") if not unit.endswith("feet") else unit.replace("feet", "foot")
        return "-".join(out) + "-" + unit
    if vals[i] == "ftin" and i + 1 < len(vals) and vals[i - 1].replace(".", "").isdigit():
        raise Unrenderable("convert ftin")
    return " ".join(out) + " " + unit


def render_template(t, ctx):
    name = str(t.name).strip()
    key = name.lower().replace("_", " ")
    if name in LITERAL:
        return LITERAL[name]
    if key in LITERAL:
        return LITERAL[key]
    if key in ("convert", "cvt"):
        return render_convert(t, ctx)
    if key in FIRST_ARG and _arg(t, 1) is not None:
        return render(_arg(t, 1), ctx)
    if key in LAST_ARG:
        ps = _positional(t)
        if not ps:
            raise Unrenderable(name)
        return render(ps[-1], ctx)
    if key in SHIP_PREFIX:
        n = _arg(t, 1)
        if n is None:
            raise Unrenderable(name)
        return f"{name} {render(n, ctx).strip()}"
    if key == "ship":
        pre, n, disp = _arg(t, 1), _arg(t, 2), _arg(t, 4)
        if pre is None or n is None:
            raise Unrenderable(name)
        if disp is not None and render(disp, ctx).strip() == "2":
            return render(n, ctx).strip()
        return f"{render(pre, ctx).strip()} {render(n, ctx).strip()}"
    if key == "sclass":
        n, kind = _arg(t, 1), _arg(t, 2)
        if n is None or kind is None:
            raise Unrenderable(name)
        return f"{render(n, ctx).strip()}-class {render(kind, ctx).strip()}"
    if key == "frac":
        ps = [render(p, ctx).strip() for p in _positional(t)]
        if len(ps) == 2:
            return f"{ps[0]}/{ps[1]}"
        if len(ps) == 3:
            return f"{ps[0]} {ps[1]}/{ps[2]}"
    raise Unrenderable(name)


# --- wikicode -> plain text ---------------------------------------------------------------------

SKIP_LINK_NS = ("file:", "image:", "category:", "media:")
# links to other wikis/namespaces are not articles we can check (wikt:, commons:, fr:, Wikipedia:, ...)
# (language prefixes are matched lower-case only, so "UFO: Enemy Unknown" stays an article)
INTERWIKI_RE = re.compile(r"^(?:(?i:wikt|wiktionary|w|commons|c|s|q|n|b|v|d|m|meta|species|wikipedia|wp|help|"
                          r"template|portal|user|talk|special)|[a-z]{2,3}(?:-[a-z]+)?)\s*:")


def render(code, ctx, bold=False):
    out = []
    for node in code.nodes:
        if isinstance(node, Text):
            out.append(str(node))
        elif isinstance(node, Wikilink):
            title = str(node.title).strip()
            if title.lower().lstrip(":").startswith(SKIP_LINK_NS):
                continue
            label = render(node.text, ctx, bold) if node.text is not None else title.lstrip(":")
            # [[Foo|]] pipe trick / [[foo]]s suffix are rare in hooks; take the label as written
            target = title.lstrip(":").split("#")[0].strip()
            if target and not INTERWIKI_RE.match(target):
                ctx["links"].append({"title": target[0].upper() + target[1:] if target else target,
                                     "label": label.strip(), "bold": bold})
            out.append(label)
        elif isinstance(node, Tag):
            tag = str(node.tag).lower()
            if tag in ("ref", "references"):
                continue
            if tag == "br":
                out.append(" ")
                continue
            if node.contents is None:
                continue
            out.append(render(node.contents, ctx, bold or tag == "b"))
        elif isinstance(node, Template):
            out.append(render_template(node, ctx))
        elif isinstance(node, HTMLEntity):
            out.append(html.unescape(str(node)))
        elif isinstance(node, ExternalLink):
            if node.title is not None:
                out.append(render(node.title, ctx, bold))
        elif isinstance(node, Comment):
            continue
        else:
            out.append(str(node))
    return "".join(out)


PICTURED_RE = re.compile(
    r"\s*\((?:[^()]{0,25}\b)?(?:pictured|illustrated|shown|depicted|portrayed|photographed|example pictured|"
    r"left|right|centre|center|top|bottom|above|below|inset|in front|background|foreground)(?:\b[^()]{0,25})?\)",
    re.I)


def clean_spaces(s):
    s = html.unescape(s)  # entities inside plain text nodes, e.g. "BWV&nbsp;109"
    s = s.replace(" ", " ").replace("​", "")
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+([,.;:?!])", r"\1", s)
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)
    return s


def to_statement(hook_text):
    """'that octopuses have three hearts?' -> 'Octopuses have three hearts.'  Returns (statement, problem)."""
    s = hook_text
    m = re.match(r"^(?:that|That),?\s+", s)
    if not m:
        return None, "no_that"
    s = s[m.end():]
    s = s.rstrip()
    if s.endswith("?"):
        s = s[:-1].rstrip()
    elif re.search(r"\?[\"'”’]$", s):
        return None, "ends_in_quoted_question"
    else:
        return None, "no_question_mark"
    if "?" in s and not re.search(r"[\"“'][^\"”]*\?[^\"”]*[\"”']", s):
        return None, "multiple_questions"
    if not s:
        return None, "empty"
    s = s.replace(", and that ", ", and ")  # merged double hooks: "A, and that B"
    # capitalise the first letter unless the word is deliberately lower-case-first (iPhone, eBay)
    first = s.split(" ", 1)[0]
    if not (len(first) > 1 and first[0].islower() and any(c.isupper() for c in first[1:])):
        lead = re.match(r"^[\"“'‘(]*", s).end()
        s = s[:lead] + s[lead:lead + 1].upper() + s[lead + 1:]
    if s[-1] in ".!":
        pass
    elif re.search(r"[.!][\"”'’)]$", s):
        pass
    else:
        s += "."
    return s, None


def parse_line(line):
    body = HOOK_RE.sub("", line.strip(), count=1)
    ctx = {"links": []}
    try:
        text = render(mw.parse(body), ctx)
    except Unrenderable as e:
        return {"hook_text": body, "links": [], "statement": None, "pictured": False,
                "problem": f"template:{e}"}
    pictured = bool(PICTURED_RE.search(text))
    text = clean_spaces(PICTURED_RE.sub("", text))
    if "[[" in text or "{{" in text or "<" in text or "''" in text:
        return {"hook_text": text, "links": ctx["links"], "statement": None, "pictured": pictured,
                "problem": "leftover_markup"}
    statement, problem = to_statement(text)
    return {"hook_text": text, "links": ctx["links"], "statement": statement, "pictured": pictured,
            "problem": problem}


def parse_date(s):
    return datetime.strptime(s, "%d %B %Y").date().isoformat()


def parse_page(wikitext):
    day, ran = None, None
    for line in wikitext.splitlines():
        st = line.strip()
        if m := HEADER_RE.match(st):
            try:
                day = parse_date(m.group(1))
            except ValueError:
                pass
            ran = None
            continue
        if m := SET_TIME_RE.match(st):
            try:
                ran = f"{parse_date(m.group(2))}T{int(m.group(1).split(':')[0]):02d}:{m.group(1).split(':')[1]}Z"
            except ValueError:
                pass
            continue
        if HOOK_RE.match(st):
            h = parse_line(st)
            h["ran"] = ran or (day and f"{day}T00:00Z")
            yield h


def hook_id(statement_or_text):
    return hashlib.sha1(statement_or_text.encode("utf-8")).hexdigest()[:12]


def main():
    hooks, seen = [], set()
    dupes = 0
    for f in sorted(RAW.glob("*.json")):
        page = json.loads(f.read_text(encoding="utf-8"))
        for h in parse_page(page["wikitext"]):
            key = h["statement"] or h["hook_text"]
            hid = hook_id(key.lower())
            if hid in seen:
                dupes += 1
                continue
            seen.add(hid)
            h["id"] = hid
            hooks.append(h)
    hooks.sort(key=lambda h: (h["ran"] or "", h["id"]))
    with OUT.open("w", encoding="utf-8", newline="\n") as fh:
        for h in hooks:
            fh.write(json.dumps({k: h[k] for k in ("id", "ran", "statement", "hook_text", "links", "pictured",
                                                   "problem")}, ensure_ascii=False) + "\n")
    ok = sum(1 for h in hooks if not h["problem"])
    print(f"{len(hooks)} unique hooks ({dupes} duplicates dropped), {ok} converted cleanly -> {OUT}")


if __name__ == "__main__":
    main()
