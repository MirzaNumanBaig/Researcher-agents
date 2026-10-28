"""Step 3: write ONE natural-language FLUX.1 schnell prompt (90-150 words with people, 60+ without) from the scene blueprint and the stand-in cast.
Order for people: shot size and subject, face and expression, body language, clothing and props, setting and depth, camera, light, mood and palette, realism tail, "no text, no logos, no watermark."
An LLM writes it when available; every result is cleaned and checked by concept.py, and a deterministic template is the fallback."""
import json
import logging
import re
from collections import Counter

from . import concept, presets
from . import llm as llmmod

log = logging.getLogger("imagegen")

SHOTS = ["wide establishing shot", "medium-wide shot", "medium shot", "close-up detail shot", "over-the-shoulder shot", "overhead shot"]
ANGLES = ["eye-level", "slightly low angle", "high angle", "tilted angle", "from behind", "side-on view"]
LENSES = ["24mm", "35mm", "50mm", "85mm"]
TARGET_WORDS = 185  # the tiers below drop optional detail above this; the hard limit is concept.HARD_MAX_WORDS
PEOPLE_SHOTS = ["medium shot", "medium-wide shot", "wide shot"]  # no extreme close-ups: schnell bends faces up close
PEOPLE_ANGLES = ["eye-level", "slightly low angle", "slightly high angle", "three-quarter view", "side-on view"]
PEOPLE_LENSES = ["35mm", "50mm", "85mm"]

SCENES = {  # story_type -> subject and action sentence; {o1}{o2}{o3} are key objects, {setting} the place
    "relationship": "Two anonymous figures seen from behind sharing a small table in {setting}, their hands almost touching beside {o1}, {o2} nearby.",
    "breakup": "A woman in a long camel coat seen from behind, walking away through {setting} with {o1}, {o2} blurred behind her.",
    "wedding": "A bride in a long white gown seen from behind, holding {o3}, walking slowly through {setting}, {o1} catching the light.",
    "pregnancy": "An adult's hands resting gently on {o2} in {setting}, {o1} placed beside them.",
    "red_carpet": "A woman in a long black gown seen from behind on {setting}, a wall of {o1} flaring ahead of her, {o2} lining the path.",
    "film_release": "A single red velvet seat in the front row of {setting}, {o1} resting on the armrest, {o3} cutting through the haze.",
    "trailer": "{o1} lighting up the dark of {setting}, one lone silhouette in the third row, {o2} on the seat beside it.",
    "box_office": "A hand holding {o1} in front of {setting}, {o2} glowing out of focus behind.",
    "award": "{o1} gleaming on a podium in {setting}, an anonymous figure in a dark suit out of focus at the edge of the frame.",
    "music_release": "{o1} standing alone in {setting}, a pair of hands adjusting {o2} on {o3}.",
    "concert": "{o1} at the centre of {setting}, a crowd of anonymous silhouettes with raised hands filling the lower frame.",
    "feud": "{o1} facing away from each other in {setting}, {o2} between them, {o3} on the floor.",
    "legal": "{o1} resting on a desk in front of {setting}, {o2} blurred behind, a far-off anonymous figure in a dark coat.",
    "scandal": "{o1} in {setting}, light spilling across {o3}, a lone coat hanging in the foreground.",
    "interview": "{o1} angled toward each other in {setting}, {o2} between them, soft light on {o3}.",
    "fashion": "A model in a sculptural gown seen from behind on {setting}, {o1} and {o2} lining the walkway.",
    "travel": "A woman in a light trench coat seen from behind pulling {o1} through {setting}, {o2} glowing in the distance.",
    "reality_tv": "{o1} pointed at a lone sofa in {setting}, {o2} glowing out of focus, an empty chair in the foreground.",
    "other": "{o1} and {o2} in {setting}, a lone figure seen from behind in the distance.",
}
ATMOSPHERE = {"joyful": "warm haze and soft bokeh", "glamorous": "flaring lights and drifting haze", "melancholic": "rain mist and blurred city lights",
              "tense": "hard shadows and a thin haze", "tender": "soft bokeh and a gentle glow", "sombre": "still air and soft grey haze"}

SYSTEM = (
    "You write image prompts for FLUX.1 schnell. Output ONE prompt of 90-150 words (never over 190) as flowing descriptive sentences, nothing else.\n"
    "When the brief lists stand-in people, use exactly those descriptions and body-language cards, in this order: "
    "1 shot size and subject (\"A medium shot of a woman in her early 30s...\"); 2 face and expression in detail (eyebrows, eyes, mouth, jaw, gaze direction); "
    "3 body language (head tilt, shoulders, posture, hand position, distance or touch between people); 4 clothing and props; "
    "5 setting and depth (foreground, midground, background blur); 6 camera (lens, angle, shallow depth of field); 7 lighting (name the real source and direction); "
    "8 mood and colour palette; 9 the realism tail given in the brief; 10 end with the sentence: No text, no logos, no watermark.\n"
    "When there are no people, describe the scene and objects in the same order and skip steps 2, 3 and the realism tail.\n"
    "Rules: never use a real person's name or say someone looks like anyone; the people are original stand-ins, never real people; at most 2 faces; medium or medium-wide shots, "
    "no extreme close-ups; keep hands simple (holding an object, resting on a surface, in a pocket), never fingers spread or interlaced in the foreground; "
    "describe emotion through specific muscle cues, not just sad or happy; no children; no readable text, signs, posters, logos or brands; "
    "do not copy any existing photo, film, album cover or poster; no negative prompts and no weighting syntax; no hype words like masterpiece, ultra-detailed or 8k."
)


def pick_variation(history, key="", people=False):
    """Least-used shot, angle and lens in the recent history (ties broken by a stable hash of the article key) so neighbouring images differ."""
    recent = history[-20:]
    shots, angles, lenses = (PEOPLE_SHOTS, PEOPLE_ANGLES, PEOPLE_LENSES) if people else (SHOTS, ANGLES, LENSES)

    def choose(options, field):
        used = Counter(h.get(field) for h in recent)
        low = min(used.get(o, 0) for o in options)
        pool = [o for o in options if used.get(o, 0) == low]
        return pool[sum(map(ord, key + field)) % len(pool)]

    return {"shot": choose(shots, "shot"), "angle": choose(angles, "angle"), "lens": choose(lenses, "lens")}


def pick_palette(analysis, history):
    """The analysis palette, unless the same colours were used in the last 5 images; then the next-best suited pair from the defaults."""
    pal = _join(analysis.get("palette", [])[:3])
    if pal and pal.lower() not in [h.get("palette", "").lower() for h in history[-5:]]:
        return pal
    alts = ["deep teal and warm amber", "dusty rose and slate blue", "emerald green and brass gold", "burnt orange and midnight blue", "ivory and soft charcoal"]
    used = [h.get("palette", "").lower() for h in history[-5:]]
    return next((a for a in alts if a not in used), alts[0])


def _used(prop, text):
    """True when the prop's key noun already appears in the text ("an empty chair" vs "an empty wooden chair", "seats" vs "seat")."""
    key = prop.lower().split()[-1]
    key = key[:-1] if key.endswith("s") and len(key) > 3 else key
    return key in text.lower()


def _join(items):
    items = [i for i in items if i]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1] if items else ""


def _pron(stand_in):
    return ("Her", "her") if stand_in["presentation"] == "woman" else ("His", "his")


def _lower(s):
    return s[0].lower() + s[1:] if s else s


def compose_people(analysis, preset, variation, palette, blueprint, standins):
    """Deterministic people prompt in the spec's order. One face sentence and one body sentence per stand-in, using the blueprint's cards as written.
    Kept near 150 words (two people about 165) so the camera, light and realism sentences are never the part that gets cut."""
    people, n = blueprint["people"], len(blueprint["people"])
    shot = variation["shot"]
    interaction = next((p["interaction"] for p in people if p.get("interaction")), "")
    s1 = f"A {shot} of {' and '.join(st['descriptor'] for st in standins)}" + (f", {interaction}" if interaction else "") + "."
    same = n == 2 and standins[0]["presentation"] == standins[1]["presentation"]
    people_text = []
    for st, p in zip(standins, people):
        fe, label = p["facial_expression"], st["label"]
        owner = f"{label}'s" if same else ("Her" if st["presentation"] == "woman" else "His")
        face = f"{label}'s brows {fe['eyebrows']}, eyes {fe['eyes']}, {fe['mouth']}, jaw {fe['jaw']}, gaze {p['gaze']}"
        body = f"head {_lower(p['head'])}, {_lower(p['posture'])}, {_lower(p['hands'])}"
        # one person: two sentences (face, then body). Two people: one sentence each (face, then body) so the whole prompt stays readable by schnell.
        people_text += [face + ".", f"{owner} pose: {body}."] if n == 1 else [f"{face}; {body}."]
    wears = "; ".join(f"{st['label'].lower()} wears {st['style']}" for st in standins)
    depth = blueprint["composition"]["depth_layers"]
    fg = _lower(depth["foreground"])
    prop = next((x for x in blueprint.get("props", []) if x.lower().split()[-1][:5] not in (fg + " " + wears).lower()), "")
    camera = f"{variation['lens']} lens, {variation['angle']}, shallow depth of field."
    light = f"Lit by {blueprint['light']['source']}" + (f", {blueprint['light']['direction']}" if blueprint["light"].get("direction") else "") + "."
    mood = f"{blueprint['mood'].capitalize()} mood, {palette} palette."
    tail = preset.get("tail") or preset["style"]
    short_tail = preset.get("tail_short") or tail

    def build(with_prop, with_fg, tail_text=tail):  # least important detail goes first when the prompt is too long, so camera, light and the realism tail always survive
        setting = f"{_cap(wears)}. The setting is {blueprint['setting']}" + (f", {prop} nearby" if prop and with_prop else "") + \
                  (f", {fg} soft in the foreground" if with_fg else "") + f", {_lower(depth['background'])} behind."
        return " ".join([s1, *people_text, setting, camera, light, mood, tail_text])

    text = build(True, True)
    for args in ((False, True), (False, False), (False, False, short_tail)):
        if concept.words(text) <= TARGET_WORDS:
            break
        text = build(*args)
    return concept.sanitize_prompt(text, [])


def _cap(s):
    return s[:1].upper() + s[1:]


def compose(analysis, preset, variation, palette, names):
    """Deterministic prompt used when no LLM is available or its answer fails the checks."""
    sym = concept.is_sensitive(analysis)
    if sym:  # calm, people-free props, lighting and mood, whatever the story type (a sensitive wedding must not get "guests" or "raised hands")
        from .analyzer import DEFAULTS
        emo, _, objs, light, calm = DEFAULTS[analysis["story_type"] if analysis["story_type"] in concept.SYMBOLIC else "tribute"]
        o = list(objs) + ["a quiet bench"]
        subject, emotion, light = concept.symbolic_scene(analysis), "quiet", light
        palette = _join(calm[:2]) if palette == _join(analysis.get("palette", [])[:3]) else palette
    else:
        o = list(analysis.get("key_objects", [])) + ["a quiet bench", "a street lamp", "a folded coat"]
        subject = SCENES.get(analysis["story_type"], SCENES["other"]).format(setting=analysis["setting"], o1=o[0], o2=o[1], o3=o[2])
        emotion, light = analysis["emotion"], analysis["time_and_light"]
    subject = subject[0].upper() + subject[1:] + ("" if subject.endswith(".") else ".")
    atmosphere = ATMOSPHERE.get(emotion.split()[0].lower(), "soft haze and gentle bokeh")
    fg = next((x for x in o if not _used(x, f"{subject} {light}")), o[-1])  # a prop neither the scene sentence nor the light source already uses
    text = (f"{subject} Softly out of focus in the foreground: {fg}. The background fades into {atmosphere}. "
            f"{variation['shot'].capitalize()}, {variation['lens']} lens, {variation['angle']}, shallow depth of field. "
            f"Lit by {light}. {emotion.capitalize()} mood, {palette} palette. {preset['style']}")
    return concept.sanitize_prompt(text, names)


def _llm_user(analysis, preset, variation, palette, history, names, blueprint=None, standins=()):
    safe, _ = concept.strip_names(analysis.get("core_event", ""), names)
    brief = {k: analysis[k] for k in ("story_type", "emotion", "setting", "key_objects", "time_and_light", "sensitivity")}
    brief["core_event"] = safe
    brief["palette"] = palette
    lines = [f"Story analysis (names removed): {json.dumps(brief)}",
             f"Use this camera: {variation['shot']}, {variation['angle']}, {variation['lens']} lens."]
    if standins and blueprint and blueprint.get("people"):
        cards = []
        for st, p in zip(standins, blueprint["people"]):
            cards.append({"who": f"{st['label']}: {st['descriptor']}", "wears": st["style"], "facial_expression": p["facial_expression"], "gaze": p["gaze"], "head": p["head"],
                          "posture": p["posture"], "hands": p["hands"], "interaction": p.get("interaction", "")})
        lines.append("Stand-in people (original fictional characters; describe them exactly like this): " + json.dumps(cards))
        lines.append(f"Scene blueprint: setting {blueprint['setting']}; props {blueprint['props']}; light {blueprint['light']}; mood {blueprint['mood']}; "
                     f"composition {blueprint['composition']['layout']}; depth {blueprint['composition']['depth_layers']}")
        lines.append("Realism tail to use before the final sentence: " + (preset.get("tail") or preset["style"]))
    else:
        lines.append(f"Style sentence to close with before the final sentence: {preset['style']}")
    if concept.is_sensitive(analysis):
        lines.append(f"This story is {analysis['sensitivity']}: show only a calm, respectful, symbolic scene with NO people, for example {concept.symbolic_scene(analysis)}.")
    avoid = [" ".join(h.get("prompt", "").split()[:10]) for h in history[-5:] if h.get("prompt")]
    if avoid:
        lines.append("Do not repeat the composition of these recent images: " + " | ".join(avoid))
    return "\n".join(lines)


def write_prompt(analysis, preset_name, history, names, llm=None, key="", blueprint=None, standins=()):
    """Returns {prompt, shot, angle, lens, palette, source, notes}. Never returns a prompt that fails concept.check_prompt.
    blueprint + standins (from blueprint.py / cast.py) make it a people prompt; without them it is an object scene."""
    preset = presets.get(preset_name)
    with_people = bool(standins and blueprint and blueprint.get("people")) and not concept.is_sensitive(analysis)
    variation = pick_variation(history, key, with_people)
    palette = pick_palette(analysis, history)
    notes = []
    sens = analysis.get("sensitivity", "safe") if concept.is_sensitive(analysis) else "safe"
    if llm is not None:
        user = _llm_user(analysis, preset, variation, palette, history, names, blueprint if with_people else None, standins if with_people else ())
        for attempt in range(2):
            try:
                raw = llm.complete(SYSTEM, user, max_tokens=500, temperature=0.8)
            except llmmod.LLMError as e:
                notes.append(f"llm error: {e}")
                log.warning("prompt writer: LLM error (%s); using the template", str(e)[:300])
                break
            cleaned = concept.sanitize_prompt(raw, names)
            problems = concept.check_prompt(cleaned, names, sens, people=with_people)
            if not problems:
                return {"prompt": cleaned, **variation, "palette": palette, "source": "llm", "notes": notes}
            notes.append(f"attempt {attempt + 1} rejected: {'; '.join(problems)}")
            log.info("prompt writer: LLM prompt rejected (%s)", "; ".join(problems))
            user += f"\nYour last prompt was rejected: {'; '.join(problems)}. Write it again and fix this."
    if with_people:
        prompt = compose_people(analysis, preset, variation, palette, blueprint, standins)
    else:
        prompt = compose(analysis, preset, variation, palette, names)
    return {"prompt": prompt, **variation, "palette": palette, "source": "template", "notes": notes}
