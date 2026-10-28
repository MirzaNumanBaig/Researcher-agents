"""Per-article metadata (article id, story type, final prompt, seed, model, timestamp, quality result) and the recent-prompt history used to vary images."""
import json
from datetime import datetime, timezone
from pathlib import Path

from . import config


def meta_dir():
    d = Path(config.get("meta_dir"))
    return d if d.is_absolute() else config.ROOT / d


def save(key, data):
    d = meta_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{key}.json"
    path.write_text(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), **data}, indent=2, ensure_ascii=False) + "\n")
    return path


def load_history():
    try:
        return json.loads((meta_dir() / "_history.json").read_text())
    except (OSError, ValueError):
        return []


def add_history(entry):
    hist = (load_history() + [entry])[-config.get("history_size"):]
    meta_dir().mkdir(parents=True, exist_ok=True)
    (meta_dir() / "_history.json").write_text(json.dumps(hist, indent=1, ensure_ascii=False) + "\n")
    return hist
