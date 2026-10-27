"""Step 4: the image. FLUX.1 schnell on Cloudflare Workers AI (4 steps, no guidance), saved seed, backoff on errors, cover-crop to the target size."""
import base64
import io
import json
import random
import time
import urllib.error
import urllib.request

from . import config

_sleep = time.sleep  # replaced in tests
_size_rejected = False  # set once the API refuses width/height; schnell's docs list no size input, so we try and fall back


class GenerationError(Exception):
    pass


def _request(prompt, seed, with_size):
    account, token = config.secret("CF_ACCOUNT_ID"), config.secret("CF_API_TOKEN")
    if not (account and token):
        raise GenerationError("CF_ACCOUNT_ID / CF_API_TOKEN are not set")
    base = (config.secret("CF_API_BASE") or "https://api.cloudflare.com/client/v4").rstrip("/")
    body = {"prompt": prompt, "steps": config.steps(), "seed": seed}  # no guidance: schnell does not use it
    if with_size:
        body.update(width=config.get("width"), height=config.get("height"))
    req = urllib.request.Request(f"{base}/accounts/{account}/ai/run/{config.get('image_model')}", data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": "researcher-agents"})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw, ctype = r.read(), r.headers.get("Content-Type", "")
    if ctype.startswith("image/"):
        return raw
    j = json.loads(raw)
    if not j.get("success", True):
        raise GenerationError(str(j.get("errors"))[:200])
    img = (j.get("result") or {}).get("image")
    if not img:
        raise GenerationError("no image in the response")
    return base64.b64decode(img)


def generate(prompt, seed=None, attempts=3):
    """One image from the prompt. Returns (raw image bytes, seed used). Retries rate limits, 5xx errors and timeouts with exponential backoff."""
    global _size_rejected
    seed = random.randint(0, 2**32 - 1) if seed in (None, "") else int(seed)
    last = None
    for i in range(attempts):
        try:
            return _request(prompt, seed, config.get("send_size") and not _size_rejected), seed
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:200]
            last = f"HTTP {e.code} {body}"
            if e.code in (400, 422) and config.get("send_size") and not _size_rejected:
                _size_rejected = True  # retry at once without width/height; the result is cropped to size afterwards
                continue
            if e.code not in (429, 500, 502, 503, 504):
                raise GenerationError(last)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            last = str(e)
        if i < attempts - 1:
            _sleep(2 * 3 ** i)
    raise GenerationError(f"gave up after {attempts} attempts: {last}")


def fit(raw, width=None, height=None, quality=82):
    """Cover-crop to width x height (never stretched) and convert to WebP. Returns (webp bytes, (raw width, raw height))."""
    from PIL import Image
    width, height = width or config.get("width"), height or config.get("height")
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    raw_size = img.size
    scale = max(width / img.width, height / img.height)
    img = img.resize((max(width, round(img.width * scale)), max(height, round(img.height * scale))), Image.LANCZOS)
    left, top = (img.width - width) // 2, (img.height - height) // 2
    out = io.BytesIO()
    img.crop((left, top, left + width, top + height)).save(out, "WEBP", quality=quality)
    return out.getvalue(), raw_size
