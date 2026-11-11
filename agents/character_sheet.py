"""Builds data/character-sheet.json: the pool of open-licence Wikimedia Commons photos of every celebrity (links only; nothing is downloaded here).

generate_images.py draws a post's featured image from this pool. Discovery, licence rules and ranking live in commons_photos.py: the person's main Commons
category plus their year/event sub-categories, CC0 / public domain / CC BY / CC BY-SA only, a 1920 px copy so pictures are not stretched, best ones first.

Run: python3 agents/character_sheet.py [--only "Chris Hemsworth"] [--refresh] [--max N]
  - resumable: people already done with the current method are skipped; older entries are redone; "no free photo" is re-checked after 30 days
  - --max N does at most N people per run (Wikimedia throttles automated clients, so a run stops early and the next run continues)
  - --refresh redoes everyone
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import commons_photos  # noqa: E402
import openverse_photos  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "character-sheet.json"
RECHECK_DAYS = 30


def due(entry):
    """Does this person need (re)searching? Missing, built by the old method, or 'no free photo' found more than RECHECK_DAYS ago."""
    if not entry or entry.get("v") != commons_photos.VERSION:
        return True
    if entry.get("ov") != openverse_photos.VERSION and len([p for p in entry.get("photos") or [] if p.get("source") != "openverse"]) < openverse_photos.ENOUGH:
        return True  # Commons gave this person (almost) nothing and Openverse has not been searched yet
    if entry.get("status") == "ok":
        return False
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(entry["checked"])).days >= RECHECK_DAYS
    except (KeyError, ValueError):
        return True


def save(sheet):
    PATH.parent.mkdir(exist_ok=True)
    PATH.write_text(json.dumps(sheet, indent=1, ensure_ascii=False) + "\n")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cfg = json.loads((ROOT / "config.json").read_text())
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    limit = int(argv[argv.index("--max") + 1]) if "--max" in argv else 10**6
    sheet = json.loads(PATH.read_text()) if PATH.exists() else {}
    done = 0
    for name in cfg["celebrities"]:
        if only and name != only:
            continue
        if not (due(sheet.get(name)) or "--refresh" in argv):
            continue
        if done >= limit:
            print("run limit reached; the next run continues")
            break
        old = sheet.get(name)
        try:
            if old and old.get("v") == commons_photos.VERSION and "--refresh" not in argv and old.get("ov") != openverse_photos.VERSION:
                entry = dict(old)  # Commons part is current; only the Openverse step is missing
            else:
                entry = commons_photos.refresh(name)
            commons_n = len(entry["photos"])
            if commons_n < openverse_photos.ENOUGH:
                extra = openverse_photos.refresh(name)
                entry["photos"] = [p for p in entry["photos"] if p.get("source") != "openverse"] + extra
                if entry["photos"]:
                    entry["status"] = "ok"
            entry["ov"] = openverse_photos.VERSION
        except commons_photos.FaceCheckUnavailable as e:
            print(f"STOP: {e}", file=sys.stderr)
            return 1
        except commons_photos.CommonsError as e:  # a throttled request is not "no photo": keep what we had and stop politely
            print(f"throttled at {name}: {e}; the next run continues", flush=True)
            break
        entry["checked"] = datetime.now(timezone.utc).isoformat()
        sheet[name] = entry
        done += 1
        top = entry["photos"][0] if entry["photos"] else None
        print(f"{entry['status']:14} {name}: {len(entry['photos'])} photos ({sum(1 for p in entry['photos'] if p.get('source') == 'openverse')} from Openverse; {entry.get('examined', '?')} Commons files examined)" + (f" (best: {top['file']} | {top['license']} | {top['date']} | {top['width']}x{top['height']})" if top else ""), flush=True)
        save(sheet)
    save(sheet)
    have = sum(1 for n in cfg["celebrities"] if (sheet.get(n) or {}).get("photos"))
    print(f"{have} of {len(cfg['celebrities'])} celebrities have at least one free photo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
