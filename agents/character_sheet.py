"""Builds data/character-sheet.json: the newest free-licence Commons photo of every celebrity.

For each name it tries the Commons category "<Name> in 2026", then 2025, then 2024, and
keeps the newest still image with a free licence and a face-friendly size. Each entry has the
file, licence, author, date and the credit line to print. Links only; nothing is downloaded.
Run: python3 agents/character_sheet.py [--only "Chris Hemsworth"]
"""
import json, re, sys, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://commons.wikimedia.org/w/api.php"
UA = "ModusCarry/1.0 (themoduscarry@gmail.com)"
YEARS = (2026, 2025, 2024)
FREE = ("CC BY", "CC0", "Public domain", "PD")
BAD = ("logo", "signature", "poster", "autograph")


def call(params, tries=6):
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    for i in range(tries):
        time.sleep(1.5)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            return json.load(urllib.request.urlopen(req, timeout=30))
        except Exception:
            time.sleep(10 * (i + 1))
    raise RuntimeError("Wikimedia kept refusing the request (rate limit)")


def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def candidates(name):
    for year in YEARS:
        cat = f"Category:{name} in {year}"
        d = call({"action": "query", "generator": "categorymembers", "gcmtitle": cat,
                  "gcmtype": "file", "gcmlimit": 50, "prop": "imageinfo",
                  "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 800})
        pages = (d.get("query") or {}).get("pages") or {}
        out = []
        for p in pages.values():
            ii = (p.get("imageinfo") or [{}])[0]
            m = ii.get("extmetadata") or {}
            lic = clean((m.get("LicenseShortName") or {}).get("value"))
            if ii.get("mime") != "image/jpeg" or not lic.startswith(FREE):
                continue
            if min(ii.get("width", 0), ii.get("height", 0)) < 900:
                continue
            title = p["title"]
            if any(b in title.lower() for b in BAD):
                continue
            out.append({
                "file": title, "page": ii["descriptionurl"], "url": ii["url"],
                "thumb": ii.get("thumburl"), "width": ii["width"], "height": ii["height"],
                "license": lic, "license_url": clean((m.get("LicenseUrl") or {}).get("value")),
                "author": clean((m.get("Artist") or {}).get("value")),
                "date": clean((m.get("DateTimeOriginal") or m.get("DateTime") or {}).get("value"))[:10],
                "description": clean((m.get("ImageDescription") or {}).get("value"))[:200],
                "category": cat,
            })
        if out:
            out.sort(key=lambda x: x["date"], reverse=True)
            return out
    return []


def credit(e):
    return f"Photo: {e['author'] or 'Wikimedia Commons contributor'}, {e['license']}, via Wikimedia Commons"


def main():
    cfg = json.load(open(ROOT / "config.json"))
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    path = ROOT / "data" / "character-sheet.json"
    sheet = json.load(open(path)) if path.exists() else {}
    for name in cfg["celebrities"]:
        if only and name != only:
            continue
        if (sheet.get(name) or {}).get("status") == "ok":
            continue  # already found; a re-run only fills the gaps
        try:
            found = candidates(name)
        except RuntimeError as e:  # a throttled request is not "no photo": leave it for the next run
            print("retry", name, e, flush=True)
            continue
        if not found:
            sheet[name] = {"status": "no_free_photo", "photos": []}
            print("none ", name, flush=True)
            save(path, sheet)
            continue
        for e in found:
            e["credit"] = credit(e)
        sheet[name] = {"status": "ok", "photos": found[:3]}
        print("ok   ", name, found[0]["date"], found[0]["file"], flush=True)
        save(path, sheet)
    save(path, sheet)


def save(path, sheet):
    path.parent.mkdir(exist_ok=True)
    json.dump(sheet, open(path, "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
