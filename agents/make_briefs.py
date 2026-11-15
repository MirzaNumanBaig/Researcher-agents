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


def film_facts(celeb, films):
    """Recorded facts (data/movies.json) about the film itself, or about the films this person is in, directs or produces: the writer may use them."""
    out = []
    for f in films:
        people = set(f.get("director", [])) | set(f.get("cast", [])) | set(f.get("producers", []))
        if f["title"].lower() == celeb.lower() or celeb in people:
            c = f.get("critics") or {}
            out.append({"title": f["title"], "release": f["release"], "director": f.get("director", []), "cast": f.get("cast", [])[:5],
                        "budget_usd": f.get("budget"), "box_office_usd": f.get("gross"), "scope": f.get("scale"), "verdict": f.get("verdict"),
                        "gross_vs_budget": f.get("multiple"), "rotten_tomatoes": c.get("rotten_tomatoes"), "metacritic": c.get("metacritic"),
                        "critics_consensus": c.get("consensus"), "critics_overview": c.get("overview"), "sources": f.get("sources", {})})
    return out[:4]


def main():
    mf = ROOT / "data" / "movies.json"
    films = json.loads(mf.read_text()).get("films", []) if mf.exists() else []
    stories = json.loads((ROOT / "data" / "stories.json").read_text())
    made = 0
    for s in stories:
        if s["batch"] == "Earlier":
            continue
        for celeb in s["celebrities"]:
            path = ROOT / "briefs" / slug(s["batch"]) / f"{slug(celeb)}.json"
            brief = json.loads(path.read_text()) if path.exists() else {"batch": s["batch"], "celebrity": celeb, "stories": []}
            facts = film_facts(celeb, films)
            if facts:
                brief["film_facts"] = facts  # budget, box office, scope and critics' view for the writer
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
