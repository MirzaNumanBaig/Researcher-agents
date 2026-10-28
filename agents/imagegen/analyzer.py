"""Step 1: understand the story. One LLM call returns JSON; rule-based fallbacks and safety checks guarantee a complete, valid result."""
import logging
import re

from . import llm as llmmod

log = logging.getLogger("imagegen")

STORY_TYPES = ["relationship", "breakup", "wedding", "pregnancy", "red_carpet", "film_release", "trailer", "box_office", "award", "music_release",
               "concert", "feud", "legal", "scandal", "health", "tribute", "interview", "fashion", "travel", "reality_tv", "other"]
SENSITIVITY = ["safe", "sensitive", "high_risk"]

# story_type -> (emotion, setting, key objects, time and light, palette)
DEFAULTS = {
    "relationship": ("tender", "a quiet restaurant terrace", ["two coffee cups", "a small bouquet", "string lights"], "warm evening light from string lights", ["warm amber", "soft rose"]),
    "breakup": ("melancholic", "a rain-wet city street", ["a small suitcase", "a glowing café window", "an open umbrella"], "blue-hour sky light with warm window glow", ["muted teal", "amber"]),
    "wedding": ("joyful", "a flower-covered wedding venue", ["wedding rings", "a long white veil", "a bouquet of white roses"], "golden-hour sun from low behind the guests", ["ivory", "soft gold"]),
    "pregnancy": ("tender", "a sunlit nursery", ["knitted booties", "a soft cream blanket", "a wooden crib"], "soft window light from the left", ["cream", "pale sage"]),
    "red_carpet": ("glamorous", "a red carpet at night", ["camera flashes", "velvet ropes", "a long satin gown"], "camera flashes at night", ["deep red", "gold"]),
    "film_release": ("anticipatory", "an empty cinema auditorium", ["a film clapperboard", "red velvet seats", "a projector beam"], "a bright projector beam through haze", ["deep blue", "warm gold"]),
    "trailer": ("tense", "a dark screening room", ["a glowing screen", "a film reel", "popcorn on a seat"], "cold light from a large screen", ["steel blue", "orange"]),
    "box_office": ("triumphant", "a cinema foyer at night", ["a stack of tickets", "a glowing marquee", "popcorn"], "warm neon from the foyer lights", ["red", "gold"]),
    "award": ("triumphant", "an awards stage", ["a golden trophy", "stage spotlights", "a podium"], "overhead stage spotlights", ["gold", "deep black"]),
    "music_release": ("energetic", "a recording studio", ["a condenser microphone", "headphones", "a mixing desk"], "warm lamp light and glowing studio meters", ["violet", "amber"]),
    "concert": ("electric", "a concert stage", ["a microphone stand", "stage spotlights", "a sea of raised hands"], "overhead stage spotlights through haze", ["magenta", "electric blue"]),
    "feud": ("tense", "an empty press room", ["two empty chairs", "a long table", "scattered papers"], "hard overhead light", ["slate grey", "red"]),
    "legal": ("sombre", "courthouse steps", ["a wooden gavel", "stone columns", "a leather briefcase"], "soft overcast daylight", ["stone grey", "warm brown"]),
    "scandal": ("uneasy", "a dim corridor", ["a half-open door", "a flickering lamp", "a coat on a hook"], "a single warm lamp in a dark room", ["charcoal", "amber"]),
    "health": ("quiet", "a calm hospital corridor", ["an empty chair", "a window with soft light", "a potted plant"], "soft window light", ["pale blue", "white"]),
    "tribute": ("reflective", "a quiet room by a window", ["lit white candles", "an empty chair", "fresh flowers"], "candlelight and soft window light", ["warm cream", "dusk blue"]),
    "interview": ("candid", "a cosy studio set", ["two armchairs", "a small table with water glasses", "studio lights"], "soft key light from a large window", ["warm teal", "cream"]),
    "fashion": ("glamorous", "a fashion runway", ["a rack of dresses", "a long runway", "rows of empty chairs"], "bright runway spotlights", ["black", "silver"]),
    "travel": ("carefree", "an airport arrivals hall", ["luggage trolley", "a passport", "a departures board"], "golden-hour sun through tall windows", ["sky blue", "sand"]),
    "reality_tv": ("dramatic", "a TV studio set", ["studio cameras", "a glowing 'on air' light", "a leather sofa"], "bright studio lighting", ["hot pink", "teal"]),
    "other": ("curious", "a city street at dusk", ["a folded coat", "a street lamp", "a quiet bench"], "blue-hour light with street lamps", ["teal", "amber"]),
}

TYPE_WORDS = [  # keyword rules used when no LLM is available (first match wins)
    ("wedding", r"\b(wedding|married|marries|marry|marrying|weds|ties the knot|tie the knot|engaged|engagement|bride|groom|honeymoon)\b"),
    ("breakup", r"\b(split|splits|break ?up|broke up|separat\w+|divorce\w*)\b"),
    ("pregnancy", r"\b(pregnan\w+|baby bump|expecting a|gives birth|newborn)\b"),
    ("relationship", r"\b(dating|couple|romance|girlfriend|boyfriend|spotted together|relationship)\b"),
    ("tribute", r"\b(tribute|died|dies|death|funeral|passed away|memorial|farewell)\b"),
    ("health", r"\b(cancer|diagnos\w+|illness|hospital|surgery|rehab|health scare)\b"),
    ("legal", r"\b(court|lawsuit|sued|trial|judge|arrest\w*|charged|verdict|legal)\b"),
    ("scandal", r"\b(scandal|allegation\w*|alleged|controvers\w+|backlash)\b"),
    ("feud", r"\b(feud|clash|slams|fires back|war of words)\b"),
    ("box_office", r"\b(box office|opening weekend|grossed|takings)\b"),
    ("trailer", r"\b(trailer|teaser|first look)\b"),
    ("red_carpet", r"\b(red carpet|gala|premiere night|arrives at)\b"),
    ("film_release", r"\b(film|movie|premiere|sequel|release date|cinema release|cinemas?|starring|streaming|series|thriller|cast)\b"),
    ("award", r"\b(award|oscar|emmy|bafta|grammy|golden globe|nominat\w+|wins best)\b"),
    ("music_release", r"\b(album|single|new song|ep|track|music video)\b"),
    ("concert", r"\b(concert|tour|gig|festival|live show|sold out)\b"),
    ("fashion", r"\b(fashion|runway|vogue|designer|collection|cover shoot)\b"),
    ("travel", r"\b(holiday|vacation|airport|travel\w*|getaway)\b"),
    ("reality_tv", r"\b(reality|bachelor|big brother|masterchef|survivor|dancing with the stars|strictly)\b"),
    ("interview", r"\b(interview|reveals|opens up|says|speaks)\b"),
]

HIGH_RISK = r"\b(died|dies|dead|death|funeral|passed away|suicide|overdose|abuse\w*|assault\w*|rape\w*|murder\w*|killed|underage|minors?|child(?:ren)?|toddler|teen(?:ager)?s?)\b"
SENSITIVE = r"\b(cancer|diagnos\w+|illness|ill|hospital\w*|surgery|rehab|lawsuit|sued|court|trial|arrest\w*|charged|allegation\w*|alleged\w*|rumou?rs?|reportedly|unconfirmed|divorce\w*|health)\b"


def rule_sensitivity(text):
    t = (text or "").lower()
    if re.search(HIGH_RISK, t):
        return "high_risk"
    return "sensitive" if re.search(SENSITIVE, t) else "safe"


def worst(a, b):
    return SENSITIVITY[max(SENSITIVITY.index(a) if a in SENSITIVITY else 0, SENSITIVITY.index(b) if b in SENSITIVITY else 0)]


def heuristic(headline, body="", category=""):
    text = f"{headline} {category} {(body or '')[:600]}".lower()
    head = f"{headline} {category}".lower()
    # the headline decides the story type; the start of the body is only used when the headline matches no rule
    kind = next((k for k, rx in TYPE_WORDS if re.search(rx, head)), None) or next((k for k, rx in TYPE_WORDS if re.search(rx, text)), "other")
    emo, setting, objs, light, pal = DEFAULTS[kind]
    return {"story_type": kind, "core_event": headline.strip().rstrip(".") + ".", "emotion": emo, "setting": setting, "key_objects": list(objs),
            "time_and_light": light, "palette": list(pal), "sensitivity": rule_sensitivity(text), "source": "rules"}


def _str(v, default=""):
    return " ".join(str(v).split()) if isinstance(v, (str, int, float)) and str(v).strip() else default


def normalize(raw, headline, body="", category=""):
    """Validate an LLM answer field by field; anything missing or invalid comes from the rule-based analysis. Sensitivity can only go up."""
    base = heuristic(headline, body, category)
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    kind = _str(raw.get("story_type")).lower().replace(" ", "_")
    out["story_type"] = kind if kind in STORY_TYPES else base["story_type"]
    if out["story_type"] != base["story_type"]:  # take the matching defaults for fields the model left out
        emo, setting, objs, light, pal = DEFAULTS[out["story_type"]]
        out.update(emotion=emo, setting=setting, key_objects=list(objs), time_and_light=light, palette=list(pal))
    out["core_event"] = _str(raw.get("core_event"), base["core_event"])
    out["emotion"] = _str(raw.get("emotion"), out["emotion"])[:40]
    out["setting"] = _str(raw.get("setting"), out["setting"])
    objs = raw.get("key_objects")
    if isinstance(objs, str):
        objs = [o for o in re.split(r"[;,]", objs)]
    objs = [_str(o) for o in (objs or []) if _str(o)][:5]
    out["key_objects"] = objs if len(objs) >= 3 else (objs + out["key_objects"])[:5]
    out["time_and_light"] = _str(raw.get("time_and_light"), out["time_and_light"])
    pal = raw.get("palette")
    if isinstance(pal, str):
        pal = [p for p in re.split(r"[;,]", pal)]
    pal = [_str(p) for p in (pal or []) if _str(p)][:3]
    out["palette"] = pal if len(pal) >= 2 else out["palette"]
    llm_sens = _str(raw.get("sensitivity")).lower().replace(" ", "_")
    out["sensitivity"] = worst(llm_sens if llm_sens in SENSITIVITY else "safe", base["sensitivity"])
    out["source"] = "llm"
    return out


SYSTEM = ("You are a picture editor at an entertainment news site. Read the news item and return ONLY one JSON object, no commentary. "
          "Never name or describe any real person's face or likeness.")


def build_user(headline, body, category, source_url, reference):
    return (
        f"Headline: {headline}\nCategory: {category or 'n/a'}\nSource URL: {source_url or 'n/a'}\n"
        f"\nArticle:\n{(body or '')[:3500]}\n\n"
        "Return JSON with exactly these keys:\n"
        f'"story_type": one of {STORY_TYPES}\n'
        '"core_event": one plain sentence\n"emotion": 1-2 words\n'
        '"setting": the most likely real-world place or scene type (courthouse steps, airport arrivals, red carpet, recording studio, wedding venue, hospital corridor, film set, stage)\n'
        '"key_objects": 3-5 concrete visual props tied to the story, as a list of short phrases\n'
        '"time_and_light": time of day and a named light source\n"palette": 2-3 colours that suit the mood, as a list\n'
        '"sensitivity": one of ["safe","sensitive","high_risk"]; use sensitive or high_risk for death, health, legal, abuse, minors or unverified rumours'
    )


def analyze(headline, body="", category="", source_url="", reference="", llm=None):
    """Story analysis dict. Uses the LLM when there is one, otherwise (or when its answer is unusable) the keyword rules."""
    if llm is None:
        return heuristic(headline, body, category)
    for _ in range(2):
        try:
            return normalize(llmmod.parse_json(llm.complete(SYSTEM, build_user(headline, body, category, source_url, reference), max_tokens=500, temperature=0.2)),
                             headline, body, category)
        except (ValueError, llmmod.LLMError) as e:
            log.warning("story analysis: LLM answer unusable (%s)", str(e)[:300])
    log.warning("story analysis: using the keyword rules")
    return heuristic(headline, body, category)
