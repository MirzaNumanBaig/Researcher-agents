"""Write one brief per (batch, celebrity) for Claude to turn into a blog article.

briefs/<batch>/<celebrity>.json lists that run's stories about the celebrity with every outlet link.
Existing briefs are never overwritten; the "Earlier" backlog is skipped.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def main():
    stories = json.loads((ROOT / "data" / "stories.json").read_text())
    made = 0
    for s in stories:
        if s["batch"] == "Earlier":
            continue
        for celeb in s["celebrities"]:
            path = ROOT / "briefs" / slug(s["batch"]) / f"{slug(celeb)}.json"
            brief = json.loads(path.read_text()) if path.exists() else {"batch": s["batch"], "celebrity": celeb, "stories": []}
            have = next((x for x in brief["stories"] if x["url"] == s["url"]), None)
            if have:
                if s.get("image") and not have.get("image"):  # image links found after the brief was first written
                    have.update(image=s["image"], image_source=s["image_source"], outlets=s["outlets"])
                    path.write_text(json.dumps(brief, indent=2, ensure_ascii=False))
                continue
            brief["stories"].append({k: s.get(k, "") for k in ("title", "url", "published", "outlets", "image", "image_source")})
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(brief, indent=2, ensure_ascii=False))
            made += 1
    print(f"{made} story entries added to briefs")


if __name__ == "__main__":
    main()
