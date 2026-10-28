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
    "image_model": "@cf/black-forest-labs/flux-2-klein-4b",  # default; "@cf/black-forest-labs/flux-1-schnell" is the other free-tier model (see generator.MODELS)
    "steps": 4,                                             # schnell is distilled for 4 steps; never more than 4
    "width": 0,                                             # generation size; 0 = the model's own (klein 1024x576, schnell 1536x864: 16:9, schnell gets worse above ~1.3 MP)
    "height": 0,
    "send_size": True,                                      # ask the API for width x height; retried without when rejected (Cloudflare's schnell may ignore it)
    "seed": "",                                             # empty = random per attempt; the seed used is always saved
    "max_retries": 2,                                       # new seed after a failed quality check (3 attempts in all), then one symbolic-scene fallback
    "min_score": 4,                                         # vision quality scores are 1-5; any score under this rejects the image
    "upscaler": "lanczos",                                  # lanczos (built in) | realesrgan (needs the realesrgan-ncnn-vulkan program, see upscale_cmd) | none
    "upscale_factor": 2,                                    # how much the upscaler enlarges before the final crop and downscale
    "upscale_cmd": "realesrgan-ncnn-vulkan -i {input} -o {output} -s {scale}",  # command template for upscaler=realesrgan; falls back to lanczos when it fails
    "out_width": 1600,                                      # final featured image (1920 x 1080 for the large size)
    "out_height": 900,
    "out_format": "webp",                                   # webp | jpeg
    "out_quality": 90,                                      # starting quality; lowered step by step until the file fits max_kb
    "min_quality": 78,                                      # never go below this to save bytes
    "max_kb": 400,                                          # target file size for page speed ("where possible": the quality floor wins)
    "sharpen": 0.4,                                         # finishing pass: unsharp-mask strength, 0 = off
    "grain": 0.015,                                         # finishing pass: film grain amount, 0 = off
    "face_restore": "off",                                  # off | command: run face_restore_cmd on accepted images
    "face_restore_cmd": "",                                 # e.g. a CodeFormer or GFPGAN wrapper using {input} {output}; use a LOW strength so skin stays natural
    "cast_file": "agents/imagegen/cast.json",               # fictional stand-in characters used instead of real people
    "preset": "candid_news_photo",                          # candid_news_photo | glossy_magazine | cinematic_still | soft_illustration
    "neuron_budget": 9000,                                  # per account and UTC day, estimated; the next account takes over at this point (0 = off). Cloudflare's free limit is 10,000
    "neurons_per_image": 0,                                 # estimate per picture; 0 = the model's default (schnell 170, klein 150)
    "neurons_per_text": 20,                                 # estimate per text call
    "neurons_per_vision": 80,                               # estimate per vision call
    "daily_image_cap": 40,                                  # image attempts per UTC day across all runs; protects the 10,000 free neurons a day
    "history_size": 20,                                     # last prompts remembered to vary shot, angle and palette
    "caption": "",                                          # visible caption under the image. OFF by default (empty or "off"); set text to turn it on. The AI flag is always kept in the log
    "reference_images": False,                              # build a scene_blueprint from the news photo (needs the vision model); recreated with stand-ins, never copied
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
    if isinstance(default, float):
        try:
            return float(raw)
        except (TypeError, ValueError):
            return default
    if isinstance(default, int):
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default
    return str(raw) if raw is not None else default


def steps():
    return max(1, min(4, get("steps")))  # schnell: 4 at most


def out_format():
    return "jpeg" if get("out_format").strip().lower() in ("jpg", "jpeg") else "webp"


def out_ext():
    return "jpg" if out_format() == "jpeg" else "webp"


def score_min():
    return max(1, min(5, get("min_score")))


def caption():
    c = get("caption").strip()
    return "" if c.lower() in ("", "off", "none", "false") else c


def secret(name):
    return os.environ.get(name, "").strip()
