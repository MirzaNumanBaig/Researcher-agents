"""Step 2b: the stand-in cast. Every person in an image is one of a few FICTIONAL characters from cast.json, never a real person.
A stand-in is matched to the blueprint person by gender presentation, age range and clothing style, and the least recently used card wins, so the site shows
varied but consistent people. The prompt only ever gets the description (age, hair, skin, build, clothes), never a name or a "looks like"."""
import json
import re
from collections import Counter
from pathlib import Path

from . import config


def load():
    path = Path(config.get("cast_file"))
    path = path if path.is_absolute() else config.ROOT / path
    try:
        cards = json.loads(path.read_text()).get("cast", [])
    except (OSError, ValueError):
        cards = []
    return [c for c in cards if isinstance(c, dict) and c.get("id") and c.get("presentation")]


def _decade(age):
    m = re.search(r"(\d)0s", age or "")
    return int(m.group(1)) * 10 + {"early": 2, "mid": 5, "late": 8}.get(next((w for w in ("early", "mid", "late") if w in (age or "")), ""), 5) if m else None


def _age_gap(card, wanted):
    a, b = _decade(card.get("age")), _decade(wanted)
    return 0 if a is None or b is None else abs(a - b)


def _style(card, hint, key):
    """The card's clothing style closest to the blueprint's clothing words, else a stable pick."""
    styles = card.get("styles") or ["plain everyday clothes"]
    words = set(re.findall(r"[a-z]{4,}", (hint or "").lower()))
    scored = [(len(words & set(re.findall(r"[a-z]{4,}", s.lower()))), s) for s in styles]
    best = max(s for s, _ in scored)
    if best:
        return next(s for n, s in scored if n == best)
    return styles[sum(map(ord, key)) % len(styles)]


def describe(card):
    """'a woman in her early 30s with shoulder-length wavy chestnut hair and light olive skin'. No clothes (they come later in the prompt), no build, no name, ever."""
    age = f" in {'her' if card['presentation'] == 'woman' else 'his'} {card['age']}" if card.get("age") else ""
    traits = [x for x in (card.get("hair"), card.get("skin")) if x]
    return f"a {card['presentation']}{age}" + (f" with {' and '.join(traits)}" if traits else "")


def assign(blueprint, history=(), key=""):
    """One stand-in per blueprint person: [{id, presentation, descriptor, label}]. Least recently used first, never the same card twice in one image."""
    people = blueprint.get("people") or []
    cast = load()
    if not people or not cast:
        return []
    recent = Counter(i for h in list(history)[-config.get("history_size"):] for i in h.get("cast", []))
    chosen, out = set(), []
    for n, person in enumerate(people):
        pres = person.get("gender_presentation")
        pool = [c for c in cast if c["id"] not in chosen and (pres in ("woman", "man") and c["presentation"] == pres or pres not in ("woman", "man"))] or \
               [c for c in cast if c["id"] not in chosen] or cast
        ranked = sorted(pool, key=lambda c: (_age_gap(c, person.get("age_range")) // 5, recent[c["id"]], sum(map(ord, key + c["id"])) % 7))
        card = ranked[0]
        chosen.add(card["id"])
        style = _style(card, person.get("clothing"), key + card["id"])
        out.append({"id": card["id"], "presentation": card["presentation"], "descriptor": describe(card), "style": style})
    if len(out) == 2 and out[0]["presentation"] == out[1]["presentation"]:  # "the first woman / the second woman" reads clumsily, so label by position
        out[0]["label"], out[1]["label"] = f"The first {out[0]['presentation']}", f"The second {out[1]['presentation']}"
    for o in out:
        o.setdefault("label", f"The {o['presentation']}")
    return out
