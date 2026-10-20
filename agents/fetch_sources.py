"""Download the readable text of the pages behind one brief, so ANY AI (Claude, Codex, other) can write from it offline.

usage: fetch_sources.py briefs/<batch>/<celebrity>.json  ->  work/<batch>-<celebrity>/sources.md  (not committed)
Google News links are resolved to the real article first. Text is for reading/fact-checking only and is never published or stored in git.
"""
import base64
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36", "Cookie": "CONSENT=YES+cb"}
MAX_STORIES, MAX_OUTLETS, MAX_CHARS = 6, 3, 5000
MIN_CHARS = 300  # shorter than this is a cookie banner or a paywall stub, not an article


def get(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "replace")


def embedded_url(gid):
    """Old-style Google News ids carry the publisher URL inside the base64 payload."""
    try:
        raw = base64.urlsafe_b64decode(gid + "=" * (-len(gid) % 4))
    except ValueError:
        return None
    m = re.search(rb"https?://[\x21-\x7e]+", raw)
    return m.group(0).decode() if m else None


def resolve(url):
    """Resolve a news.google.com/rss/articles/... link to the publisher's URL."""
    if "news.google.com/rss/articles/" not in url:
        return url
    gid = urllib.parse.urlparse(url).path.rstrip("/").split("/")[-1]
    direct = embedded_url(gid)
    if direct:
        return direct
    last = None
    for attempt in range(3):
        try:
            return batchexecute(gid)
        except Exception as e:  # Google rate-limits or changes this call; retry, then report why
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"could not resolve the Google News link ({last})")


def batchexecute(gid):
    page = get(f"https://news.google.com/rss/articles/{gid}")
    sg, ts = re.search(r'data-n-a-sg="([^"]+)"', page), re.search(r'data-n-a-ts="([^"]+)"', page)
    if not (sg and ts):
        raise RuntimeError("Google returned no signature (consent page or block)")
    inner = json.dumps(["garturlreq", [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None, None, None, 0, 1],
                                       "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0], gid, int(ts.group(1)), sg.group(1)])
    body = "f.req=" + urllib.parse.quote(json.dumps([[["Fbv4je", inner, None, "generic"]]]))
    out = get("https://news.google.com/_/DotsSplashUi/data/batchexecute", body.encode(),
              {"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"})
    m = re.search(r'\\"garturlres\\",\\"(.*?)\\"', out)
    if not m:
        raise RuntimeError("no publisher URL in response")
    url = json.loads('"' + m.group(1) + '"')
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda x: chr(int(x.group(1), 16)), url)


class Text(HTMLParser):
    SKIP = {"script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg"}

    def __init__(self):
        super().__init__()
        self.skip = 0
        self.in_p = False
        self.title = ""
        self.in_title = False
        self.paras = []
        self.cur = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag == "title":
            self.in_title = True
        elif tag in ("p", "h1", "h2", "li") and not self.skip:
            self.in_p, self.cur = True, []

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag == "title":
            self.in_title = False
        elif tag in ("p", "h1", "h2", "li") and self.in_p:
            text = " ".join("".join(self.cur).split())
            if len(text) > 40:
                self.paras.append(text)
            self.in_p = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        elif self.in_p and not self.skip:
            self.cur.append(data)


def read_page(url):
    real = resolve(url)
    p = Text()
    p.feed(get(real))
    text = "\n\n".join(dict.fromkeys(p.paras))[:MAX_CHARS]
    return real, " ".join(html.unescape(p.title).split()), text


def main():
    brief_path = ROOT / sys.argv[1]
    brief = json.loads(brief_path.read_text())
    out_dir = ROOT / "work" / f"{brief_path.parent.name}-{brief_path.stem}"
    out_dir.mkdir(parents=True, exist_ok=True)
    parts, readable, tried = [], 0, 0
    for i, story in enumerate(brief["stories"][:MAX_STORIES], 1):
        parts.append(f"\n## Story {i}: {story['title']}\n")
        for o in story["outlets"][:MAX_OUTLETS]:
            tried += 1
            try:
                real, title, text = read_page(o["url"])
                if len(text) >= MIN_CHARS:
                    readable += 1
                    parts.append(f"\n### {o['source']}: {title}\nURL: {real}\n\n{text}\n")
                else:
                    parts.append(f"\n### {o['source']}\nURL: {real}\n(not usable: {'no readable text, likely paywalled or script-rendered' if not text else 'only a short stub'})\n")
            except Exception as e:
                parts.append(f"\n### {o['source']}\n(could not fetch: {e})\n")
    head = [f"# Source texts for {brief['celebrity']} (batch {brief['batch']})\n",
            f"Readable sources: {readable} of {tried}.\n",
            "Read-only research material fetched automatically. Never copy sentences from it.\n"]
    if not readable:
        head.append("**NO READABLE SOURCE TEXT.** Do not write from the headlines alone. Try the story links with your web tools; if you still cannot "
                    "read at least one real article, write the file with `status: skipped` and `skip_reason: no readable source text`.\n")
        print(f"::warning::No readable source text for {brief['celebrity']} ({brief['batch']}): {tried} outlet(s) tried")
    (out_dir / "sources.md").write_text("\n".join(head + parts))
    print(f"wrote {out_dir / 'sources.md'} ({readable}/{tried} readable)")


if __name__ == "__main__":
    main()
