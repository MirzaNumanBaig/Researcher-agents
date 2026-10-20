"""Download the readable text of the pages behind one brief, so ANY AI (Claude, Codex, other) can write from it offline.

usage: fetch_sources.py briefs/<batch>/<celebrity>.json  ->  work/<batch>-<celebrity>/sources.md  (not committed)
Google News links are resolved to the real article first. Text is for reading/fact-checking only and is never published or stored in git.
"""
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36", "Cookie": "CONSENT=YES+cb"}
MAX_STORIES, MAX_OUTLETS, MAX_CHARS = 6, 3, 5000


def get(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "replace")


def resolve(url):
    """Resolve a news.google.com/rss/articles/... link to the publisher's URL."""
    if "news.google.com/rss/articles/" not in url:
        return url
    gid = urllib.parse.urlparse(url).path.rstrip("/").split("/")[-1]
    page = get(f"https://news.google.com/rss/articles/{gid}")
    sg, ts = re.search(r'data-n-a-sg="([^"]+)"', page), re.search(r'data-n-a-ts="([^"]+)"', page)
    if not (sg and ts):
        raise RuntimeError("could not resolve Google News link")
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
    parts = [f"# Source texts for {brief['celebrity']} (batch {brief['batch']})\n",
             "Read-only research material fetched automatically. Never copy sentences from it.\n"]
    for i, story in enumerate(brief["stories"][:MAX_STORIES], 1):
        parts.append(f"\n## Story {i}: {story['title']}\n")
        for o in story["outlets"][:MAX_OUTLETS]:
            try:
                real, title, text = read_page(o["url"])
                parts.append(f"\n### {o['source']}: {title}\nURL: {real}\n\n{text or '(no readable text; likely paywalled or script-rendered)'}\n")
            except Exception as e:
                parts.append(f"\n### {o['source']}\n(could not fetch: {e})\n")
    (out_dir / "sources.md").write_text("\n".join(parts))
    print(f"wrote {out_dir / 'sources.md'}")


if __name__ == "__main__":
    main()
