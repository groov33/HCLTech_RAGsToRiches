"""Text cleaning: remove pressure/hype sentences and find dates.

Why remove hype: words like "URGENT" or "I'm the CEO" say nothing about WHAT is
broken, but a model would happily learn "URGENT" -> outage. Priority must come
from facts, so the classifiers only ever see the factual sentences.
"""
import re
from datetime import date

# A sentence is treated as hype if it contains any of these phrases.
HYPE_PATTERN = re.compile(
    r"\b("
    r"urgent\w*|asap|a\.s\.a\.p|immediately|right now|right away|at once|"
    r"high priority|top priority|highest priority|priority one|p1 please|"
    r"emergency|crisis|disaster|unacceptable|ridiculous|embarrassing|"
    r"out of patience|stop making me wait|losing patience|"
    r"heat from above|executive|escalat\w*|ceo|cfo|cto|director|vice president|vip|my boss|senior management|"
    r"pick this up|take this now|fix (this|it) now|need this fixed|get someone on this|"
    r"whole company depends|everything depends|deadline is killing"
    r")\b",
    re.IGNORECASE,
)

# Words that suggest a possible security incident (safety net, see classify.py).
SECURITY_CUES = re.compile(
    r"\b(phish\w*|fishy|suspicious|scam|spoof\w*|virus|malware|ransom\w*|trojan|hack\w*|"
    r"stolen|lost (my |the )?(laptop|phone|device|mobile)|data (leak|exposure)|"
    r"(sign-?in|login) link|strange (link|attachment)|unknown sender|different domain)\b",
    re.IGNORECASE,
)


def has_security_cue(text: str) -> bool:
    return bool(SECURITY_CUES.search(text))


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}
_DATE_DMY = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(MONTHS) + r"),?\s+(\d{4})\b", re.I)
_DATE_MDY = re.compile(r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", re.I)
_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text.strip()) if s.strip()]


def is_hype(sentence: str) -> bool:
    return bool(HYPE_PATTERN.search(sentence))


def has_hype(text: str) -> bool:
    return any(is_hype(s) for s in split_sentences(text))


MIN_FACT_WORDS = 7   # a hype sentence with fewer words left than this is pure pressure


def clean_description(text: str) -> str:
    """Remove hype phrases, keep the facts, drop '!', lowercase.

    "PLEASE TAKE ASAP The site is down" -> "please take the site is down" (facts kept)
    "I'm the CEO, fix this now."        -> dropped (nothing factual left)
    """
    kept = []
    for s in split_sentences(text):
        if is_hype(s):
            stripped = HYPE_PATTERN.sub(" ", s)
            if len(re.findall(r"[A-Za-z0-9']+", stripped)) < MIN_FACT_WORDS:
                continue
            s = stripped
        kept.append(s)
    if not kept:                       # everything was hype: keep the original words
        kept = [text]
    cleaned = " ".join(kept).replace("!", ".")
    return re.sub(r"\s+", " ", cleaned).strip().lower()


def find_date(text: str) -> date | None:
    """Return the first calendar date written in the text, if any."""
    for pattern, order in ((_DATE_DMY, "dmy"), (_DATE_MDY, "mdy"), (_DATE_ISO, "iso")):
        m = pattern.search(text)
        if not m:
            continue
        try:
            if order == "dmy":
                return date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
            if order == "mdy":
                return date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)))
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
    return None


# Words that say nothing about WHAT is broken. "system not working" is all generic.
_GENERIC = set("""a an the it its this that is are was be been not no isn't doesn't don't can't cannot won't
working work works broken down issue issues problem problems error help please something anything
everything system thing stuff again still any some i my me we our us you your have has had and or
but so to of for on in at with just now today fix fixed""".split())


def is_too_vague(text: str) -> bool:
    """True when fewer than 2 words say what is actually affected or happening.

    "System not working."          -> vague (0 specific words)
    "My scan takes a few tries."   -> fine  (scan, takes, few, tries)
    """
    words = re.findall(r"[a-z0-9']+", text.lower())
    return sum(w not in _GENERIC for w in words) < 2
