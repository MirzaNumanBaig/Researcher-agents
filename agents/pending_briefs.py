"""Print the article queue as JSON (for the GitHub Actions matrix): briefs in the latest batches with no article yet.

config.json: article_batches_back (default 2), max_articles_per_run (default 8), wp_default_status (default "pending").
An article file of any status (including skipped/rejected) counts as done, so nothing is written twice,
except `status: rewrite` (set by the dashboard's Rewrite button): those are queued first, from any batch.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def main():
    cfg = json.loads((ROOT / "config.json").read_text())
    batches = sorted((p for p in (ROOT / "briefs").glob("*") if p.is_dir()), reverse=True)[: cfg.get("article_batches_back", 2)]
    queue, seen = [], set()

    def add(batch_dir, brief, article):
        data = json.loads(brief.read_text())
        queue.append({"brief": str(brief.relative_to(ROOT)), "article": article, "batch": data["batch"],
                      "celebrity": data["celebrity"], "sources": f"work/{batch_dir.name}-{brief.stem}/sources.md", "links": f"work/{batch_dir.name}-{brief.stem}/links.md",
                      "wp_status": cfg.get("wp_default_status", "pending")})
        seen.add(article)

    for f in sorted((ROOT / "articles").glob("*.md"), reverse=True):
        if re.search(r"^status: ?rewrite\s*$", f.read_text().split("\n---", 1)[0], re.M):
            for batch_dir in (p for p in (ROOT / "briefs").glob("*") if p.is_dir()):
                brief = batch_dir / (f.stem[len(batch_dir.name) + 1:] + ".json")
                if f.stem.startswith(batch_dir.name + "-") and brief.exists():
                    add(batch_dir, brief, f"articles/{f.name}")
                    break
    for batch_dir in batches:
        for brief in sorted(batch_dir.glob("*.json")):
            article = f"articles/{batch_dir.name}-{brief.stem}.md"
            if article in seen or (ROOT / article).exists():
                continue
            add(batch_dir, brief, article)
    print(json.dumps(queue[: cfg.get("max_articles_per_run", 8)]))


if __name__ == "__main__":
    main()
