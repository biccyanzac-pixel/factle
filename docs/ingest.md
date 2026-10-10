# Phase 1: ingest and clean (report)

Status: done (2026-10-09). **Update 2026-10-10:** the owner chose to keep neutral war history, works by living creators and companies, so the current count is **38,019 facts** (`data/ingest_stats.json`). The figures below are from the first run.

## Result
**33,586 usable facts** out of 121,239 unique DYK hooks (28%), covering 2004 to 9 October 2026.

- The game needs 365 true facts a year, plus 365 more as sources for fakes. **The pool covers about 45 years**, even with the 2-year no-reuse rule.
- About **1,100 new usable facts a year** arrive from new DYK hooks (2016–2025 average), three times what the game uses.
- 14,263 facts (42%) contain a number and 29,470 (88%) contain a named place, person, organisation or nationality. That gives the Phase 2 parity rule plenty of material in both groups.
- Length: median 18 words (10% are 12 words or fewer, 10% are 26 or more).

## Source
- The DYK archive **moved in 2026**. It's now `Wikipedia:Did you know archive/YYYY/Month` (274 pages, Feb 2004 to Oct 2026), and the old `Wikipedia:Recent additions/...` titles redirect there. The current month is on the root page `Wikipedia:Did you know archive`, which gets each set as it leaves the Main Page. The nightly job (Phase 4) re-downloads the root page and the latest month (`--refresh-recent 1`).
- Each hook's run date comes from the set's UTC timestamp line (`*'''''00:00, 9 October 2026 (UTC)'''''`), or the day header if there isn't one.
- Only official APIs are used, all serial with a 0.2 s minimum gap and backoff on 429/5xx. Wikipedia requests send `maxlag=5`. Wikidata reads don't send it: its maxlag includes query-service lag (14 s when tested), which is meant to slow bot edits, not reads. User-Agent: `FactleBot/0.1 (<contact>) python-requests/x`. The contact defaults to the planned repo URL; **set `FACTLE_CONTACT` to an email** if you'd rather. The full download took 6 requests, and the entity lookups about 7,000 batched requests (about 2 hours, cached on disk).

## Hook → statement
`* ... that '''[[Suga Shrine (Shinjuku)|a shrine]]'''{{`s}} staircase is popular with fans of ''[[Your Name]]''{{-?}}`
→ `A shrine's staircase is popular with fans of Your Name.`

- Strip `... that` (also `...that`, `…`, `that,`), drop the final `?`, capitalise the first letter (except `eBay`, `iPhone`), add a full stop.
- Links become their visible text, and the linked titles are recorded. Bold links are the hook's subject articles.
- Templates are rendered explicitly: punctuation helpers (`{{`s}}`, `{{-?}}`), `nowrap`, `convert` (the original value and unit only, `200 metres`, so there's one number to mutate), ship prefixes (`HMS Colchester`), `frac` and others. **Any unrecognised template drops the hook (146) instead of guessing.**
- `(pictured)`, `(left)` and similar are removed. Refs, comments and HTML entities are cleaned up.
- 534 hooks couldn't be converted (no `that`, a question inside a title, leftover markup). Merged double hooks ("A, and that B") become "A, and B".

## Filtering rules and counts
Each hook is rejected at the first stage it fails. Counts are hooks rejected at that stage.

| Stage | Rule | Rejected |
|---|---|---|
| 1 Parse | can't be converted cleanly (see above) | 534 |
| 2 Text: unsuitable topic | violence and war, death and tragedy, crime, disease and medicine, hate and slavery, sexual content and profanity, and heavy topics (scandal, coups, gambling, alcohol and drugs, bankruptcy). Checked against the statement **and the linked article titles** (catches "Siege of …", "Murder of …") | 29,213 |
| 2 Text: fast-changing | always: currently, now, still, present, population, records, rankings, living/surviving, charts, views/followers, endangered. Superlatives, "only/first/last", prices and currencies: allowed only when the fact has a year and no present tense ("In 1890 it was the longest bridge" is kept; "It is the longest bridge" is rejected) | 21,828 |
| 2 Text: too long / short | over 30 words / under 6 | 6,484 |
| 2 Text: needs context | starts with a pronoun (He, It, This…); refers to the image, relative time (last year, recently, upcoming, will be) or "you/we" | 2,771 |
| 3 Subject | no bold subject link (252), or the subject article is missing or has no Wikidata item (453) | 705 |
| 4 Living people | **any** linked article is a person with no Wikidata date of death and born within 115 years (or birth unknown), or is in Wikipedia's "Living people" categories | 11,369 |
| 4 Recently dead | a linked person who died in 2024 or later (Wikipedia's BLP policy covers the recently dead too) | 496 |
| 4 Group with living members | a linked band, duo, family, siblings, troupe and so on, **unless it ended over 100 years ago**. The Beatles and ABBA are dissolved but most members are alive | 1,897 |
| 4 Ambiguous link | an old hook link that now points at a disambiguation or list page, so we can't tell who was meant (this leak was found in the audit, e.g. "footballer Mark Bonner") | 2,761 |
| 5 Unlinked person | spaCy `en_core_web_lg` PERSON names, plus a role-word pattern ("author Guillaume Prévost"), that don't match a linked, verified-dead person or a linked non-person | 1,480 |
| 5 Unnamed identifiable person | "the author of the Alex novels", "Millennium's casting director", "its CEO": allowed only if every year in the fact is 1920 or earlier | 1,546 |
| 6 Sensitive subject | the subject article's Wikipedia categories match the unsuitable-topic list (e.g. "Poisonous fungi", "Stamp forgers"). `NNNN births/deaths` categories are ignored | 6,569 |

The rules are deliberately strict. With about 33k facts against 365 a year, a wrongly lost good fact costs nothing, while a kept risky one matters. Known over-rejections:
- war-related history makes up a large share of DYK and is all excluded
- any link to a religion or nationality that resolves to a "group" type
- "Federation of Christian Athletes" matching a role word
- every hook mentioning a death, even a historical one

## Examples
**Kept** (random sample):
- Elizabeth Fox, Baroness Holland was a political hostess who introduced the dahlia to the United Kingdom in 1804.
- Michigan's Alma Downtown Historic District, listed on the National Register of Historic Places in 2013, contains 72 structures.
- The razorfish hides in the spines of sea urchins both for protection and as a hunting strategy.
- After buying a view camera in the 1880s, Marie Hartig Kendall took over 30,000 photographs.
- Tajchy, a network of 60 water reservoirs and more than 100 km of channels, was built in the 1700s to drain flooded silver mines in Banská Štiavnica.
- The 9th-century Lindau Gospels contains two illuminated pages imitating textiles.
- When the sea cucumber Holothuria hilla reproduces by fission, the regenerated part is often paler in colour than the original one.
- 900 volunteers completed the initial work on Camano Island State Park in Washington in a single day.
- Lake Uniamési in East Africa would have been larger than the Black Sea – if it had existed.
- Taco Cat Goat Cheese Pizza is based on Egyptian Ratscrew.

**Rejected:**
| Reason | Example |
|---|---|
| living person | Gerbrand Bakker played a tape recording of a 1994 Eurovision entry as he was given the 2010 IMPAC award (Bakker: living) |
| living person | WDAB sold its former call letters to Michael Bloomberg… (Bloomberg: living) |
| group | 13 + 3 + 1 = Seventeen. (Seventeen, a South Korean band) |
| recently dead | Katerina Clark wrote "a brave and intelligent study of the Soviet novel". |
| ambiguous link | Dr John Billings was an Australian neurologist who developed the Billings ovulation method. ("John Billings" is now a disambiguation page) |
| unlinked person | Swedish champions Harry Ramberg and Curt Östberg defeated two professional tennis duos in 1932… (Östberg not linked) |
| unnamed person | The CEO of Toonlet has also worked on The Sims, SimCity and Spore. |
| unsuitable | Humphrey de Bohun was allegedly killed by a spear… at the Battle of Boroughbridge in 1322. |
| fast-changing | Untersturmführer was the first commissioned officer rank of the German SS. (also unsuitable) |
| needs context | It was J. R. R. Tolkien's intention for Black Speech to be "full of harsh and hideous sounds". |
| sensitive category | The royal fly agaric was the German Mycological Society's "Mushroom of the Year" in 2000. (Poisonous fungi) |
| too long | The Church of St George the Exiler in Famagusta has been used as a Nestorian church, a stable for camels, … |

## Files
| File | What | Committed? |
|---|---|---|
| `pipeline/fetch_archive.py` | download the archive (resumable, `--refresh-recent N`) | yes |
| `pipeline/parse_hooks.py` | wikitext → `data/hooks.jsonl` | yes |
| `pipeline/filters_text.py` | text rules | yes |
| `pipeline/entities.py` | Wikipedia + Wikidata lookups, living/dead/group classification | yes |
| `pipeline/ingest.py` | runs every stage → `data/facts.jsonl`, `data/rejected.jsonl`, `data/ingest_stats.json` | yes |
| `data/facts.jsonl` | the facts (28 MB): statement, run date, words, `has_number`, NER entities, sources with URLs, Wikidata IDs and kinds | private repo only, see open question 1 |
| `data/raw/`, `data/cache/` | downloads and lookup caches | no (gitignored) |
| `tests/` | 50 tests: hook conversion, templates, text rules, role and unnamed-person rules, known living/dead/group examples, "no living source in facts" | yes |

Rerun everything: `python -m pipeline.fetch_archive && python -m pipeline.parse_hooks && python -m pipeline.ingest` (`--no-fetch` uses only the cache). Tests: `python -m pytest`.

## Decisions I made (check these)
1. **Hosting changes to a Cloudflare Worker + D1** (like Yogle and ridd-le), not "publish one file a day". The Worker keeps future puzzles only in D1 and withholds today's answer until you pick. That makes the leaderboard trustworthy (the server judges picks) and keeps future puzzles out of every public place. Details and verified free-tier limits are in `docs/architecture.md`.
2. **Private repo** recommended. If the full fact pool were public, players could search it to spot the fake. CC BY-SA is met by publishing every *shown* fact with its source and licence. Estimated Actions use is 150–300 of the 2,000 free minutes a month.
3. **Families and bands count as living people** unless they ended over 100 years ago.
4. **The recently dead (since 2024) are excluded** as well as the living.
5. **"Not linked" means "not safe".** A person's name in the text that isn't linked to a verified-dead person rejects the hook, even for figures like Belisarius. This costs about 1,500 facts.

## Open questions
1. **The licence obligation for unshown facts.** My reading: CC BY-SA share-alike applies to what's distributed, so publishing only shown facts (with attribution) is enough, and the unshown pool can stay private. Is that how you want it? The alternative is publishing the whole pool, which makes cheating easy.
2. **Works by living creators.** Facts about a book, film or company with a living creator are kept unless the fact refers to the person ("the author of…", which is rejected). A fake such as "*Ethical Oil* won the National Business Book Award in **2013**" is a false claim about a book, not directly about a person. OK, or exclude works whose creator is living? That needs one more Wikidata lookup (P50 author, P57 director, P112 founder) and would cost an estimated few thousand facts.
3. **Organisations and companies** are allowed. Phase 2 mutations only change numbers and swap entities and never add negations, so no fake should be defamatory, but a fake can still be wrong about a real company.
4. **Should war be allowed?** Excluding it removes the biggest single topic (about 4,000 hooks matched "war" or "battle" first). Neutral military history ("a ship built in 1890") is gone too.

## Not verified / known gaps
- spaCy misses some names. The role pattern and the "unnamed person" rule cover the common gaps I found, but a living person named in the text without a link, a role word or an NER tag could still get through. The Phase 2 entity-swap rule ("never swap in a living person") and the player report button are the other defences. **The rate of this is unmeasured.** A hand-labelled audit of, say, 300 random facts would measure it; you asked for no manual checking, so I haven't done one.
- Wikidata errors (a dead person with no date of death is treated as living, which is the safe direction; a living person wrongly given a date of death would be the dangerous direction) are trusted as-is.
- Free-tier limits were read from the official docs on 2026-10-09. Whether static-asset requests count towards the 100k/day Worker limit isn't stated.
- Old hooks (2004–2010) weren't checked for accuracy against today's articles. DYK facts were checked when they ran, but articles can change. The Phase 2 "not true elsewhere" search doesn't recheck true facts; a Phase 2 option is to recheck that each true fact's key detail still appears in its source article.
