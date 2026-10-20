"""Send approved drafts in articles/ to WordPress through its REST API (standard library only).

Env (GitHub Actions secrets): WP_URL (https://moduscarry.com), WP_USER, WP_APP_PASSWORD.
Front matter per article:  status: pending|approved|rejected|sent   wp_status: draft|pending|publish|private
 - approved + no wp_id  -> create the post with wp_status, then status: sent, wp_id, wp_link, wp_synced.
 - sent + wp_status != wp_synced -> update the existing post's status (e.g. draft -> publish).
Nothing is ever sent unless a human (or an approved MCP call) set status: approved.
"""
import base64
import html
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WP_STATUSES = {"draft", "pending", "publish", "private"}
URL, USER, PW = (os.environ.get(k, "").rstrip("/") for k in ("WP_URL", "WP_USER", "WP_APP_PASSWORD"))


def split(text):
    m = re.match(r"---\n(.*?)\n---\n\n?(.*)", text, re.S)
    return (m.group(1), m.group(2)) if m else ("", text)


def field(front, key):
    m = re.search(rf"^{key}: ?(.*)$", front, re.M)
    if not m:
        return ""
    v = m.group(1).strip()
    return json.loads(v) if v.startswith('"') else v


def set_field(front, key, value):
    line = f"{key}: {json.dumps(value) if key in ('title', 'wp_link') else value}"
    if re.search(rf"^{key}: ?.*$", front, re.M):
        return re.sub(rf"^{key}: ?.*$", lambda _: line, front, count=1, flags=re.M)
    return front + "\n" + line


def inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" rel="noopener">\1</a>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    return re.sub(r"(?<!\*)\*(?!\*)(.+?)\*", r"<em>\1</em>", t)


def to_html(md):
    out, para, items = [], [], []

    def flush():
        nonlocal para, items
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")
        if items:
            out.append("<ul>" + "".join(f"<li>{inline(i)}</li>" for i in items) + "</ul>")
        para, items = [], []

    for line in md.splitlines():
        h = re.match(r"(#{1,4})\s+(.*)", line)
        if h:
            flush()
            lvl = max(2, len(h.group(1)))  # WordPress supplies the h1 (post title)
            out.append(f"<h{lvl}>{inline(h.group(2))}</h{lvl}>")
        elif re.match(r"\s*[-*]\s+", line):
            if para:
                flush()
            items.append(re.sub(r"^\s*[-*]\s+", "", line))
        elif not line.strip():
            flush()
        else:
            if items:
                flush()
            para.append(line.strip())
    flush()
    return "\n".join(out)


def wp(path, payload):
    req = urllib.request.Request(
        f"{URL}/wp-json/wp/v2/{path}", data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "researcher-agents",
                 "Authorization": "Basic " + base64.b64encode(f"{USER}:{PW}".encode()).decode()})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def main():
    if not (URL and USER and PW):
        print("WP_URL / WP_USER / WP_APP_PASSWORD not set; nothing sent.")
        return
    failed = False
    for f in sorted((ROOT / "articles").glob("*.md")):
        front, body = split(f.read_text())
        status, want = field(front, "status"), field(front, "wp_status") or "draft"
        if want not in WP_STATUSES:
            print(f"skip {f.name}: bad wp_status {want!r}")
            continue
        try:
            if status == "approved" and not field(front, "wp_id"):
                post = wp("posts", {"title": field(front, "title"), "content": to_html(body), "status": want})
                front = set_field(front, "status", "sent")
            elif status == "sent" and field(front, "wp_id") and want != field(front, "wp_synced"):
                post = wp(f"posts/{field(front, 'wp_id')}", {"status": want})
            else:
                continue
            front = set_field(set_field(set_field(front, "wp_id", post["id"]), "wp_link", post["link"]), "wp_synced", want)
            f.write_text(f"---\n{front}\n---\n\n{body}")
            print(f"ok {f.name} -> WordPress #{post['id']} ({want})")
        except Exception as e:  # keep going; failed files stay approved and retry on the next run
            failed = True
            print(f"FAIL {f.name}: {e}", file=sys.stderr)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
