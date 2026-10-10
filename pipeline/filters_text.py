"""Text-only filters for hooks (no network). Each rule returns a reason code or None.

Rules are deliberately conservative: the archive has ~120k hooks and the game needs ~365 a year,
so it is far better to throw away a good fact than to keep a risky one.
"""
import re

MAX_WORDS = 30
MIN_WORDS = 6


def _rx(words, flags=re.I):
    return re.compile(r"\b(?:" + "|".join(words) + r")\b", flags)


# --- needs context to understand ---------------------------------------------------------------
CONTEXT_START = re.compile(r"^[\"“']?(?:He|She|It|They|His|Her|Its|Their|Them|This|These|Those|Him)\b")
CONTEXT_WORDS = _rx([
    r"pictured", r"shown here", r"seen here", r"depicted here", r"photographed here", r"the image",
    r"this (?:image|photo|photograph|picture|painting|statue|building|man|woman|person|bird|animal|species|plant)",
    r"last (?:week|month|year|season|weekend)", r"this (?:week|month|year|season|weekend)",
    r"next (?:week|month|year|season)", r"yesterday", r"tomorrow", r"tonight", r"recently", r"upcoming", r"soon",
    r"ago", r"will be", r"is scheduled", r"are scheduled", r"is set to", r"are set to", r"is expected", r"is due to",
    r"you", r"your", r"yours", r"we", r"our", r"ours",
])

# --- fast-changing facts -----------------------------------------------------------------------
ALWAYS_CHANGING = _rx([
    r"currently", r"current", r"as of", r"present", r"present-day", r"ongoing", r"incumbent", r"now", r"nowadays", r"presently", r"to date", r"so far", r"today",
    r"still", r"population", r"populations", r"inhabitants", r"residents", r"people live", r"live there",
    r"ranked", r"ranking", r"rankings", r"rank", r"ranks", r"world records?", r"records?", r"record-breaking",
    r"record-holder", r"living", r"surviving", r"survivors?", r"remaining", r"extant", r"followers", r"subscribers",
    r"views", r"viewers", r"downloads", r"streams", r"best-selling", r"bestselling", r"top-selling", r"chart",
    r"charts", r"charted", r"Billboard", r"number one", r"No\. ?1", r"top \d+", r"endangered", r"critically",
    r"extinct in the wild", r"under construction", r"proposed",
])
SUPERLATIVE = _rx([
    r"\w+est", r"most", r"least", r"only", r"first", r"last", r"world's", r"every", r"no other", r"none",
    r"price", r"prices", r"costs?", r"worth", r"valued", r"million", r"billion",
])
# words ending in -est that are not superlatives
NOT_SUPERLATIVE = {"interest", "forest", "west", "test", "nest", "rest", "guest", "quest", "honest", "chest",
                   "protest", "contest", "request", "harvest", "modest", "arrest", "suggest", "invest", "digest",
                   "manifest", "priest", "conquest", "lest", "pest", "vest", "crest", "zest", "jest", "behest",
                   "everest", "budapest", "bucharest", "midwest", "northwest", "southwest", "earnest", "inquest",
                   "attest", "detest", "unrest", "molest", "infest", "celest", "tempest", "bequest", "forrest",
                   "ernest", "almost", "against", "amongst", "midst", "sunniest", "harvests", "festival"}
CURRENCY = re.compile(r"[$£€¥₹]|\b(?:dollars?|pounds sterling|euros?|yen|rupees?|francs?)\b", re.I)
PRESENT = _rx([r"is", r"are", r"has", r"have", r"remains", r"remain", r"holds", r"hold", r"isn't", r"aren't"])
YEAR = re.compile(r"\b(?:1\d{3}|20\d{2})s?\b")

# --- unsuitable for a family game --------------------------------------------------------------
UNSUITABLE = _rx([
    # violence (neutral war/military history is allowed: owner decision 2026-10-09)
    r"kill(?:s|ed|ing|er|ers)?", r"murder\w*", r"assassin\w*", r"massacre\w*", r"genocide\w*", r"slaughter\w*",
    r"bomb\w*", r"shoot\w*", r"shot dead",
    r"was shot", r"were shot", r"gunshots?", r"guns?", r"gunm[ae]n", r"gunfire", r"rifles?", r"pistols?",
    r"weapons?", 
    r"attack\w*", r"assault\w*", 
    r"terror\w*", r"hostages?", r"kidnap\w*", r"abduct\w*", r"rap(?:e|ed|es|ist|ists)", r"sexual\w*", r"sex",
    r"sexy", r"porn\w*", r"nude\w*", r"naked", r"prostitut\w*", r"brothels?", r"abus\w*", r"tortur\w*",
    r"execut(?:ed|ion|ions|ioner)", r"hanged", r"lynch\w*", r"behead\w*", r"decapitat\w*", r"stab\w*",
    r"injur\w*", r"wound\w*", r"blood\w*", r"violen\w*", 
    r"riots?", r"rioters?", r"casualt\w*", r"fatal\w*", r"victims?", r"martyr\w*", r"atrocit\w*",
    r"explosi\w*", r"grenades?", 
    r"shell(?:ed|ing)", r"sniper\w*", r"wounded", r"slain", r"duel\w*", r"poison\w*",
    r"strangl\w*", r"suffocat\w*", r"mutilat\w*", r"cannibal\w*", r"human sacrifice\w*", r"sacrificed",
    # death and tragedy
    r"death\w*", r"dead", r"die", r"died", r"dies", r"dying", r"deceased", r"funerals?", r"burials?", r"buried",
    r"graves?", r"gravestones?", r"cemeter\w*", r"corpses?", r"remains of", r"mummif\w*", r"suicid\w*",
    r"drown\w*", r"accident\w*", r"crash\w*", r"disasters?", r"disastrous", r"catastroph\w*", r"traged\w*",
    r"tragic", r"famine\w*", r"starv\w*", r"earthquakes?", r"floods?", r"flooding", r"tsunamis?", r"hurricanes?",
    r"tornado\w*", r"eruption killed", r"caught fire", r"burned down", r"burnt down", r"destroyed by fire",
    r"fire killed", r"orphan\w*", r"widow\w*", r"mourn\w*", r"perish\w*", r"collapse killed", r"lost at sea",
    r"coffins?", r"autops\w*", r"euthanas\w*", r"posthumous\w*", r"obituar\w*", r"deathbed", r"killed in action",
    # crime
    r"crimes?", r"criminal\w*", r"convict\w*", r"sentenced", r"prison\w*", r"jail\w*", r"imprison\w*", r"arrest\w*",
    r"police\w*", r"theft\w*", r"thie\w*", r"stole", r"stolen", r"steal\w*", r"robber\w*", r"robbed", r"fraud\w*",
    r"smuggl\w*", r"gangs?", r"gangster\w*", r"mafia", r"mobster\w*", r"drugs?", r"cocaine", r"heroin", r"cannabis",
    r"marijuana", r"opium", r"narcotic\w*", r"trials?", r"prosecut\w*", r"illegal\w*", r"outlaw\w*", r"bandit\w*",
    r"pirates?", r"piracy", r"convicts?", r"felon\w*", r"manslaughter", r"homicid\w*", r"extort\w*", r"brib\w*",
    r"arms dealw*", r"arms trade", r"embezzl\w*", r"counterfeit\w*", r"forger\w*", r"scam\w*", r"swindl\w*", r"lawsuits?", r"sued", r"acquitt\w*",
    r"guilty", r"exiled?", r"banished", r"escaped from",
    # disease and medicine
    r"disease\w*", r"cancer\w*", r"tumou?rs?", r"illness\w*", r"ill", r"sick\w*", r"virus\w*", r"infect\w*",
    r"epidemic\w*", r"pandemic\w*", r"plagues?", r"covid\w*", r"coronavirus\w*", r"HIV", r"tuberculosis", r"leprosy",
    r"lepers?", r"polio", r"smallpox", r"cholera", r"malaria", r"syphilis", r"ebola", r"influenza", r"flu",
    r"dementia", r"alzheimer\w*", r"stroke", r"heart attack", r"overdos\w*", r"addict\w*", r"psychiatric", r"asylums?",
    r"insan\w*", r"mental illness", r"amputat\w*", r"surger\w*", r"diagnos\w*", r"symptoms?", r"patients?",
    r"terminal\w*", r"pathogen\w*", r"parasit\w*", r"vomit\w*", r"miscarriag\w*", r"abortion\w*", r"pregnan\w*",
    r"leukemia", r"leukaemia", r"diabetes", r"autism", r"autistic", r"disabilit\w*", r"blind\w*", r"deaf\w*",
    # hate, extremism, slavery
    r"nazis?", r"nazism", r"hitler\w*", r"holocaust", r"fascis\w*", r"racis\w*", r"racial\w*", r"slaves?",
    r"slavery", r"enslav\w*", r"ku klux", r"kkk", r"apartheid", r"supremac\w*", r"antisemit\w*", r"anti-semit\w*",
    r"jihad\w*", r"extremis\w*", r"segregat\w*", r"persecut\w*", r"pogroms?", r"concentration camps?",
    r"ethnic cleansing", r"lynching", r"swastikas?", r"hate", r"slurs?",
    # sexual content and profanity
    r"fuck\w*", r"shit\w*", r"bitch\w*", r"asshole\w*", r"damn\w*", r"crap\w*", r"piss\w*", r"bastard\w*",
    r"whore\w*", r"cunt\w*", r"dick", r"penis\w*", r"vagina\w*", r"testic\w*", r"breasts?", r"nipples?", r"condoms?",
    r"erotic\w*", r"fetish\w*", r"orgasm\w*", r"genital\w*", r"strip(?:per|pers|tease)", r"brothel", r"masturbat\w*",
    r"semen", r"sperm", r"lesbian\w*", r"homosexual\w*", r"adulter\w*", r"affairs? with", r"mistress\w*",
    r"seduc\w*", r"incest\w*", r"pedophil\w*", r"paedophil\w*", r"obscen\w*", r"vulgar\w*", r"playboy", r"lingerie",
    r"sexually", r"intercourse", r"toilet\w*", r"feces", r"faeces", r"excrement", r"urine", r"urinat\w*",
    # other heavy topics
    r"bankrupt\w*", r"divorc\w*", r"scandal\w*", r"controvers\w*", r"propaganda", r"dictator\w*", r"coup\w*",
    r"protest\w*", r"riot\w*", r"cults?", r"occult\w*", r"satan\w*", r"witch(?:es|craft|-hunt)", r"exorcis\w*",
    r"gambl\w*", r"casinos?", r"alcoholi\w*", r"drunk\w*", r"cigarettes?", r"tobacco", r"smok(?:er|ers|ing)",
    r"vaccin\w*", r"abortion",
])
# AIDS only as the disease (case-sensitive, so "aids" the verb stays)
AIDS = re.compile(r"\bAIDS\b")


def word_count(s):
    return len(re.findall(r"\S+", s))


def has_superlative(s):
    for m in SUPERLATIVE.finditer(s):
        w = m.group(0).lower()
        if w.endswith("est") and (w in NOT_SUPERLATIVE or len(w) <= 4):
            continue
        return True
    return False


def check(statement, link_titles=()):
    """Return the first reason code that rejects this statement, or None if it passes."""
    n = word_count(statement)
    if n > MAX_WORDS:
        return "too_long"
    if n < MIN_WORDS:
        return "too_short"
    if CONTEXT_START.search(statement) or CONTEXT_WORDS.search(statement):
        return "needs_context"
    text_and_titles = " ".join([statement, *link_titles])
    if UNSUITABLE.search(text_and_titles) or AIDS.search(text_and_titles):
        return "unsuitable_topic"
    if ALWAYS_CHANGING.search(statement):
        return "fast_changing"
    # superlatives, "only", "first", prices: fine when clearly historical ("in 1890 it was the largest"),
    # rejected when stated in the present tense or without any date
    if (has_superlative(statement) or CURRENCY.search(statement)) and (PRESENT.search(statement)
                                                                       or not YEAR.search(statement)):
        return "fast_changing"
    return None


def matched_term(statement, link_titles=()):
    """For the report: which unsuitable term matched (None if none)."""
    t = " ".join([statement, *link_titles])
    m = UNSUITABLE.search(t) or AIDS.search(t)
    return m.group(0) if m else None
