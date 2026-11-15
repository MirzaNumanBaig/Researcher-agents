"""What the system follows: people (config.json "celebrities") and films (config.json "movies"), plus when each was added by the
discovery step (config.json "added": {name: "YYYY-MM-DD"}), which the dashboard shows as a "New" tag for NEW_DAYS days."""
import json
import re
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.json"
NEW_DAYS = 7


def load():
    return json.loads(CONFIG.read_text())


def save(cfg):
    text = json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"
    # embed_accounts was hand-written on one line; keep it so (everything else stays as json.dumps lays it out)
    text = re.sub(r'("embed_accounts": )\[\n\s+("[^"\n]*"(?:,\n\s+"[^"\n]*")*)\n\s+\]', lambda m: m.group(1) + "[" + re.sub(r",\n\s+", ", ", m.group(2)) + "]", text)
    CONFIG.write_text(text)


def topics(cfg):
    """Everything the collector searches for: people first, then films."""
    return list(cfg["celebrities"]) + [m for m in cfg.get("movies", []) if m not in cfg["celebrities"]]


def is_new(cfg, name, today=None):
    d = (cfg.get("added") or {}).get(name)
    try:
        return bool(d) and (today or date.today()) - date.fromisoformat(d) <= timedelta(days=NEW_DAYS)
    except ValueError:
        return False
