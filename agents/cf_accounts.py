"""Several Cloudflare accounts for image generation, with a daily neuron budget per account (standard library only, shared by generate_images.py and imagegen/).
Secrets: CF_ACCOUNT_ID + CF_API_TOKEN (the first account), then CF_ACCOUNT_ID_2 + CF_API_TOKEN_2, ... up to _9. Only complete pairs count.

Which account is used: the first one that is neither spent nor over budget.
 - budget: each call adds an ESTIMATE of its neurons to articles/image-meta/_usage.json (kept per account slot number, never the id). When an account's estimate for
   today (UTC) reaches IMG_NEURON_BUDGET (default 9000 of Cloudflare's 10,000 free neurons) the next account takes over. 0 turns the budget off.
 - safety net: when Cloudflare itself answers "you have used up your daily free allocation", that account is marked spent for the rest of the run.
Text, vision and image calls share one pool, because they spend the same neurons."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUOTA_TEXT = "daily free allocation"
IMAGE_NEURONS = {"@cf/black-forest-labs/flux-1-schnell": 170, "@cf/black-forest-labs/flux-2-klein-4b": 150}  # measured / estimated per picture; IMG_NEURONS_PER_IMAGE overrides
_spent = set()


def _env(name):
    return os.environ.get(name, "").strip()


def _setting(name, default):
    """IMG_<NAME> from the environment, else config.json image_pipeline.<name>, else the default (always an int)."""
    raw = os.environ.get("IMG_" + name.upper())
    if raw is None:
        try:
            raw = (json.loads((ROOT / "config.json").read_text()).get("image_pipeline") or {}).get(name, default)
        except (OSError, ValueError):
            raw = default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def load():
    """[(account id, token)] in order, skipping incomplete pairs and duplicates."""
    out = []
    for suffix in [""] + [f"_{n}" for n in range(2, 10)]:
        pair = (_env("CF_ACCOUNT_ID" + suffix), _env("CF_API_TOKEN" + suffix))
        if all(pair) and pair not in out:
            out.append(pair)
    return out


def count():
    return len(load())


# ---- the daily budget -------------------------------------------------------------------------------------------------------------------

def budget():
    return _setting("neuron_budget", 9000)


def cost(kind, model=""):
    """Estimated neurons for one call: kind is image, text or vision."""
    if kind == "image":
        return _setting("neurons_per_image", 0) or IMAGE_NEURONS.get(model, 170)
    return _setting("neurons_per_vision", 80) if kind == "vision" else _setting("neurons_per_text", 20)


def usage_path():
    d = Path(_env("IMG_META_DIR") or "articles/image-meta")
    return (d if d.is_absolute() else ROOT / d) / "_usage.json"


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def read_today():
    """Today's usage record {date, neurons: {slot: n}, images, history}. A new UTC day starts empty and moves yesterday into history (kept 30 days)."""
    try:
        u = json.loads(usage_path().read_text())
    except (OSError, ValueError):
        u = {}
    u = u if isinstance(u, dict) else {}
    if u.get("date") == _today():
        return u
    history = dict(u.get("history") or {})
    if u.get("date") and (u.get("neurons") or u.get("images")):
        history[u["date"]] = {"neurons": u.get("neurons") or {}, "images": u.get("images", 0)}
    return {"date": _today(), "history": dict(sorted(history.items())[-30:])}


def write(u):
    try:
        usage_path().parent.mkdir(parents=True, exist_ok=True)
        usage_path().write_text(json.dumps(u) + "\n")
    except OSError:
        pass  # a counter that cannot be saved must never stop a picture


def label(account_id):
    """The account's slot as text: "1" for CF_ACCOUNT_ID, "2" for CF_ACCOUNT_ID_2 ... The usage file holds only slot numbers, never an account id."""
    ids = [a[0] for a in load()]
    return str(ids.index(account_id) + 1) if account_id in ids else "0"


def used(account_id):
    """Estimated neurons this account has spent today (UTC)."""
    return int((read_today().get("neurons") or {}).get(label(account_id), 0))


def record(account_id, neurons):
    """Add an estimate to today's counter for this account. Other keys of the usage file (the image-attempt counter, history) are kept."""
    u = read_today()
    u.setdefault("neurons", {})[label(account_id)] = used(account_id) + int(neurons)
    write(u)


def over_budget(account_id):
    return budget() > 0 and used(account_id) >= budget()


# ---- choosing the account ---------------------------------------------------------------------------------------------------------------

def active():
    """The first configured account that is not spent and not over budget, as (id, token), or None."""
    return next((a for a in load() if a[0] not in _spent and not over_budget(a[0])), None)


def none_left_message():
    accounts = load()
    if not accounts:
        return "no Cloudflare account is configured (CF_ACCOUNT_ID / CF_API_TOKEN)"
    if all(a[0] in _spent for a in accounts):
        return "every Cloudflare account has used up its daily free allocation"
    return f"every Cloudflare account has reached its daily budget of {budget()} neurons (IMG_NEURON_BUDGET; 0 turns the budget off)"


def mark_spent(account_id):
    _spent.add(account_id)


def is_quota_error(text):
    return QUOTA_TEXT in (text or "")


def reset():
    _spent.clear()
