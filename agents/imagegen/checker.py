"""Step 5: quality check. Cheap pixel rules always run; a vision model then scores the picture 1-5 on six points and any score under min_score (default 4) rejects it.
When the vision model is unavailable (licence not accepted, API error, quota) the scored check is skipped, not failed, and the result says so."""
import io

from . import config
from . import llm as llmmod

SYSTEM = "You are a strict picture editor checking an AI-generated news illustration. Answer with ONE JSON object only."
SCORES = {"face_naturalness": "face naturalness", "expression_match": "expression matches the blueprint", "hands_anatomy": "hands and body anatomy",
          "composition_match": "composition matches the blueprint", "realism": "realism", "no_text_or_logos": "no visible text or logos"}
FLAGS = {"recognizable_real_person": "a clearly recognizable real person", "nudity": "nudity", "graphic_injury": "graphic injury"}


def rule_check(image):
    """Reasons to reject from pixel statistics alone (blank, nearly one colour, far too dark or bright, too small)."""
    from PIL import Image, ImageStat
    img = Image.open(io.BytesIO(image)).convert("L")
    problems = []
    if min(img.size) < 400:
        problems.append(f"too small ({img.width}x{img.height})")
    st = ImageStat.Stat(img)
    if st.stddev[0] < 12:
        problems.append("nearly blank or one flat colour")
    if st.mean[0] < 14:
        problems.append("almost black")
    if st.mean[0] > 243:
        problems.append("almost white")
    return problems


def _expect(analysis, blueprint):
    lines = [f"The picture should show this story: {analysis.get('core_event')} (mood: {analysis.get('emotion')}, setting: {analysis.get('setting')})."]
    people = (blueprint or {}).get("people") or []
    if people:
        lines.append("Planned people (original stand-ins): " + "; ".join(
            f"{p.get('facial_expression')}, gaze {p.get('gaze')}, head {p.get('head')}, posture {p.get('posture')}, hands {p.get('hands')}" for p in people))
        lines.append(f"Planned composition: {(blueprint or {}).get('composition', {}).get('layout', '')}.")
    else:
        lines.append("The plan has NO people: score the three people-related points 5 if no person is visible.")
    return " ".join(lines)


def vision_check(image, analysis, llm, blueprint=None):
    """Returns {ran, scores, reasons, verdict}. When the vision model is unavailable it is skipped, not failed."""
    if llm is None or not config.get("vision_check"):
        return {"ran": False, "skipped": "vision check is off or no LLM provider is configured", "scores": {}, "reasons": [], "verdict": {}}
    keys = ", ".join(f'"{k}": 1-5' for k in SCORES)
    user = (f"{_expect(analysis, blueprint)}\nScore the picture 1 (bad) to 5 (excellent) on: face_naturalness (no warped, waxy or melted faces; 5 if no face), "
            "expression_match (the planned expression, gaze and mood are visible), hands_anatomy (fingers, arms, bodies look physically right), "
            "composition_match (shot size, placement and setting follow the plan), realism (looks like a real photograph), "
            "no_text_or_logos (5 = no readable text, logos or watermarks anywhere).\n"
            f'Return JSON: {{{keys}, "recognizable_real_person": bool, "nudity": bool, "graphic_injury": bool, "notes": "one short sentence"}}')
    try:
        verdict = llmmod.parse_json(llm.vision(SYSTEM, user, image))
    except (llmmod.LLMError, ValueError) as e:
        return {"ran": False, "skipped": f"vision model unavailable: {str(e)[:160]}", "scores": {}, "reasons": [], "verdict": {}}
    scores, reasons, floor = {}, [], config.score_min()
    for key, label in SCORES.items():
        try:
            scores[key] = max(1, min(5, int(round(float(verdict.get(key))))))
        except (TypeError, ValueError):
            scores[key] = None
        if scores[key] is not None and scores[key] < floor:
            reasons.append(f"{label} scored {scores[key]}/5")
    reasons += [text for key, text in FLAGS.items() if verdict.get(key) is True]
    return {"ran": True, "scores": scores, "reasons": reasons, "verdict": verdict}


def check(image, analysis, llm, blueprint=None):
    rules = rule_check(image)
    vision = vision_check(image, analysis, llm, blueprint) if not rules else \
        {"ran": False, "skipped": "rule check already failed", "scores": {}, "reasons": [], "verdict": {}}
    reasons = rules + vision["reasons"]
    return {"passed": not reasons, "reasons": reasons, "rules": rules, "vision": vision, "scores": vision["scores"]}
