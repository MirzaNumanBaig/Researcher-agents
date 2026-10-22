"""Check a freshly written article against the house rules and print warnings (never blocks the pipeline).

usage: check_article.py articles/<file>.md [more files...]
Checks: front matter, Quick summary first, word count (600-800 target, 450 floor), FAQ, sources, external link for the subject,
internal links, no em dashes. Prints ::warning:: lines that show up in the GitHub Actions log.
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent


def check(path):
    text = Path(path).read_text()
    if not text.startswith("---"):
        return ["no front matter"]
    front, _, body = text[3:].partition("\n---")
    if re.search(r"^status: ?skipped", front, re.M):
        return []
    cfg = json.loads((ROOT / "config.json").read_text())
    site_host = urlparse((cfg.get("site") or {}).get("url", "")).netloc
    celeb = (re.search(r'^celebrity: ?"?(.*?)"?\s*$', front, re.M) or [None, ""])[1]
    problems = []
    main = body.split("## Sources")[0]
    words = len(re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", main).split())
    if words < 450:
        problems.append(f"only {words} words (target 600-800, never under 450)")
    elif words < 600 or words > 800:
        problems.append(f"{words} words (target 600-800)")
    if not body.lstrip().startswith("**Quick summary**"):
        problems.append("body does not open with the Quick summary")
    if "## Frequently asked questions" not in body:
        problems.append("no FAQ section")
    if "## Sources" not in body:
        problems.append("no Sources section")
    links = re.findall(r"\[[^\]]+\]\((https?://[^)\s]+)\)", main)
    internal = [u for u in links if site_host and urlparse(u).netloc == site_host]
    external = [u for u in links if u not in internal]
    own_site = urlparse(((cfg.get("profiles") or {}).get(celeb) or {}).get("website", "")).netloc
    slug = celeb.replace(" ", "_").lower()
    person_links = [u for u in external if ("wikipedia.org/wiki/" in u and slug in u.lower()) or "imdb.com/name/" in u or (own_site and own_site in u)]
    if celeb and not person_links:
        problems.append(f"no external link to {celeb} (Wikipedia, official site or similar)")
    if len(internal) < 1:
        problems.append("no internal links to the site")
    elif len(internal) > 5:
        problems.append(f"{len(internal)} internal links (use 2 to 4)")
    if "—" in body:
        problems.append("contains em dashes")
    return problems


def main():
    bad = 0
    for p in sys.argv[1:]:
        issues = check(p)
        for i in issues:
            print(f"::warning file={p}::{i}")
        bad += bool(issues)
        print(f"{p}: {'OK' if not issues else str(len(issues)) + ' issue(s)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
