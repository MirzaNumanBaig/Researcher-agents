"""Create one featured image per article with Cloudflare Workers AI (standard library only).

Env (GitHub Actions secrets): CF_ACCOUNT_ID, CF_API_TOKEN.  The model is MODEL below (FLUX.1 schnell). CF_IMAGE_MODEL overrides it only where it is set explicitly (the test-image-model workflow, local runs); the sending workflows do not pass it.
For every article whose status is pending/approved/sent and that has no `image:` yet, it reads the front matter `image_prompt`
(a scene description the writer produced; never a real person), asks Cloudflare for an image, resizes and centre-crops it to exactly 1600x900 (config: OUT_WIDTH/OUT_HEIGHT), converts it to WebP (Pillow) and saves it as
articles/images/<article-name>.webp (git-ignored; the publish step uploads it in the same run) and adds `image:` and `image_alt:` to the front matter. publish_wordpress.py uploads it
and sets it as the post's featured image. Without the secrets, or with "ai_images": false in config.json, this does nothing, so the pipeline keeps working.
Only articles that are about to be (or were just) sent get an image, so no request is wasted on a drafts waiting for a human:
  approved                         always
  pending                          only with --include-pending (the writer workflow, which auto-approves and sends right after)
  sent without wp_media_id         only when the article is at most RETRY_HOURS old (retries a failed upload; never backfills old posts)
usage: generate_images.py [--max N] [--include-pending]
       generate_images.py --sample "scene" [--out file.webp]   one test image with CF_IMAGE_MODEL (nothing is saved to articles or WordPress)
Models (to change the live model, edit the MODEL default below), all inside Cloudflare's free 10,000 neurons/day at your volume (neurons per 1536x896 image, 6 tiles, rounded up):
  @cf/black-forest-labs/flux-2-klein-4b   ~156 (about 60 images/day free; multipart request, 1024x576 as proven in PR #5)
  @cf/black-forest-labs/flux-1-schnell    DEFAULT. ~70-110 (about 90+ images/day free; JSON, size not selectable)
  @cf/lykon/dreamshaper-8-lcm             the old default (its sample pictures were poor; price not in Cloudflare's table)
Each has its own request settings in MODEL_SETTINGS below. Leonardo Lucid/Phoenix cost 3,400-4,100 neurons per image (2-3 images/day free), so they are not offered.
"""
import base64
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACCOUNT, TOKEN = os.environ.get("CF_ACCOUNT_ID", "").strip(), os.environ.get("CF_API_TOKEN", "").strip()
MODEL = os.environ.get("CF_IMAGE_MODEL", "@cf/black-forest-labs/flux-1-schnell")
BASE = os.environ.get("CF_API_BASE", "https://api.cloudflare.com/client/v4").rstrip("/")
STYLE = "editorial photograph, cinematic lighting, shallow depth of field, rich colour, no text, no logos, no watermark, no people's faces"
FALLBACK = {  # used only when the writer gave no image_prompt; scenes, never people
    "movies": "a empty cinema auditorium with red seats and a bright projector beam",
    "tv": "a cosy living room with a glowing television in the evening",
    "music": "a concert stage with warm spotlights and an empty microphone stand",
    "fashion": "a runway with soft spotlights and rows of empty chairs",
}
# Final file: 1600x900 WebP. The model is asked for a canvas near that size (see gen_size)
# and the result is cover-cropped to the exact size, so the picture is never stretched.
OUT_W, OUT_H = int(os.environ.get("OUT_WIDTH", "1600")), int(os.environ.get("OUT_HEIGHT", "900"))
WEBP_QUALITY = int(os.environ.get("WEBP_QUALITY", "82"))
RETRY_HOURS = 48
DEFAULT_SCENE = "a red carpet at night with camera flashes and velvet ropes, no people"


def split(text):
    m = re.match(r"---\n(.*?)\n---\n\n?(.*)", text, re.S)
    return (m.group(1), m.group(2)) if m else ("", text)


def field(front, key):
    m = re.search(rf"^{key}: ?(.*)$", front, re.M)
    if not m:
        return ""
    v = m.group(1).strip()
    try:
        return json.loads(v) if v.startswith('"') else v
    except ValueError:
        return v.strip('"')


def set_field(front, key, value):
    line = f"{key}: {json.dumps(value)}"
    if re.search(rf"^{key}: ?.*$", front, re.M):
        return re.sub(rf"^{key}: ?.*$", lambda _: line, front, count=1, flags=re.M)
    return front + "\n" + line


def scene_for(front):
    p = field(front, "image_prompt").strip()
    if p:
        return p
    cats = (field(front, "categories") or "").lower()
    for k, v in FALLBACK.items():
        if k in cats:
            return v
    return DEFAULT_SCENE


# Request settings per model (Workers AI REST). A model not listed gets the dreamshaper-style defaults.
#   steps_key/steps: diffusion steps parameter (None: the model takes none)   multipart: FLUX.2 wants multipart form data, not JSON
#   size: (width, height) to ask for when CF_GEN_WIDTH/HEIGHT are not set     no_size: the model has no width/height input
MODEL_SETTINGS = {
    "@cf/lykon/dreamshaper-8-lcm": {"steps_key": "num_steps", "steps": 8},
    "@cf/black-forest-labs/flux-2-klein-4b": {"steps_key": None, "multipart": True, "size": (1024, 576)},
    "@cf/black-forest-labs/flux-1-schnell": {"steps_key": "steps", "steps": 4, "no_size": True},
}


def settings(model):
    return MODEL_SETTINGS.get(model, MODEL_SETTINGS["@cf/lykon/dreamshaper-8-lcm"])


def gen_size(model):
    """Size requested from the model: env override, else the model's own proven size, else 1536x896."""
    w, h = settings(model).get("size", (1536, 896))
    return int(os.environ.get("CF_GEN_WIDTH") or w), int(os.environ.get("CF_GEN_HEIGHT") or h)


def build_body(model, prompt, width, height):
    """Request fields for one image. CF_IMAGE_STEPS overrides the step count."""
    cfg = settings(model)
    body = {"prompt": f"{prompt}, {STYLE}"}
    if not cfg.get("no_size"):
        body.update(width=width, height=height)
    if cfg.get("steps_key"):
        body[cfg["steps_key"]] = int(os.environ.get("CF_IMAGE_STEPS") or cfg["steps"])
    return body


def encode(model, fields):
    """(bytes, content-type): multipart form data for FLUX.2, JSON for the others."""
    if settings(model).get("multipart"):
        boundary = "----ra" + os.urandom(8).hex()
        parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items()]
        return b"".join(parts) + f"--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"
    return json.dumps(fields).encode(), "application/json"


def wants_image(status, stem, include_pending, now):
    """Whether an article of this status should get an image now. stem is the file name: YYYY-MM-DD-HH-MM-celebrity."""
    if status == "approved":
        return True
    if status == "pending":
        return include_pending
    if status == "sent":
        try:
            made = datetime.strptime(stem[:16], "%Y-%m-%d-%H-%M").replace(tzinfo=timezone.utc)
        except ValueError:
            return False
        return now - made <= timedelta(hours=RETRY_HOURS)
    return False


def render(prompt):
    body, ctype_in = encode(MODEL, build_body(MODEL, prompt, *gen_size(MODEL)))
    req = urllib.request.Request(f"{BASE}/accounts/{ACCOUNT}/ai/run/{MODEL}", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": ctype_in, "User-Agent": "researcher-agents"})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw, ctype = r.read(), r.headers.get("Content-Type", "")
    if ctype.startswith("image/"):
        return raw
    j = json.loads(raw)
    if not j.get("success", True):
        raise RuntimeError(str(j.get("errors"))[:200])
    img = (j.get("result") or {}).get("image")
    if not img:
        raise RuntimeError("no image in the response")
    return base64.b64decode(img)


def to_webp(raw):
    """Cover-crop the generated image to OUT_W x OUT_H and encode it as WebP. Returns (bytes, extension)."""
    try:
        from PIL import Image
    except ImportError:
        print("::warning::Pillow is not installed; keeping the original image format (pip install pillow)", file=sys.stderr)
        return raw, "png"
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    scale = max(OUT_W / img.width, OUT_H / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left, top = (img.width - OUT_W) // 2, (img.height - OUT_H) // 2
    img = img.crop((left, top, left + OUT_W, top + OUT_H))
    out = io.BytesIO()
    img.save(out, "WEBP", quality=WEBP_QUALITY, method=6)
    return out.getvalue(), "webp"


def sample():
    """One test image with the configured model, to compare models before switching the pipeline over."""
    if not (ACCOUNT and TOKEN):
        sys.exit("CF_ACCOUNT_ID / CF_API_TOKEN are not set.")
    scene = sys.argv[sys.argv.index("--sample") + 1]
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else Path("sample.webp")
    try:
        data, ext = to_webp(render(scene))
    except urllib.error.HTTPError as e:
        sys.exit(f"{MODEL}: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:300]}")
    out.write_bytes(data)
    print(f"ok {MODEL}: {out} ({len(data) // 1024} KB, {OUT_W}x{OUT_H} {ext})")


def usage_file():
    return ROOT / "articles" / "image-meta" / "_usage.json"


def used_today(today):
    try:
        u = json.loads(usage_file().read_text())
        return u["images"] if u.get("date") == today else 0
    except (OSError, ValueError, KeyError):
        return 0


def add_used(today, n):
    usage_file().parent.mkdir(parents=True, exist_ok=True)
    usage_file().write_text(json.dumps({"date": today, "images": used_today(today) + n}) + "\n")


def brief_image(front):
    """The news photo link in this article's brief (only used when image_pipeline.reference_images is on), else ''."""
    slug = lambda t: re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")  # noqa: E731
    try:
        brief = json.loads((ROOT / "briefs" / slug(field(front, "batch")) / f"{slug(field(front, 'celebrity'))}.json").read_text())
        return next((st["image"] for st in brief["stories"] if st.get("image")), "")
    except (OSError, ValueError, KeyError):
        return ""


def main():
    if "--sample" in sys.argv:
        return sample()
    if json.loads((ROOT / "config.json").read_text()).get("ai_images", True) is False:
        print("ai_images is false in config.json; no images generated.")
        return
    if not (ACCOUNT and TOKEN):
        print("CF_ACCOUNT_ID / CF_API_TOKEN not set; no images generated.")
        return
    limit = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 20
    out_dir = ROOT / "articles" / "images"
    now = datetime.now(timezone.utc)
    done = failed = 0
    today = now.strftime("%Y-%m-%d")
    try:
        cap = int(os.environ.get("IMG_DAILY_IMAGE_CAP") or (json.loads((ROOT / "config.json").read_text()).get("image_pipeline") or {}).get("daily_image_cap", 40))
    except (OSError, ValueError):
        cap = 40
    try:  # the Article -> Image pipeline (agents/imagegen); any problem falls back to the writer's scene prompt below
        from imagegen import config as icfg, llm as illm, pipeline as ipipe
        use_pipeline, llm = icfg.get("enabled"), illm.get_llm()
    except Exception as e:
        print(f"image pipeline unavailable ({e}); using the writer's scene prompt", file=sys.stderr)
        use_pipeline, llm = False, None
    for f in sorted((ROOT / "articles").glob("*.md"), reverse=True):
        if done >= limit:
            break
        front, body = split(f.read_text())
        have = field(front, "image") and (ROOT / "articles" / field(front, "image")).exists()
        # images are not stored in git: an article needs one until WordPress has it (wp_media_id) or the file exists in this run
        if field(front, "wp_media_id") or have or not wants_image(field(front, "status"), f.stem, "--include-pending" in sys.argv, now):
            continue
        if used_today(today) >= cap:
            print(f"daily image cap reached ({cap} attempts today, UTC); the remaining articles wait until tomorrow so the free allowance is not used up")
            break
        res = None
        if use_pipeline:
            try:
                res = ipipe.run(ipipe.article_from_front(front, body, f.stem, field, brief_image(front) if icfg.get("reference_images") else ""), llm=llm)
            except Exception as e:
                print(f"pipeline error for {f.name}: {e}; using the writer's scene prompt", file=sys.stderr)
        if res is not None:
            add_used(today, max(1, len(res["attempts"])))
            if not res["ok"]:  # rejected by the quality check on every attempt, or the API failed: better no image than a bad one
                failed += 1
                why = res["error"] or "; ".join(r for a in res["attempts"] for r in a["reasons"]) or "unknown"
                print(f"FAIL {f.name}: no usable image ({why})", file=sys.stderr)
                if any(c in res["error"] for c in ("HTTP 401", "HTTP 403", "HTTP 429")):
                    break  # bad key or rate limit: stop instead of hammering the API
                continue
            data, ext = res["image"], res["ext"]
            front = set_field(front, "image_alt", res["alt"])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"{f.stem}.{ext}").write_bytes(data)
            front = set_field(front, "image", f"images/{f.stem}.{ext}")
            f.write_text(f"---\n{front}\n---\n\n{body}")
            done += 1
            print(f"ok {f.name} -> images/{f.stem}.{ext} ({len(data)//1024} KB, {res['analysis']['story_type']}, {res['prompt_source']} prompt)")
            continue
        scene = scene_for(front)
        add_used(today, 1)
        try:
            data, ext = to_webp(render(scene))
        except urllib.error.HTTPError as e:
            failed += 1
            print(f"FAIL {f.name}: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:160]}", file=sys.stderr)
            if e.code in (401, 403, 429):
                break  # bad key or rate limit: stop instead of hammering the API
            continue
        except Exception as e:
            failed += 1
            print(f"FAIL {f.name}: {e}", file=sys.stderr)
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{f.stem}.{ext}").write_bytes(data)
        front = set_field(front, "image", f"images/{f.stem}.{ext}")
        front = set_field(front, "image_alt", f"AI-generated illustration for: {field(front, 'title')}")
        f.write_text(f"---\n{front}\n---\n\n{body}")
        done += 1
        print(f"ok {f.name} -> images/{f.stem}.{ext} ({len(data)//1024} KB)")
    print(f"{done} image(s) created, {failed} failed")


if __name__ == "__main__":
    main()
