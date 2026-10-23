"""Create one featured image per article with Cloudflare Workers AI (standard library only).

Env (GitHub Actions secrets): CF_ACCOUNT_ID, CF_API_TOKEN.  Optional: CF_IMAGE_MODEL (default @cf/lykon/dreamshaper-8-lcm).
For every article whose status is pending/approved/sent and that has no `image:` yet, it reads the front matter `image_prompt`
(a scene description the writer produced; never a real person), asks Cloudflare for an image, resizes and centre-crops it to exactly 1500x900 (config: OUT_WIDTH/OUT_HEIGHT), converts it to WebP (Pillow) and saves it as
articles/images/<article-name>.webp (git-ignored; the publish step uploads it in the same run) and adds `image:` and `image_alt:` to the front matter. publish_wordpress.py uploads it
and sets it as the post's featured image. Without the secrets this does nothing, so the pipeline keeps working.
usage: generate_images.py [--max N]
"""
import base64
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACCOUNT, TOKEN = os.environ.get("CF_ACCOUNT_ID", "").strip(), os.environ.get("CF_API_TOKEN", "").strip()
MODEL = os.environ.get("CF_IMAGE_MODEL", "@cf/lykon/dreamshaper-8-lcm")
BASE = os.environ.get("CF_API_BASE", "https://api.cloudflare.com/client/v4").rstrip("/")
STYLE = "editorial photograph, cinematic lighting, shallow depth of field, rich colour, no text, no logos, no watermark, no people's faces"
FALLBACK = {  # used only when the writer gave no image_prompt; scenes, never people
    "movies": "a empty cinema auditorium with red seats and a bright projector beam",
    "tv": "a cosy living room with a glowing television in the evening",
    "music": "a concert stage with warm spotlights and an empty microphone stand",
    "fashion": "a runway with soft spotlights and rows of empty chairs",
}
# Final file: 1500x900 WebP. The model is asked for a slightly larger multiple-of-8 canvas (1536x896, Cloudflare accepts 256-2048)
# and the result is cover-cropped to the exact size, so the picture is never stretched.
OUT_W, OUT_H = int(os.environ.get("OUT_WIDTH", "1500")), int(os.environ.get("OUT_HEIGHT", "900"))
GEN_W, GEN_H = int(os.environ.get("CF_GEN_WIDTH", "1536")), int(os.environ.get("CF_GEN_HEIGHT", "896"))
WEBP_QUALITY = int(os.environ.get("WEBP_QUALITY", "82"))
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


def render(prompt):
    body = json.dumps({"prompt": f"{prompt}, {STYLE}", "width": GEN_W, "height": GEN_H, "num_steps": 8}).encode()
    req = urllib.request.Request(f"{BASE}/accounts/{ACCOUNT}/ai/run/{MODEL}", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json", "User-Agent": "researcher-agents"})
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


def main():
    if not (ACCOUNT and TOKEN):
        print("CF_ACCOUNT_ID / CF_API_TOKEN not set; no images generated.")
        return
    limit = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 20
    out_dir = ROOT / "articles" / "images"
    done = failed = 0
    for f in sorted((ROOT / "articles").glob("*.md"), reverse=True):
        if done >= limit:
            break
        front, body = split(f.read_text())
        have = field(front, "image") and (ROOT / "articles" / field(front, "image")).exists()
        # images are not stored in git: an article needs one until WordPress has it (wp_media_id) or the file exists in this run
        if field(front, "status") not in ("pending", "approved", "sent") or field(front, "wp_media_id") or have:
            continue
        scene = scene_for(front)
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
