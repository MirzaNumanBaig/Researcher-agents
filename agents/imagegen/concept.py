"""Step 2: the non-negotiable visual rules, enforced in code (not just asked of the model).
 - no real person's name or likeness in a prompt or alt text; people in an image are always fictional stand-ins (cast.py)
 - no readable text, signs, logos; no children; weighting syntax and negative prompts removed
 - sensitive / high-risk stories get a calm symbolic scene with no people
"""
import re

from . import config

FINAL_SENTENCE = "No text, no logos, no watermark."
MAX_WORDS, HARD_MAX_WORDS, MIN_WORDS, MIN_WORDS_NO_PEOPLE = 196, 200, 90, 60  # the writer aims for 90-150; two people with full face and body cards need up to ~190; schnell reads about 256 tokens

PLACE_CUES = {"in", "near", "at", "outside", "across", "from", "to", "around", "off", "over", "into", "through"}  # "near Byron Bay": a place, not a person
COMMON_CAPS = {"veteran", "australian", "american", "british", "canadian", "irish", "french", "german", "italian", "indian", "korean", "japanese", "chinese",
               "former", "young", "old", "new", "great", "big", "little", "royal", "national", "international", "hollywood", "bollywood", "oscar", "emmy", "grammy",
               "breaking", "exclusive", "first", "final", "latest", "official", "world", "global", "live", "top", "best", "star", "actor", "actress", "singer"}
NOT_NAMES = {  # capitalised word pairs that are places, titles or brands, never people
    "academy awards", "apple tv", "barrier reef", "blue mountains", "bondi beach", "box office", "byron bay", "celebrity news",
    "circular quay", "disney plus", "gold coast", "golden globe", "golden globes", "great barrier", "harbour bridge", "hbo max",
    "los angeles", "melbourne", "netflix", "new york", "new zealand", "northern beaches", "northern territory", "opera house",
    "port douglas", "prime video", "quick summary", "red carpet", "south australia", "sunshine coast", "sydney harbour", "sydney opera",
    "western australia", "world tour"}
SHARED_WORDS = {"short", "fox", "oh", "williams", "anderson", "john", "james", "david", "michael", "will", "mark", "jack", "love", "grace", "hope"}

LIKENESS = re.compile(r"\b(looks? like|looking like|resembl\w+|look-?alike|likeness|as played by|portrait of|photo of|picture of)\b[^.,;]*", re.I)
STYLE_OF = re.compile(r"\bin the style of\b[^.,;]*", re.I)
NEGATIVE = re.compile(r"(negative prompt|avoid:|--no\b|--ar\b)[^\n]*", re.I)
WEIGHT = re.compile(r"\(([^()]{1,80}?):[0-9.]+\)|\[([^\[\]]{1,80})\]")
TEXT_NOUNS = re.compile(r"\b(?:an?\s+|the\s+)?(?:neon\s+|street\s+|shop\s+|store\s+|cinema\s+|movie\s+|film\s+)?"
                        r"(?:signage|sign|signs|billboard|banner|poster|album cover|marquee|headline|caption|logo|logos|brand)s?\b", re.I)
READING = re.compile(r"\b(reading|that says|saying|written|spelling|lettering|typography|inscribed)\b[^.;]*", re.I)
CHILD = re.compile(r"\b(child|children|kid|kids|baby|babies|toddler|infant|teen|teenager|teenagers|boy|girl|schoolboy|schoolgirl|minor|minors)\b", re.I)
PEOPLE = re.compile(r"\b(man|woman|men|women|person|people|couple|figure|figures|silhouette|silhouettes|crowd|bride|groom|actor|actress|singer|dancer|audience|guests?|hands?|faces?|model)\b", re.I)

SYMBOLIC = {  # calm scenes without people, by story type
    "tribute": "a single empty wooden chair beside a tall window, a row of lit white candles on a small table",
    "health": "a quiet empty corridor with a bench under a tall window, soft daylight on the floor",
    "legal": "a wooden gavel resting on a bare desk beside a closed leather folder, soft light across the grain",
    "scandal": "a half-open door at the end of a dim hallway, warm light spilling across the floorboards",
    "feud": "two empty armchairs facing away from each other in a quiet room, a closed door behind them",
}
SYMBOLIC_DEFAULT = "an empty armchair beside a rain-streaked window, soft grey light across the floor"


def known_names(headline="", extra=()):
    """Every name that must never reach a prompt: tracked celebrities from config.json, the given extras, and capitalised word pairs in the headline."""
    names = set(n for n in extra if n)
    try:
        import json
        names |= set(json.loads((config.ROOT / "config.json").read_text()).get("celebrities", []))
    except (OSError, ValueError):
        pass
    text = headline or ""
    for m in re.finditer(r"\b[A-Z][\w'’-]+(?:\s+[A-Z][\w'’-]+)+\b", text):
        words_ = [w.lower() for w in m.group(0).split()]
        before = re.findall(r"[\w'’-]+", text[:m.start()])[-1:]  # the word in front of the pair
        if m.group(0).lower() in NOT_NAMES or words_[0] in COMMON_CAPS or words_[-1] in COMMON_CAPS or (before and before[0].lower() in PLACE_CUES):
            continue
        names.add(m.group(0))
    return sorted(names, key=len, reverse=True)


def _parts(name):
    return [p for p in re.split(r"\s+", name) if len(p) >= 4 and p.lower() not in SHARED_WORDS]


def names_in(text, names):
    found = []
    for n in names:
        if re.search(rf"\b{re.escape(n)}\b", text, re.I) or any(re.search(rf"\b{re.escape(p)}\b", text, re.I) for p in _parts(n)):
            found.append(n)
    return found


def strip_names(text, names):
    """Replace full names (and distinctive first/last names) with anonymous wording. Returns (clean text, names that were removed)."""
    removed = []
    for n in names:
        if re.search(rf"\b{re.escape(n)}\b", text, re.I):
            text, removed = re.sub(rf"\b{re.escape(n)}\b", "an anonymous figure", text, flags=re.I), removed + [n]
    for n in names:
        for p in _parts(n):
            if re.search(rf"\b{re.escape(p)}\b", text, re.I):
                text, removed = re.sub(rf"\b{re.escape(p)}\b", "the figure", text, flags=re.I), removed + [n]
    return re.sub(r"\s{2,}", " ", text).strip(), sorted(set(removed))


def words(text):
    return len(re.findall(r"\b[\w'’-]+\b", text))


def limit_words(text, cap=MAX_WORDS):
    """Cut whole sentences until the prompt fits, keeping the opening sentences and the last one (the realism / style tail)."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    while len(parts) > 3 and words(" ".join(parts)) > cap:
        parts.pop(-2)
    return " ".join(parts)


def sanitize_prompt(prompt, names, final=True):
    """Clean a model-written prompt: remove names, likeness phrases, weighting syntax, negative prompts, text/sign requests; end with the no-text sentence."""
    s = (prompt or "").strip().strip('"').strip("'")
    s = NEGATIVE.sub("", s)
    s = WEIGHT.sub(lambda m: m.group(1) or m.group(2), s)
    s = LIKENESS.sub("", STYLE_OF.sub("", s))
    s = READING.sub("", s)
    s = TEXT_NOUNS.sub("", s)
    s, _ = strip_names(s, names)
    s = re.sub(r"\bno text[^.]*\.?", "", s, flags=re.I)  # re-added once, at the end
    s = re.sub(r"\bno (?:logos?|watermarks?)[^.]*\.?", "", s, flags=re.I)
    s = re.sub(r"\s+([,.;])", r"\1", re.sub(r"([,;])\s*([,;.])", r"\2", s))
    s = re.sub(r"\s{2,}", " ", s).strip(" ,;")
    s = limit_words(s, MAX_WORDS - 6)  # room for the closing 5-word sentence
    if final:
        s = s.rstrip(" .") + ". " + FINAL_SENTENCE
    return s


def check_prompt(prompt, names, sensitivity="safe", people=True):
    """Problems that cannot be fixed by cleaning (the caller rewrites the prompt or uses the safe template)."""
    problems = []
    if names_in(prompt, names):
        problems.append("contains a real person's name")
    if CHILD.search(prompt):
        problems.append("mentions a child or minor")
    if sensitivity != "safe" and PEOPLE.search(prompt):
        problems.append("shows people in a sensitive story")
    if LIKENESS.search(prompt) or WEIGHT.search(prompt) or NEGATIVE.search(prompt):
        problems.append("contains likeness phrases, weighting syntax or a negative prompt")
    n, low = words(prompt), (MIN_WORDS if people and sensitivity == "safe" else MIN_WORDS_NO_PEOPLE)
    if n > HARD_MAX_WORDS or n < low:
        problems.append(f"{n} words (needs {low}-{HARD_MAX_WORDS})")
    if not prompt.rstrip().endswith(FINAL_SENTENCE):
        problems.append("does not end with the no-text sentence")
    return problems


def symbolic_scene(analysis):
    return SYMBOLIC.get(analysis.get("story_type"), SYMBOLIC_DEFAULT)


def is_sensitive(analysis):
    return analysis.get("sensitivity", "safe") != "safe" or analysis.get("story_type") in ("tribute", "health", "legal")
