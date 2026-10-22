"""Build the link menu for one brief, so the writer links people and the site's own pages without guessing URLs.

usage: link_candidates.py briefs/<batch>/<celebrity>.json  ->  work/<batch>-<celebrity>/links.md  (not committed)
Run it after fetch_sources.py. It reads sources.md (people named in the coverage), checks each name against Wikipedia
(REST summary endpoint, standard library only) and combines that with data/wp_site.json (archives and published posts).
Every URL in links.md was checked or comes from the live site; the writer must not use other URLs for people.
"""
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "researcher-agents/1.0 (https://moduscarry.com; link check)"}
PERSON = re.compile(r"actor|actress|film|director|singer|songwriter|musician|rapper|presenter|comedian|producer|screenwriter|playwright|dramatist|novelist|poet|artist|"
                    r"television|model|dancer|athlete|footballer|swimmer|boxer|businessperson|entrepreneur|journalist|author|writer|personality|"
                    r"socialite|influencer|chef|politician", re.I)
NAME = re.compile(r"\b([A-Z][a-z]+(?:['’-][A-Z]?[a-z]+)?(?:\s+(?:[A-Z]\.|de|van|von|Mc[A-Z][a-z]+|Mac[A-Z][a-z]+|[A-Z][a-z]+(?:['’-][A-Z]?[a-z]+)?)){1,2})\b")
SKIP_WORDS = {"The", "This", "That", "These", "Those", "Sony", "Pictures", "Studios", "Hollywood", "Reporter", "Variety", "Deadline", "Collider",
              "Daily", "Telegraph", "News", "Network", "Netflix", "Disney", "Warner", "Bros", "Universal", "Paramount", "Fashion", "Week", "Show",
              "Australia", "Australian", "Sydney", "Melbourne", "Instagram", "Facebook", "Google", "Read", "Source", "Sources", "Story", "Quick",
              "According", "Related", "Image", "Photo", "Getty", "Images", "Amazon", "Prime", "Video", "Apple", "HBO", "Max", "Box", "Office",
              "Academy", "Awards", "Oscars", "Emmy", "Emmys", "Globes", "Golden", "Festival", "Film", "Movie", "Cinema", "Street", "Island",
              "Jump", "Dog", "Stars", "Death", "Robin", "Hood", "Long", "John", "Silver", "Treasure"}


def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def _summary(title):
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title.replace(' ', '_'), safe='()')}?redirect=true"
    for wait in (0, 1.5, 4):
        time.sleep(wait)
        try:
            return get_json(url)
        except urllib.error.HTTPError as e:
            if e.code != 429:
                return None
        except (urllib.error.URLError, ValueError, TimeoutError):
            return None
    return None


def wiki(name):
    """Return {title, url, description} when `name` is a Wikipedia article about a person, else None.
    Tries the plain name, then the usual disambiguated titles (actor, actress, director, writer, ...)."""
    for title in (name, f"{name} (actor)", f"{name} (actress)", f"{name} (director)", f"{name} (screenwriter)", f"{name} (writer)", f"{name} (producer)", f"{name} (musician)"):
        d = _summary(title)
        if not d:
            continue
        desc = d.get("description") or ""
        if d.get("type") == "standard" and PERSON.search(desc + " " + (d.get("extract") or "")[:200]):
            return {"title": d.get("title", name), "url": d["content_urls"]["desktop"]["page"], "description": desc}
    return None


def candidate_names(brief, sources_text, celeb):
    text = " ".join(s["title"] for s in brief["stories"]) + "\n" + sources_text
    seen, out = set(), []
    for m in NAME.finditer(text):
        n = m.group(1).strip()
        words = n.split()
        if n == celeb or len(words) < 2 or any(w in SKIP_WORDS for w in words) or n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out[:30]


def score(post, terms):
    hay = post["title"].lower()
    return sum(1 for t in terms if t and t in hay)


def main():
    brief_path = ROOT / sys.argv[1]
    brief = json.loads(brief_path.read_text())
    celeb = brief["celebrity"]
    out_dir = ROOT / "work" / f"{brief_path.parent.name}-{brief_path.stem}"
    out_dir.mkdir(parents=True, exist_ok=True)
    src = out_dir / "sources.md"
    sources_text = src.read_text() if src.exists() else ""
    cfg = json.loads((ROOT / "config.json").read_text())
    prof = (cfg.get("profiles") or {}).get(celeb, {})
    site_file = ROOT / "data" / "wp_site.json"
    site = json.loads(site_file.read_text()) if site_file.exists() else {}
    base = (cfg.get("site") or {}).get("url", "").rstrip("/")

    lines = [f"# Link menu for {celeb} (batch {brief['batch']})", "",
             "Use ONLY these URLs for people and for the site's own pages. Verified when this file was built. Never invent a URL.", "",
             "## External links to people (link each person once, at their first mention)", ""]
    main_wiki = wiki(celeb)
    lines.append(f"- **{celeb}** (the subject of this article): " + (f"[Wikipedia]({main_wiki['url']})" if main_wiki else "(no Wikipedia match; use the official site below)"))
    for label, key in (("official website", "website"), ("Instagram", "instagram"), ("X", "x"), ("Facebook", "facebook"), ("YouTube", "youtube")):
        if prof.get(key):
            lines.append(f"  - {label}: {prof[key]}")
    others = []
    for n in candidate_names(brief, sources_text, celeb):
        time.sleep(0.15)
        w = wiki(n)
        if w and w["title"] != celeb:
            others.append((n, w))
    for n, w in others:
        lines.append(f"- **{n}** ({w['description'] or 'person'}): [Wikipedia]({w['url']})")
    if not others:
        lines.append("- (no other people with a Wikipedia article were detected in the coverage)")

    lines += ["", "## Internal links (the site's own pages; use 2 to 4, with descriptive anchor text)", ""]
    terms = [celeb.lower()] + [t.lower() for t in celeb.split()]
    tags = {t["name"].lower(): t for t in site.get("tags", [])}
    cats = {c["name"].lower(): c for c in site.get("categories", [])}
    found = False
    t = tags.get(celeb.lower())
    if t and t.get("link") and t.get("count", 0) > 0:
        lines.append(f"- Everything we publish about {celeb}: [{celeb}]({t['link']}) (tag archive)")
        found = True
    for c in site.get("categories", []):
        if c.get("link") and c.get("count", 0) > 0 and c["name"].lower() in ("movies", "celebrities", "tv & dramas", "fashion", "music"):
            lines.append(f"- Category page: [{c['name']}]({c['link']})")
            found = True
    posts = sorted(site.get("recent_posts", []), key=lambda p: -score(p, terms))
    related = [p for p in posts if score(p, terms) > 0 and not p["title"].lower().startswith("sample")][:5]
    for p in related:
        lines.append(f"- Related post: [{p['title']}]({p['link']})")
        found = True
    if base:
        lines.append(f"- Home page: [{(cfg.get('site') or {}).get('name') or 'Home'}]({base}/)")
        found = True
    if not found:
        lines.append("- (no site pages available yet; skip internal links)")
    (out_dir / "links.md").write_text("\n".join(lines) + "\n")
    print(f"wrote {out_dir / 'links.md'} ({len(others)} other people, {len(related)} related posts)")


if __name__ == "__main__":
    main()
