"""Several Cloudflare accounts for image generation (standard library only, shared by generate_images.py and imagegen/).
Secrets: CF_ACCOUNT_ID + CF_API_TOKEN (the first account), then CF_ACCOUNT_ID_2 + CF_API_TOKEN_2, ... up to _9. Only complete pairs count.
The first account that still has free neurons is used. When Cloudflare answers "you have used up your daily free allocation", that account is
marked spent for the rest of this run and the next one takes over. Text, vision and image calls share one pool, because they spend the same neurons."""
import os

QUOTA_TEXT = "daily free allocation"
_spent = set()


def _env(name):
    return os.environ.get(name, "").strip()


def load():
    """[(account id, token)] in order, skipping incomplete pairs and duplicates."""
    out = []
    for suffix in [""] + [f"_{n}" for n in range(2, 10)]:
        pair = (_env("CF_ACCOUNT_ID" + suffix), _env("CF_API_TOKEN" + suffix))
        if all(pair) and pair not in out:
            out.append(pair)
    return out


def active():
    """The first configured account that is not spent, as (id, token), or None."""
    return next((a for a in load() if a[0] not in _spent), None)


def mark_spent(account_id):
    _spent.add(account_id)


def is_quota_error(text):
    return QUOTA_TEXT in (text or "")


def count():
    return len(load())


def reset():
    _spent.clear()
