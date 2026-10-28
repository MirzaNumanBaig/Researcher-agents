"""Step 4: the image. FLUX.1 schnell on Cloudflare Workers AI (4 steps, no guidance), saved seed, backoff on errors. Upscaling, cropping and encoding live in finish.py."""
import base64
import json
import os
import random
import re
import time
import urllib.error
import urllib.request

import cf_accounts
from . import config

_sleep = time.sleep  # replaced in tests
_rejected = set()  # request fields this API refused (Cloudflare's schnell accepts only prompt and steps, so seed/width/height end up here)
OPTIONAL = {"seed", "width", "height"}


class GenerationError(Exception):
    pass


def seed_supported():
    return "seed" not in _rejected


SCHNELL = "@cf/black-forest-labs/flux-1-schnell"
KLEIN = "@cf/black-forest-labs/flux-2-klein-4b"
# per model: steps (None = the model takes none), multipart form data instead of JSON, and the size it is asked for when IMG_WIDTH / IMG_HEIGHT are 0
MODELS = {SCHNELL: {"steps": True, "multipart": False, "size": (1536, 864)},
          KLEIN: {"steps": False, "multipart": True, "size": (1024, 576)}}  # 1024x576 is the size proven for klein; the picture is upscaled afterwards


def model_settings():
    return MODELS.get(config.get("image_model"), MODELS[SCHNELL])


def size():
    w, h = model_settings()["size"]
    return config.get("width") or w, config.get("height") or h


def _body(prompt, seed):
    body = {"prompt": prompt}
    if model_settings()["steps"]:
        body["steps"] = config.steps()  # no guidance: schnell does not use it
    if seed is not None:
        body["seed"] = seed
    if config.get("send_size"):
        body["width"], body["height"] = size()
    return {k: v for k, v in body.items() if k not in _rejected}


def _encode(fields):
    """(bytes, content type): multipart form data for klein, JSON for schnell."""
    if model_settings()["multipart"]:
        boundary = "----ra" + os.urandom(8).hex()
        parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items()]
        return b"".join(parts) + f"--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"
    return json.dumps(fields).encode(), "application/json"


def _request(prompt, seed, creds=None):
    account, token = creds or cf_accounts.active() or (None, None)
    if not (account and token):
        raise GenerationError(cf_accounts.none_left_message())
    base = (config.secret("CF_API_BASE") or "https://api.cloudflare.com/client/v4").rstrip("/")
    data, ctype_in = _encode(_body(prompt, seed))
    req = urllib.request.Request(f"{base}/accounts/{account}/ai/run/{config.get('image_model')}", data=data,
                                 method="POST", headers={"Authorization": f"Bearer {token}", "Content-Type": ctype_in, "User-Agent": "researcher-agents"})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw, ctype = r.read(), r.headers.get("Content-Type", "")
    cf_accounts.record(account, cf_accounts.cost("image", config.get("image_model")))  # estimated neurons for the daily budget
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
    """One image from the prompt. Returns (raw image bytes, seed used or None when the API has no seed input).
    A random seed is tried by default; fields the API rejects (seed, width, height) are dropped and remembered. Rate limits, 5xx errors and timeouts back off exponentially."""
    seed = random.randint(0, 2**32 - 1) if seed in (None, "") else int(seed)
    last, tries, drops = None, 0, 0
    while tries < attempts:
        creds = cf_accounts.active()
        try:
            return _request(prompt, seed, creds), (None if "seed" in _rejected else seed)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            last = f"HTTP {e.code} {body}"
            if e.code in (400, 422) and "flagged" in body:
                raise GenerationError(last)  # Cloudflare's safety filter flagged this output: not a size problem; the caller tries a new seed
            if e.code in (400, 422):
                named = {m for m in re.findall(r"'/(\w+)'", body) if m in OPTIONAL}
                new = (named or ({"width", "height"} if config.get("send_size") else set())) - _rejected  # unnamed error: suspect the size first
                if new and drops < 3:
                    _rejected.update(new)
                    drops += 1
                    continue  # retry at once without those fields (the image is cropped to size afterwards)
                raise GenerationError(last)
            if cf_accounts.is_quota_error(body) and creds:
                cf_accounts.mark_spent(creds[0])  # this account is done for the day: the next one takes over at once
                if cf_accounts.active():
                    continue
                raise GenerationError(last)
            if e.code not in (429, 500, 502, 503, 504):
                raise GenerationError(last)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            last = str(e)
        tries += 1
        if tries < attempts:
            _sleep(2 * 3 ** (tries - 1))
    raise GenerationError(f"gave up after {attempts} attempts: {last}")
