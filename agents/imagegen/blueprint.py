"""Step 1b: the scene blueprint. What a picture shows, in plain visual facts, so it can be recreated with ORIGINAL stand-in people.
 - from_reference(): a vision model reads the news photo's composition and each person's body language (never who they are, never identity traits)
 - default_blueprint(): the same structure built from the story analysis when there is no usable reference photo
Both go through normalize(), which caps the cast at two people, removes names and identity traits, and drops people entirely for sensitive stories."""
import logging
import re

from . import concept
from . import llm as llmmod

log = logging.getLogger("imagegen")

MAX_PEOPLE = 2
SHOT_SIZES = ["wide", "medium-wide", "medium", "medium close-up"]  # no extreme close-ups: schnell bends faces up close
ANGLES = ["eye-level", "slightly low angle", "slightly high angle", "side-on view", "three-quarter view"]

# Words that would describe WHO someone is rather than how they act. Clauses containing them are dropped from the person cards.
IDENTITY = re.compile(r"\b(nose|nostrils?|cheekbones?|face shape|round face|square face|oval face|jawline shape|eye colou?r|(?:blue|green|brown|hazel|grey|gray) eyes|"
                      r"hooked|freckles|dimples?|moles?|birthmarks?|scars?|tattoos?|resembl\w+|looks? like|lookalike|famous|celebrity|star)\b", re.I)

# emotion -> body-language card. Short fragments on purpose: two people have to fit a 150 word prompt.
CARDS = {
    "tender": dict(eyebrows="softened and relaxed", eyes="warm, a little crinkled", mouth="a small closed-lip smile", jaw="loose", gaze="on the other person",
                   head="tilted toward them", posture="shoulders dropped, leaning in", hands="one hand resting on the table edge"),
    "joyful": dict(eyebrows="lifted", eyes="bright and crinkled", mouth="a wide natural smile", jaw="relaxed", gaze="on the other person",
                   head="tipped back mid-laugh", posture="open chest, loose shoulders", hands="one hand in a coat pocket"),
    "melancholic": dict(eyebrows="raised and drawn together at the inner corners", eyes="glassy and cast down", mouth="lips pressed together", jaw="slightly tense",
                        gaze="down, off-frame left", head="bowed, turned slightly away", posture="shoulders rounded, weight on one leg", hands="both hands in coat pockets"),
    "glamorous": dict(eyebrows="smooth and softly arched", eyes="confident and direct", mouth="a composed soft smile", jaw="lifted slightly", gaze="toward the camera",
                      head="quarter-turned toward the lens, chin raised", posture="shoulders back, spine long", hands="one hand resting on the hip"),
    "tense": dict(eyebrows="lowered and drawn together", eyes="narrowed and steady", mouth="lips in a thin line", jaw="clenched", gaze="straight at them",
                  head="level and rigid", posture="shoulders squared", hands="arms folded"),
    "anticipatory": dict(eyebrows="slightly raised", eyes="wide and attentive", mouth="lips just parted", jaw="relaxed", gaze="up and off-frame right",
                         head="tilted slightly up", posture="leaning forward, elbows on knees", hands="holding a paper cup"),
    "reflective": dict(eyebrows="drawn up gently at the centre", eyes="unfocused and distant", mouth="lips just closed", jaw="soft",
                       gaze="off-frame toward a window", head="resting slightly back", posture="shoulders low", hands="wrapped around a mug"),
    "proud": dict(eyebrows="level and calm", eyes="bright and steady", mouth="a restrained smile", jaw="set", gaze="out toward the audience",
                  head="level, chin up", posture="upright, shoulders back", hands="one hand holding a trophy against the chest"),
}
EMOTION_TO_CARD = {"tender": "tender", "joyful": "joyful", "happy": "joyful", "melancholic": "melancholic", "heartbroken": "melancholic", "sad": "melancholic",
                   "glamorous": "glamorous", "tense": "tense", "angry": "tense", "anticipatory": "anticipatory", "excited": "anticipatory", "reflective": "reflective",
                   "quiet": "reflective", "proud": "proud", "triumphant": "proud"}

# story_type -> (number of people, interaction between them or "", clothing hint). Sensitive stories never get people (see default_blueprint).
PLAN = {
    "relationship": (2, "seated close at a small table, knees angled toward each other, mirrored relaxed poses", ""),
    "breakup": (2, "standing two metres apart in opposing poses, one turned away", ""),
    "wedding": (2, "standing close and facing each other, foreheads almost touching", "a formal gown and a dark suit"),
    "pregnancy": (1, "", ""),
    "red_carpet": (2, "standing side by side, shoulders almost touching", "an evening gown and a black tuxedo"),
    "award": (1, "", "a formal dark suit"),
    "concert": (1, "", "a stage outfit"),
    "interview": (2, "seated at an angle to each other across a low table", ""),
    "fashion": (1, "", "a sculptural gown"),
    "travel": (1, "", "a light trench coat"),
    "film_release": (1, "", ""),
    "trailer": (1, "", ""),
    "music_release": (1, "", ""),
    "reality_tv": (2, "sitting a sofa-width apart, bodies angled slightly away", ""),
    "feud": (2, "facing each other at arm's length in squared opposing stances", ""),
}
SECOND_EMOTION = {"red_carpet": "joyful", "relationship": "joyful", "breakup": "reflective", "wedding": "tender", "interview": "anticipatory", "reality_tv": "tense"}
STORY_EMOTION = {"award": "proud", "red_carpet": "glamorous", "fashion": "glamorous", "film_release": "anticipatory", "trailer": "anticipatory",
                 "music_release": "reflective", "wedding": "joyful", "pregnancy": "tender", "concert": "joyful", "travel": "joyful", "feud": "tense", "breakup": "melancholic"}

SYSTEM = ("You are a picture editor writing a scene blueprint from a news photo so a different, original picture can be made with stand-in people. "
          "Describe ONLY visual facts: camera, composition, setting, light, and each person's body language and clothing. "
          "Never identify anyone, never give a name, and never describe facial features that would identify a real person (no face shape, nose, eye colour, freckles). "
          "Expression is described by muscle cues (eyebrows, eyes, mouth, jaw), not by a single word like sad. Answer with ONE JSON object only.")


def user_prompt():
    return ("Return JSON with exactly these keys:\n"
            '"shot_size": one of ["wide","medium-wide","medium","medium close-up","close-up"], "angle": camera angle, "lens_feel": e.g. "35mm", "camera_height": e.g. "eye level",\n'
            '"composition": {"layout": where each subject sits in the frame, "leading_lines": text, "depth_layers": {"foreground": text, "midground": text, "background": text}},\n'
            '"people_count": number,\n'
            '"people": a list (at most 2 main subjects) of {"gender_presentation": "woman"|"man"|"unspecified", "age_range": e.g. "early 30s", '
            '"facial_expression": {"eyebrows": text, "eyes": text, "mouth": text, "jaw": text}, "gaze": where they look, "head": tilt and turn, "posture": shoulders, spine, weight, '
            '"hands": exact position and what they hold, "interaction": distance to the other person, touch, mirrored or opposing poses, '
            '"clothing": type, colour, fabric; generic, no brand logos},\n'
            '"setting": text, "props": list, "time_of_day": text, "light": {"source": named light source, "direction": text}, "palette": 2-3 colours, "mood": 1-2 words')


def _s(v, default=""):
    return " ".join(str(v).split()) if isinstance(v, (str, int, float)) and str(v).strip() else default


def _clean(text, names):
    """Scrub one text field: no names, no identity traits (the clause containing one is dropped), no brands/logos/text requests."""
    text, _ = concept.strip_names(_s(text), names)
    text = ", ".join(p for p in re.split(r",\s*", text) if p and not IDENTITY.search(p))
    return concept.TEXT_NOUNS.sub("", concept.READING.sub("", text)).strip(" ,;")


def _card(raw, base, names):
    """One person's card from a vision answer, field by field; anything missing or removed comes from the emotion card."""
    raw = raw if isinstance(raw, dict) else {}
    fe = raw.get("facial_expression") if isinstance(raw.get("facial_expression"), dict) else {}
    pres = _s(raw.get("gender_presentation")).lower()
    out = {"gender_presentation": pres if pres in ("woman", "man") else "unspecified", "age_range": _clean(raw.get("age_range"), names)[:30] or base.get("age_range", "")}
    out["facial_expression"] = {k: _clean(fe.get(k), names) or base["facial_expression"][k] for k in ("eyebrows", "eyes", "mouth", "jaw")}
    for k in ("gaze", "head", "posture", "hands", "interaction", "clothing"):
        out[k] = _clean(raw.get(k), names) or base.get(k, "")
    return out


def card_for(emotion, interaction="", clothing=""):
    c = CARDS[EMOTION_TO_CARD.get(_s(emotion).lower().split(" ")[0], "reflective")]
    return {"gender_presentation": "unspecified", "age_range": "", "facial_expression": {k: c[k] for k in ("eyebrows", "eyes", "mouth", "jaw")},
            "gaze": c["gaze"], "head": c["head"], "posture": c["posture"], "hands": c["hands"], "interaction": interaction, "clothing": clothing}


def normalize(raw, analysis, names):
    """Validate a blueprint field by field. Falls back to the story-based defaults for anything missing. Sensitive stories lose all people."""
    base = default_blueprint(analysis, names)
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    shot = _s(raw.get("shot_size")).lower()
    out["shot_size"] = "medium close-up" if "close" in shot else (shot if shot in SHOT_SIZES else base["shot_size"])  # close-ups become medium close-ups
    out["angle"] = _clean(raw.get("angle"), names) or base["angle"]
    out["lens_feel"] = _clean(raw.get("lens_feel"), names) or base["lens_feel"]
    out["camera_height"] = _clean(raw.get("camera_height"), names) or base["camera_height"]
    comp = raw.get("composition") if isinstance(raw.get("composition"), dict) else {}
    depth = comp.get("depth_layers") if isinstance(comp.get("depth_layers"), dict) else {}
    out["composition"] = {"layout": _clean(comp.get("layout"), names) or base["composition"]["layout"], "leading_lines": _clean(comp.get("leading_lines"), names),
                          "depth_layers": {k: _clean(depth.get(k), names) or base["composition"]["depth_layers"][k] for k in ("foreground", "midground", "background")}}
    out["setting"] = _clean(raw.get("setting"), names) or base["setting"]
    props = raw.get("props")
    props = [_clean(p, names) for p in (props if isinstance(props, list) else re.split(r"[;,]", props or "")) if _clean(p, names)][:5]
    out["props"] = props or base["props"]
    out["time_of_day"] = _clean(raw.get("time_of_day"), names) or base["time_of_day"]
    light = raw.get("light") if isinstance(raw.get("light"), dict) else {}
    out["light"] = {"source": _clean(light.get("source"), names) or base["light"]["source"], "direction": _clean(light.get("direction"), names) or base["light"]["direction"]}
    pal = raw.get("palette")
    pal = [_clean(p, names) for p in (pal if isinstance(pal, list) else re.split(r"[;,]", pal or "")) if _clean(p, names)][:3]
    out["palette"] = pal if len(pal) >= 2 else base["palette"]
    out["mood"] = _clean(raw.get("mood"), names)[:40] or base["mood"]
    people = [p for p in (raw.get("people") if isinstance(raw.get("people"), list) else []) if isinstance(p, dict)][:MAX_PEOPLE]
    emotion_card = card_for(out["mood"])
    out["people"] = [_card(p, emotion_card, names) for p in people]
    if concept.is_sensitive(analysis):
        out["people"] = []  # calm symbolic scene only
    out["people_count"] = len(out["people"])
    out["source"] = "vision"
    return out


def default_blueprint(analysis, names=()):
    """The blueprint the story alone implies: people only where the story type has them and only when it is not sensitive."""
    kind = analysis.get("story_type", "other")
    n, interaction, clothing = PLAN.get(kind, (0, "", ""))
    emotion = STORY_EMOTION.get(kind) or _s(analysis.get("emotion"), "reflective").split(" ")[0]
    second = SECOND_EMOTION.get(kind, emotion)  # two people rarely feel exactly the same thing
    people = [] if concept.is_sensitive(analysis) else [card_for(emotion if i == 0 else second, interaction if n > 1 else "", clothing) for i in range(n)]
    props = list(analysis.get("key_objects") or [])[:4]
    return {"shot_size": "medium-wide" if len(people) == 2 else "medium", "angle": "eye-level", "lens_feel": "50mm", "camera_height": "eye level",
            "composition": {"layout": "the people left of centre with the setting opening up to the right" if people else "the main object centred with depth behind it",
                            "leading_lines": "", "depth_layers": {"foreground": props[0] if props else "soft out-of-focus shapes", "midground": "the main subject",
                                                                   "background": "soft haze and bokeh"}},
            "people_count": len(people), "people": people, "setting": analysis.get("setting", ""), "props": props,
            "time_of_day": analysis.get("time_and_light", ""), "light": {"source": analysis.get("time_and_light", "soft window light"), "direction": "from the side"},
            "palette": list(analysis.get("palette") or [])[:3], "mood": _s(analysis.get("emotion"), "quiet"), "source": "template"}


def from_reference(image, analysis, names, llm, mime="image/jpeg"):
    """Vision blueprint of the news photo. Returns None when there is no vision model or its answer is unusable (the caller then uses default_blueprint)."""
    if llm is None or not image:
        return None
    for _ in range(2):
        try:
            return normalize(llmmod.parse_json(llm.vision(SYSTEM, user_prompt(), image, mime)), analysis, names)
        except (ValueError, llmmod.LLMError) as e:
            log.warning("scene blueprint: vision answer unusable (%s)", str(e)[:300])
    return None


def summary(bp):
    """One line for the story analysis and logs (no people details)."""
    return f"{bp.get('shot_size')} shot, {bp.get('angle')}, {bp.get('people_count', 0)} person(s), {bp.get('setting')}, {bp.get('mood')}"
