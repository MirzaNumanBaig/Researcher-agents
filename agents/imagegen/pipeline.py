"""The whole flow for one article: analyze -> concept rules -> prompt -> generate -> quality check (retry with new seeds) -> metadata."""
import logging
import urllib.request

from . import analyzer, checker, concept, config, generator, meta, prompt_writer, publisher
from . import llm as llmmod

log = logging.getLogger("imagegen")


def _scrub(analysis, names):
    """No real name may travel from the analysis into prompts, alt text or logs of prompts."""
    out = dict(analysis)
    for k in ("core_event", "setting", "time_and_light", "emotion", "reference_analysis"):
        out[k] = concept.strip_names(out.get(k, ""), names)[0]
    for k in ("key_objects", "palette"):
        out[k] = [concept.strip_names(x, names)[0] for x in out.get(k, [])]
    return out


def describe_reference(url, llm):
    """Composition, angle, framing, mood and colour of the news photo, never a description of a person. Empty when unavailable."""
    if not (url and llm and config.get("reference_images")):
        return ""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "researcher-agents"}), timeout=20) as r:
            image = r.read(3_000_000)
        return llm.vision("You describe photo composition for a picture editor. Never describe or identify any person's face or likeness.",
                          "In two sentences describe only composition, camera angle, framing, mood, colour and setting.", image, "image/jpeg")[:400]
    except Exception as e:
        log.info("reference image skipped: %s", e)
        return ""


def run(article, preset=None, seed=None, llm="auto", save_meta=True):
    """article: {key, headline, body, category, source_url, reference_image_url, names}.
    Returns {ok, webp, alt, analysis, prompt, seed, attempts, ...}. ok is False when no attempt passed the quality check (then no image is used)."""
    key = article["key"]
    llm = llmmod.get_llm() if llm == "auto" else llm
    names = concept.known_names(article["headline"], article.get("names", ()))
    reference = describe_reference(article.get("reference_image_url"), llm)
    analysis = _scrub(analyzer.analyze(article["headline"], article.get("body", ""), article.get("category", ""), article.get("source_url", ""), reference, llm), names)
    log.info("[%s] analysis: %s, %s, sensitivity %s (%s)", key, analysis["story_type"], analysis["emotion"], analysis["sensitivity"], analysis["source"])
    history = meta.load_history()
    pr = prompt_writer.write_prompt(analysis, preset or config.get("preset"), history, names, llm, key)
    log.info("[%s] prompt (%s, %d words): %s", key, pr["source"], concept.words(pr["prompt"]), pr["prompt"])
    attempts, webp, used_seed, error = [], None, None, ""
    for i in range(1 + config.get("max_retries")):
        try:
            raw, used = generator.generate(pr["prompt"], seed if i == 0 else None)
            fitted, raw_size = generator.fit(raw)
        except (generator.GenerationError, OSError, ValueError) as e:
            error = str(e)
            log.warning("[%s] attempt %d failed: %s", key, i + 1, e)
            break
        qc = checker.check(fitted, analysis, llm)
        attempts.append({"seed": used, "raw_size": list(raw_size), "passed": qc["passed"], "reasons": qc["reasons"],
                         "vision_ran": qc["vision"]["ran"], "vision_skipped": qc["vision"].get("skipped", "")})
        log.info("[%s] attempt %d seed %s: %s %s", key, i + 1, used, "passed" if qc["passed"] else "REJECTED", "; ".join(qc["reasons"]))
        if qc["passed"]:
            webp, used_seed = fitted, used
            break
    alt = publisher.alt_text(analysis, names)
    result = {"ok": webp is not None, "webp": webp, "alt": alt, "caption": config.caption(), "analysis": analysis, "prompt": pr["prompt"],
              "prompt_source": pr["source"], "seed": used_seed, "attempts": attempts, "error": error, "preset": preset or config.get("preset"),
              "model": config.get("image_model"), "variation": {k: pr[k] for k in ("shot", "angle", "lens", "palette")}}
    if save_meta:
        meta.save(key, {"article": key, "story_type": analysis["story_type"], "analysis": analysis, "prompt": pr["prompt"], "prompt_source": pr["source"],
                        "prompt_notes": pr["notes"], "seed": used_seed, "seed_supported": generator.seed_supported(), "model": result["model"], "preset": result["preset"], "alt": alt,
                        "ok": result["ok"], "error": error, "quality": attempts})
        if result["ok"]:
            meta.add_history({"article": key, **result["variation"], "prompt": pr["prompt"]})
    return result


def article_from_front(front, body, key, field, brief_image=""):
    """Build the pipeline input from an article file's front matter (field = the repo's front matter reader)."""
    import re
    tags = re.findall(r'"([^"]+)"', (re.search(r"^tags: ?(\[.*\])$", front, re.M) or [0, ""])[1])
    cats = re.findall(r'"([^"]+)"', (re.search(r"^categories: ?(\[.*\])$", front, re.M) or [0, ""])[1])
    src = re.search(r'^\s+- "(https?://[^"]+)"', front, re.M)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", body or "")
    return {"key": key, "headline": field(front, "title"), "body": text, "category": ", ".join(cats), "source_url": src.group(1) if src else "",
            "reference_image_url": brief_image, "names": [n for n in [field(front, "celebrity")] + tags if n]}
