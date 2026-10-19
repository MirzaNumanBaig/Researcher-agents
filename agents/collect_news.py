"""Collect celebrity news from RSS feeds into data/leads.json (stdlib only)."""
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEADS = ROOT / "data" / "leads.json"
UA = "Mozilla/5.0 (compatible; Researcher-agents/1.0)"
ATOM = "{http://www.w3.org/2005/Atom}"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def parse_date(text):
    if not text:
        return None
    try:
        d = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def strip_html(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def parse_feed(data, source, limit):
    root = ET.fromstring(data)
    out = []
    for it in (root.iter("item") or []):
        out.append((it.findtext("title"), it.findtext("link"),
                    it.findtext("pubDate"), it.findtext("description")))
    for it in root.iter(ATOM + "entry"):
        link = it.find(ATOM + "link")
        out.append((it.findtext(ATOM + "title"),
                    link.get("href") if link is not None else None,
                    it.findtext(ATOM + "updated"), it.findtext(ATOM + "summary")))
    leads = []
    for title, link, date, desc in out[:limit]:
        d = parse_date(date)
        if title and link:
            leads.append({
                "title": strip_html(title), "url": link.strip(), "source": source,
                "published": d.isoformat() if d else None,
                "summary": strip_html(desc)[:300],
            })
    return leads


def main():
    cfg = json.loads((ROOT / "config.json").read_text())
    existing = json.loads(LEADS.read_text()) if LEADS.exists() else []
    by_url = {l["url"]: l for l in existing}
    for feed in cfg["rss_feeds"]:
        source = re.sub(r"^www\.", "", feed.split("/")[2])
        try:
            for lead in parse_feed(fetch(feed), source, cfg["max_items_per_feed"]):
                by_url.setdefault(lead["url"], lead)
            print(f"ok   {feed}")
        except Exception as e:  # one broken feed must not stop the run
            print(f"FAIL {feed}: {e}", file=sys.stderr)
    kw = [k.lower() for k in cfg.get("keywords", [])]
    cutoff = datetime.now(timezone.utc) - timedelta(days=cfg["keep_days"])
    leads = []
    for l in by_url.values():
        if kw and not any(k in (l["title"] + l["summary"]).lower() for k in kw):
            continue
        d = parse_date(l["published"])
        if d and d < cutoff:
            continue
        leads.append(l)
    leads.sort(key=lambda l: l["published"] or "", reverse=True)
    LEADS.parent.mkdir(exist_ok=True)
    LEADS.write_text(json.dumps(leads, indent=2, ensure_ascii=False))
    print(f"{len(leads)} leads saved")


if __name__ == "__main__":
    main()
