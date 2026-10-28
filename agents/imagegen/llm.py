"""Provider-neutral text and vision calls. cloudflare (default, same account as the image model), anthropic (optional), none."""
import base64
import json
import re
import time
import urllib.error
import urllib.request

import cf_accounts
from . import config

_sleep = time.sleep  # replaced in tests


class LLMError(Exception):
    pass


def parse_json(text):
    """The first JSON object in a model reply (tolerates code fences, chatter around it and trailing commas)."""
    if isinstance(text, dict):
        return text
    s = re.sub(r"```(?:json)?", "", text or "")
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("no JSON object in the reply")
    chunk = s[a:b + 1]
    try:
        return json.loads(chunk)
    except ValueError:
        return json.loads(re.sub(r",\s*([}\]])", r"\1", chunk))


def post_json(url, headers, payload, timeout=90, attempts=3):
    """POST JSON with exponential backoff on rate limits, 5xx errors and timeouts. Raises LLMError."""
    last = None
    for i in range(attempts):
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": "researcher-agents", **headers})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            last = f"HTTP {e.code} {body}"
            if e.code not in (429, 500, 502, 503, 504) or "daily free allocation" in body:
                raise LLMError(last)  # a spent daily allowance cannot be fixed by waiting a few seconds
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = str(e)
        if i < attempts - 1:
            _sleep(2 * 3 ** i)
    raise LLMError(f"gave up after {attempts} attempts: {last}")


class Cloudflare:
    name = "cloudflare"

    def __init__(self):
        self.base = (config.secret("CF_API_BASE") or "https://api.cloudflare.com/client/v4").rstrip("/")
        if not cf_accounts.load():
            raise LLMError("CF_ACCOUNT_ID / CF_API_TOKEN are not set")

    def _run(self, model, payload, kind="text"):
        while True:
            creds = cf_accounts.active()
            if creds is None:
                raise LLMError(cf_accounts.none_left_message())
            try:
                j = post_json(f"{self.base}/accounts/{creds[0]}/ai/run/{model}", {"Authorization": f"Bearer {creds[1]}"}, payload)
                cf_accounts.record(creds[0], cf_accounts.cost(kind))  # estimated neurons for the daily budget
                break
            except LLMError as e:
                if not cf_accounts.is_quota_error(str(e)):
                    raise
                cf_accounts.mark_spent(creds[0])  # spent: try the next account, or fail when there is none
        if not j.get("success", True):
            raise LLMError(str(j.get("errors"))[:300])
        out = (j.get("result") or {}).get("response")
        if isinstance(out, (dict, list)):
            out = json.dumps(out)
        if not out:
            raise LLMError("empty reply")
        return out

    def complete(self, system, user, max_tokens=700, temperature=0.4):
        return self._run(config.get("llm_model"), {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                                                    "max_tokens": max_tokens, "temperature": temperature}, "text")

    def vision(self, system, user, image, mime="image/webp"):
        uri = f"data:{mime};base64,{base64.b64encode(image).decode()}"
        msgs = [{"role": "system", "content": system},
                {"role": "user", "content": [{"type": "text", "text": user}, {"type": "image_url", "image_url": {"url": uri}}]}]
        try:
            return self._run(config.get("vision_model"), {"messages": msgs, "max_tokens": 400, "temperature": 0.1}, "vision")
        except LLMError as e:
            if "HTTP 400" not in str(e) and "HTTP 422" not in str(e):
                raise
        return self._run(config.get("vision_model"), {"prompt": f"{system}\n\n{user}", "image": list(image), "max_tokens": 400}, "vision")  # older image input shape

    def accept_vision_license(self):
        """One-time acceptance of Meta's licence for the vision model. Only ever called when the user explicitly asks for it."""
        return self._run(config.get("vision_model"), {"prompt": "agree"})


class Anthropic:
    name = "anthropic"

    def __init__(self):
        self.key = config.secret("ANTHROPIC_API_KEY")
        if not self.key:
            raise LLMError("ANTHROPIC_API_KEY is not set")

    def _msg(self, system, content, max_tokens):
        model = config.get("llm_model") if config.get("llm_model").startswith("claude") else "claude-haiku-5-5"
        j = post_json("https://api.anthropic.com/v1/messages", {"x-api-key": self.key, "anthropic-version": "2023-06-01"},
                      {"model": model, "max_tokens": max_tokens, "system": system, "messages": [{"role": "user", "content": content}]})
        return "".join(b.get("text", "") for b in j.get("content", []))

    def complete(self, system, user, max_tokens=700, temperature=0.4):
        return self._msg(system, user, max_tokens)

    def vision(self, system, user, image, mime="image/webp"):
        block = {"type": "image", "source": {"type": "base64", "media_type": mime, "data": base64.b64encode(image).decode()}}
        return self._msg(system, [block, {"type": "text", "text": user}], 400)


def get_llm():
    """The configured provider, or None when it is 'none' or its credentials are missing (callers then use the rule-based fallbacks)."""
    kind = config.get("llm_provider").lower()
    try:
        return {"cloudflare": Cloudflare, "anthropic": Anthropic}[kind]() if kind in ("cloudflare", "anthropic") else None
    except LLMError:
        return None
