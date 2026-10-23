"""One-off cleanup: delete every blog post on the WordPress site and the images that belong to those posts.

usage: clean_wordpress.py [--delete] [--permanent]
Env: WP_URL, WP_USER, WP_APP_PASSWORD (GitHub Actions secrets).
Without --delete it only lists what would go (dry run). Posts of every status are included (publish, future, draft, pending, private, trash).
Posts go to the WordPress trash unless --permanent. Images deleted: featured images of those posts and media attached to them.
Never touched: pages, the site logo/icon, and images used as a page's featured image. The media library has no trash, so image deletion is permanent.
"""
import base64
import html
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

URL, USER, PW = (os.environ.get(k, "").rstrip("/") for k in ("WP_URL", "WP_USER", "WP_APP_PASSWORD"))
DELETE, PERMANENT = "--delete" in sys.argv, "--permanent" in sys.argv
AUTH = "Basic " + base64.b64encode(f"{USER}:{PW}".encode()).decode()


def call(path, method="GET"):
    req = urllib.request.Request(f"{URL}/wp-json/wp/v2/{path}", method=method, headers={"Authorization": AUTH, "User-Agent": "researcher-agents"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def all_pages(path):
    out, page = [], 1
    while True:
        sep = "&" if "?" in path else "?"
        try:
            batch = call(f"{path}{sep}per_page=100&page={page}")
        except urllib.error.HTTPError as e:
            if e.code == 400:  # page beyond the last one
                break
            raise
        out += batch
        if len(batch) < 100:
            return out
        page += 1
    return out


def main():
    if not (URL and USER and PW):
        sys.exit("WP_URL / WP_USER / WP_APP_PASSWORD not set")
    posts = all_pages("posts?context=edit&status=publish,future,draft,pending,private,trash&_fields=id,status,title,link,featured_media")
    post_ids = {p["id"] for p in posts}
    keep = set()  # media that must survive
    for p in all_pages("pages?context=edit&status=any&_fields=id,featured_media"):
        keep.add(p.get("featured_media"))
    try:
        s = call("settings")
        keep |= {s.get("site_logo"), s.get("site_icon")}
    except Exception as e:
        print(f"note: could not read site settings ({e}); the logo/icon are protected only if a page uses them")
    keep.discard(0)
    keep.discard(None)
    media = {m["id"]: m for m in all_pages("media?context=edit&status=any&_fields=id,post,source_url,title")}
    doomed = {p["featured_media"] for p in posts if p.get("featured_media")} | {i for i, m in media.items() if m.get("post") in post_ids}
    skipped = doomed & keep
    doomed = {i for i in doomed - keep if i in media}

    print(f"{'DELETING' if DELETE else 'DRY RUN'}: {len(posts)} posts, {len(doomed)} images "
          f"({'permanently' if PERMANENT else 'posts to trash'}); {len(skipped)} image(s) protected, {len(media) - len(doomed)} other media untouched\n")
    for p in sorted(posts, key=lambda p: p["id"]):
        print(f"post  {p['id']:>5}  {p['status']:<8} {html.unescape(p['title'].get('raw') or p['title'].get('rendered', ''))[:80]}")
    for i in sorted(doomed):
        print(f"image {i:>5}  {media[i]['source_url']}")
    if not DELETE:
        print("\nNothing deleted. Run again with delete=true and confirm=DELETE.")
        return
    failed = 0
    for p in posts:
        force = PERMANENT or p["status"] == "trash"  # an already-trashed post can only be removed with force
        try:
            call(f"posts/{p['id']}?force={'true' if force else 'false'}", "DELETE")
            print(f"ok   post {p['id']} {'deleted' if force else 'trashed'}")
        except Exception as e:
            failed += 1
            print(f"FAIL post {p['id']}: {e}", file=sys.stderr)
    for i in sorted(doomed):
        try:
            call(f"media/{i}?force=true", "DELETE")
            print(f"ok   image {i} deleted")
        except Exception as e:
            failed += 1
            print(f"FAIL image {i}: {e}", file=sys.stderr)
    print(f"\nDone: {len(posts)} posts and {len(doomed)} images processed, {failed} failed.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
