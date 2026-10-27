"""Settings for the image pipeline. Order: environment variable IMG_<NAME>, then config.json "image_pipeline", then the default below.
Secrets are only ever read from the environment: CF_ACCOUNT_ID, CF_API_TOKEN, ANTHROPIC_API_KEY, WP_URL, WP_USER, WP_APP_PASSWORD."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULTS = {
    "enabled": True,                                        # generate_images.py uses the pipeline (falls back to the writer's image_prompt on any error)
    "llm_provider": "cloudflare",                           # cloudflare (same secrets as the image model) | anthropic (needs ANTHROPIC_API_KEY) | none (rule-based only)
    "llm_model": "@cf/meta/llama-3.1-8b-instruct-fp8-fast",  # cheap and fits the free neurons; "@cf/meta/llama-3.3-70b-instruct-fp8-fast" is better but ~6x the cost
    "vision_model": "@cf/meta/llama-3.2-11b-vision-instruct",
    "vision_check": True,                                   # skipped automatically when the vision model is unavailable (e.g. licence not accepted)
    "image_model": "@cf/black-forest-labs/flux-1-schnell",
    "steps": 4,                                             # schnell is distilled for 4 steps; never more than 4
    "width": 1344,
    "height": 768,
    "send_size": True,                                      # ask the API for width x height; retried without when rejected
    "seed": "",                                             # empty = random per attempt; the seed used is always saved
    "max_retries": 2,                                       # new seed after a failed quality check
    "preset": "candid_news_photo",                          # candid_news_photo | glossy_magazine | cinematic_still | soft_illustration
    "history_size": 20,                                     # last prompts remembered to vary shot, angle and palette
    "caption": "Illustration generated with AI",            # "" or "off" turns the caption off
    "reference_images": False,                              # analyse the news photo's composition (needs the vision model); never copied
    "meta_dir": "articles/image-meta",
}


def _file_cfg():
    try:
        return json.loads((ROOT / "config.json").read_text()).get("image_pipeline", {}) or {}
    except (OSError, ValueError):
        return {}


def get(name):
    default = DEFAULTS[name]
    raw = os.environ.get("IMG_" + name.upper())
    if raw is None:
        raw = _file_cfg().get(name, default)
    if isinstance(default, bool):
        return raw if isinstance(raw, bool) else str(raw).strip().lower() in ("1", "true", "yes", "on")
    if isinstance(default, int):
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default
    return str(raw) if raw is not None else default


def steps():
    return max(1, min(4, get("steps")))  # schnell: 4 at most


def caption():
    c = get("caption").strip()
    return "" if c.lower() in ("", "off", "none", "false") else c


def secret(name):
    return os.environ.get(name, "").strip()
