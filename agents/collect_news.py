"""Collect celebrity news from RSS feeds into data/leads.json (stdlib only)."""
import html
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

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
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


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


def google_news_url(name, gn):
    q = urllib.parse.quote(f'"{name}" when:{gn["when"]}')
    return (f"https://news.google.com/rss/search?q={q}"
            f"&hl={gn['hl']}&gl={gn['gl']}&ceid={gn['ceid']}")


def mentioned(lead, names):
    text = (lead["title"] + " " + lead["summary"]).lower()
    return [n for n in names if n.lower() in text]


def main():
    cfg = json.loads((ROOT / "config.json").read_text())
    names = cfg["celebrities"]
    limit = cfg["max_items_per_feed"]
    existing = json.loads(LEADS.read_text()) if LEADS.exists() else []
    by_url = {l["url"]: l for l in existing}
    local = datetime.now(ZoneInfo(cfg.get("timezone", "UTC")))
    batch = local.strftime("%Y-%m-%d %H:00")  # one tab per run, labelled in the dashboard timezone

    def add(lead, tags):
        if lead["url"] not in by_url:
            lead["batch"] = batch
            lead["found"] = datetime.now(timezone.utc).isoformat()
        old = by_url.setdefault(lead["url"], lead)
        old["celebrities"] = sorted(set(old.get("celebrities", [])) | set(tags))

    # Per-celebrity Google News search, localised to the chosen country.
    for name in names:
        feed = google_news_url(name, cfg["google_news"])
        try:
            for lead in parse_feed(fetch(feed), "Google News", limit):
                # Google News titles end with " - Publisher"
                title, _, pub = lead["title"].rpartition(" - ")
                if title:
                    lead["title"], lead["source"] = title, pub
                lead["summary"] = ""  # Google News only repeats the headline
                add(lead, [name] + mentioned(lead, names))
            print(f"ok   google news: {name}")
        except Exception as e:  # one broken feed must not stop the run
            print(f"FAIL google news: {name}: {e}", file=sys.stderr)

    # Country-specific entertainment feeds: keep only stories about tracked people.
    for feed in cfg["general_feeds"]:
        source = re.sub(r"^www\.", "", feed.split("/")[2])
        try:
            for lead in parse_feed(fetch(feed), source, limit):
                tags = mentioned(lead, names)
                if tags:
                    add(lead, tags)
            print(f"ok   {feed}")
        except Exception as e:
            print(f"FAIL {feed}: {e}", file=sys.stderr)

    cutoff = datetime.now(timezone.utc) - timedelta(days=cfg["keep_days"])
    leads = []
    for l in by_url.values():
        if not l.get("celebrities") or not any(n in names for n in l["celebrities"]):
            continue  # celebrity was removed from config.json
        l["celebrities"] = [n for n in l["celebrities"] if n in names]
        d = parse_date(l["published"])
        if d and d < cutoff:
            continue
        leads.append(l)
    leads.sort(key=lambda l: l["published"] or "", reverse=True)
    LEADS.parent.mkdir(exist_ok=True)
    LEADS.write_text(json.dumps(leads, indent=2, ensure_ascii=False))
    new = sum(1 for l in leads if l.get("batch") == batch)
    usage = ROOT / "data" / "usage.json"
    u = json.loads(usage.read_text()) if usage.exists() else {}
    month = local.strftime("%Y-%m")
    u[month] = u.get(month, 0) + 1
    u["last_run"] = datetime.now(timezone.utc).isoformat()
    usage.write_text(json.dumps(u, indent=2))
    print(f"{len(leads)} leads saved ({cfg['country']}), {new} new in batch {batch}")


if __name__ == "__main__":
    main()
