"""Step 5: quality check. Cheap rules always run; a vision model also looks for text, logos, bad hands/faces, recognisable people, nudity, injury and story mismatch."""
import io

from . import config
from . import llm as llmmod

SYSTEM = "You are a strict picture editor checking an AI-generated news illustration. Answer with ONE JSON object only."
FLAGS = {"visible_text_or_logos": "visible text or logos", "distorted_hands_or_faces": "distorted hands or faces in the foreground",
         "recognizable_real_person": "a clearly recognizable real person", "nudity": "nudity", "graphic_injury": "graphic injury"}


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


def vision_check(image, analysis, llm):
    """Returns {ran, reasons, verdict}. When the vision model is unavailable (not configured, licence not accepted, API error) it is skipped, not failed."""
    if llm is None or not config.get("vision_check"):
        return {"ran": False, "skipped": "vision check is off or no LLM provider is configured", "reasons": [], "verdict": {}}
    user = (f"The illustration should show this story: {analysis.get('core_event')} (mood: {analysis.get('emotion')}, setting: {analysis.get('setting')}). "
            'Return JSON: {"visible_text_or_logos": bool, "distorted_hands_or_faces": bool, "recognizable_real_person": bool, "nudity": bool, '
            '"graphic_injury": bool, "matches_story_mood": bool, "notes": "one short sentence"}')
    try:
        verdict = llmmod.parse_json(llm.vision(SYSTEM, user, image))
    except (llmmod.LLMError, ValueError) as e:
        return {"ran": False, "skipped": f"vision model unavailable: {str(e)[:160]}", "reasons": [], "verdict": {}}
    reasons = [text for key, text in FLAGS.items() if verdict.get(key) is True]
    if verdict.get("matches_story_mood") is False:
        reasons.append("does not match the story's event or mood")
    return {"ran": True, "reasons": reasons, "verdict": verdict}


def check(image, analysis, llm):
    rules = rule_check(image)
    vision = vision_check(image, analysis, llm) if not rules else {"ran": False, "skipped": "rule check already failed", "reasons": [], "verdict": {}}
    reasons = rules + vision["reasons"]
    return {"passed": not reasons, "reasons": reasons, "rules": rules, "vision": vision}
