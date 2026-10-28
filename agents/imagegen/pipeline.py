"""The whole flow for one article: analyze -> scene blueprint -> stand-in cast -> prompt -> generate -> upscale/finish -> scored quality check (new seeds, then a symbolic fallback) -> metadata."""
import logging
import urllib.request

from . import analyzer, blueprint, cast, checker, concept, config, finish, generator, meta, prompt_writer, publisher
from . import llm as llmmod

log = logging.getLogger("imagegen")


def _scrub(analysis, names):
    """No real name may travel from the analysis into prompts, alt text or logs of prompts."""
    out = dict(analysis)
    for k in ("core_event", "setting", "time_and_light", "emotion"):
        out[k] = concept.strip_names(out.get(k, ""), names)[0]
    for k in ("key_objects", "palette"):
        out[k] = [concept.strip_names(x, names)[0] for x in out.get(k, [])]
    return out


def fetch_reference(url):
    """The news photo's bytes (at most 3 MB) and mime type, or (None, None). Only used to build the scene blueprint; the photo itself is never kept or reused."""
    if not (url and config.get("reference_images")):
        return None, None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "researcher-agents"}), timeout=20) as r:
            return r.read(3_000_000), (r.headers.get("Content-Type") or "image/jpeg").split(";")[0]
    except Exception as e:
        log.info("reference image skipped: %s", e)
        return None, None


def _attempt(prompt, seed, analysis, bp, llm, key, number):
    """One generate -> finish -> check round. Returns (record, image bytes or None, finish info, seed used, error)."""
    raw, used = generator.generate(prompt, seed)
    image, info = finish.finish(raw)
    qc = checker.check(image, analysis, llm, bp)
    rec = {"seed": used, "raw_size": info["raw_size"], "passed": qc["passed"], "reasons": qc["reasons"], "scores": qc["scores"],
           "vision_ran": qc["vision"]["ran"], "vision_skipped": qc["vision"].get("skipped", "")}
    log.info("[%s] attempt %d seed %s: %s %s %s", key, number, used, "passed" if qc["passed"] else "REJECTED", "; ".join(qc["reasons"]), qc["scores"] or "")
    return rec, (image if qc["passed"] else None), info, used


def run(article, preset=None, seed=None, llm="auto", save_meta=True):
    """article: {key, headline, body, category, source_url, reference_image_url, names}.
    Returns {ok, image, ext, alt, analysis, blueprint, stand_ins, prompt, seed, attempts, ...}. ok is False when nothing passed the quality check (then no image is used).
    Flow: story analysis -> scene blueprint (from the news photo when allowed, else from the story) -> stand-in cast -> prompt -> generate -> upscale and finish ->
    scored check (new seed on a low score, 3 attempts) -> if all fail, one calm symbolic scene instead of a face-led picture."""
    key = article["key"]
    llm = llmmod.get_llm() if llm == "auto" else llm
    names = concept.known_names(article["headline"], article.get("names", ()))
    analysis = _scrub(analyzer.analyze(article["headline"], article.get("body", ""), article.get("category", ""), article.get("source_url", ""), "", llm), names)
    log.info("[%s] analysis: %s, %s, sensitivity %s (%s)", key, analysis["story_type"], analysis["emotion"], analysis["sensitivity"], analysis["source"])
    ref, mime = fetch_reference(article.get("reference_image_url"))
    bp = blueprint.from_reference(ref, analysis, names, llm, mime or "image/jpeg") if ref else None
    bp = bp or blueprint.default_blueprint(analysis, names)
    history = meta.load_history()
    standins = cast.assign(bp, history, key)
    log.info("[%s] blueprint (%s): %s; stand-ins: %s", key, bp["source"], blueprint.summary(bp), ", ".join(s["id"] for s in standins) or "none")
    pr = prompt_writer.write_prompt(analysis, preset or config.get("preset"), history, names, llm, key, bp, standins)
    log.info("[%s] prompt (%s, %d words): %s", key, pr["source"], concept.words(pr["prompt"]), pr["prompt"])
    attempts, image, used_seed, error, info, fallback = [], None, None, "", {}, ""
    for i in range(1 + config.get("max_retries")):
        try:
            rec, image, info, used_seed = _attempt(pr["prompt"], seed if i == 0 else None, analysis, bp, llm, key, i + 1)
        except (generator.GenerationError, OSError, ValueError) as e:
            if "flagged" in str(e):  # Cloudflare's safety filter flagged this output: a new seed may pass, so count it as a rejected attempt and go on
                attempts.append({"seed": None, "passed": False, "reasons": ["the output was flagged by Cloudflare's safety filter"], "scores": {}, "vision_ran": False, "vision_skipped": ""})
                log.warning("[%s] attempt %d flagged by the safety filter", key, i + 1)
                continue
            error = str(e)
            log.warning("[%s] attempt %d failed: %s", key, i + 1, e)
            break
        attempts.append(rec)
        if image:
            break
    if image is None and attempts and not error and bp["people"]:  # every face-led attempt was rejected: a symbolic scene (props, setting, no faces) instead
        sym = dict(analysis, sensitivity="sensitive")
        sym_pr = prompt_writer.write_prompt(sym, preset or config.get("preset"), history, names, None, key)
        log.info("[%s] falling back to a symbolic scene: %s", key, sym_pr["prompt"])
        try:
            rec, image, info, used_seed = _attempt(sym_pr["prompt"], None, sym, dict(bp, people=[], people_count=0), llm, key, len(attempts) + 1)
            rec["fallback"] = "symbolic"
            attempts.append(rec)
            if image:
                pr, fallback, standins = sym_pr, "symbolic", []
        except (generator.GenerationError, OSError, ValueError) as e:
            error = str(e)
            log.warning("[%s] symbolic fallback failed: %s", key, e)
    ext = info.get("ext", config.out_ext())
    alt = publisher.alt_text(analysis, names, bp if not fallback else None, standins)
    result = {"ok": image is not None, "image": image, "webp": image, "ext": ext, "alt": alt, "caption": config.caption(), "analysis": analysis, "blueprint": bp,
              "stand_ins": [s["id"] for s in standins], "prompt": pr["prompt"], "prompt_source": pr["source"], "seed": used_seed, "attempts": attempts, "error": error,
              "fallback": fallback, "finish": info, "preset": preset or config.get("preset"), "model": config.get("image_model"),
              "variation": {k: pr[k] for k in ("shot", "angle", "lens", "palette")}}
    if save_meta:
        meta.save(key, {"article": key, "ai_generated": True, "story_type": analysis["story_type"], "analysis": analysis, "scene_blueprint": bp,
                        "stand_ins": result["stand_ins"], "prompt": pr["prompt"], "prompt_source": pr["source"], "prompt_notes": pr["notes"], "seed": used_seed,
                        "seed_supported": generator.seed_supported(), "model": result["model"], "preset": result["preset"], "alt": alt, "caption": result["caption"],
                        "finish": info, "fallback": fallback, "ok": result["ok"], "error": error, "quality": attempts})
        if result["ok"]:
            meta.add_history({"article": key, **result["variation"], "prompt": pr["prompt"], "cast": result["stand_ins"]})
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
