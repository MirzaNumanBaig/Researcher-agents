"""Find open-licence photos of a celebrity on Wikimedia Commons (standard library only). Used by character_sheet.py to build data/character-sheet.json,
the photo pool that generate_images.py draws featured images from.

What it does better than the first version (which only read the Commons categories "<Name> in 2026/2025/2024" and downloaded 800-960 px thumbnails):
  - searches the person's main Commons category (found through Wikidata) AND their year/event sub-categories ("Margot Robbie in 2023", "...at the Cannes Film Festival")
  - fetches a 1920 px wide copy, so a 1600 px featured image is not stretched from a small thumbnail
  - rejects non-commercial/no-derivatives licences, posters, covers, screenshots, wax figures, signatures and group-photo-style files
  - ranks photos: recent (looks like the person today), large, landscape (crops well), described as this person, and rated Featured/Quality/Valued on Commons
  - LOOKS at the pictures (OpenCV face detection, as the live image step already does): a photo is kept only when one face is clearly the subject: at least
    12% of the image width, no second face nearly as big (groups and panels are out), not pushed against the edge. Distant stage shots, crowds, plaques,
    memorials, objects and the back of someone's head have no such face and are dropped. A file must also name the person in its title or description.
Licences accepted: CC0, public domain, CC BY, CC BY-SA. The site earns from ads, so NC and ND are never used. Credit is always printed with the picture.
"""
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

COMMONS = os.environ.get("COMMONS_API_URL", "https://commons.wikimedia.org/w/api.php")
WIKIDATA = os.environ.get("WIKIDATA_API_URL", "https://www.wikidata.org/w/api.php")
UA = {"User-Agent": "Researcher-agents/1.0 (news site photo credits; https://github.com/MirzaNumanBaig/Researcher-agents)"}
PAUSE = float(os.environ.get("COMMONS_PAUSE", "1.5"))
IMG_PAUSE = float(os.environ.get("COMMONS_IMG_PAUSE", "0.6"))  # between picture downloads  # seconds between requests: Wikimedia asks automated clients to be gentle
VERSION = 3  # bump to make character_sheet.py search everyone again with a better method
KEEP, MIN_WIDTH, MIN_HEIGHT, THUMB_WIDTH = 20, 1200, 700, 1920
FACE_MIN, FACE_SECOND, CHECK, CHECK_WIDTH = 0.12, 0.45, 24, 500  # 500 is one of Wikimedia's fixed thumbnail sizes (other widths return HTTP 400)  # face >= 12% of width; 2nd face < 45% of the biggest's area; how many candidates to look at
_sleep = time.sleep  # replaced in tests

BAD_WORDS = re.compile(r"\b(poster|cover|screenshot|signature|autograph|wax|statue|mural|cartoon|caricature|stamp|logo|fan art|film still|still from|trailer|album|dvd|figurine|lookalike|impersonat\w+|cosplay|walk of fame|memorial|plaque|grave|tomb|sculpture|bust of)\b", re.I)
MOOD = {"featured pictures": 2.0, "quality images": 1.5, "valued images": 1.0}
META_FIELDS = "LicenseShortName|LicenseUrl|Artist|Credit|ImageDescription|DateTimeOriginal|DateTime|Categories|NonFree"


class CommonsError(Exception):
    pass


class FaceCheckUnavailable(CommonsError):
    """OpenCV is not installed: without the face check the pool would contain distant shots, plaques and groups, so the builder stops instead."""


def _get(url, tries=4):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=45) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code not in (429, 500, 502, 503, 504):
                raise CommonsError(last)
            wait = e.headers.get("Retry-After", "")
            _sleep(int(wait) if wait.isdigit() and int(wait) <= 90 else 8 * 2 ** i)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = str(e)
            _sleep(3 * 2 ** i)
    raise CommonsError(f"gave up after {tries} attempts: {last}")


def api(base, **params):
    _sleep(PAUSE)
    try:
        return json.loads(_get(base + "?" + urllib.parse.urlencode({"format": "json", "formatversion": 2, **params})))
    except ValueError as e:
        raise CommonsError(f"bad JSON from {base}: {e}")


def strip(text):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text or "")).split())


def allowed_license(short):
    """CC0, public domain, CC BY and CC BY-SA only (NC = non-commercial and ND = no derivatives cannot be used on an ad-funded site that crops images)."""
    s = (short or "").strip().lower()
    if not s or re.search(r"\b(nc|nd)\b|-nc|-nd|non-?commercial|no derivatives|gfdl|fair use|copyrighted|all rights|unknown", s):
        return False
    return bool(re.match(r"^(cc0|cc[ -]?zero|public domain|pd\b|pdm|cc[ -]by(-sa)?\b)", s))


def parse_photo(page, category=""):
    """A character-sheet photo entry from one Commons API page, or None when the file cannot be used."""
    info = (page.get("imageinfo") or [None])[0]
    if not info:
        return None
    m = {k: (v.get("value") if isinstance(v, dict) else v) for k, v in (info.get("extmetadata") or {}).items()}
    w, h = info.get("width") or 0, info.get("height") or 0
    if info.get("mime") != "image/jpeg" or w < MIN_WIDTH or h < MIN_HEIGHT:
        return None
    if str(m.get("NonFree", "")).lower() in ("true", "1", "yes") or not allowed_license(m.get("LicenseShortName")):
        return None
    title, desc = page.get("title", ""), strip(m.get("ImageDescription"))
    cats = [c.strip() for c in (m.get("Categories") or "").split("|") if c.strip()]
    if BAD_WORDS.search(f"{title} {desc} {' '.join(cats)}"):
        return None
    artist = m.get("Artist") or m.get("Credit") or ""
    href = re.search(r'href="([^"]+)"', artist)
    date = re.search(r"((?:19|20)\d{2})(?:-(\d{2}))?(?:-(\d{2}))?", m.get("DateTimeOriginal") or m.get("DateTime") or "")
    when = "-".join(x for x in date.groups() if x) if date else ""
    author = strip(artist)[:120] or "Wikimedia Commons contributor"
    lic = strip(m.get("LicenseShortName"))
    return {"file": title, "page": info.get("descriptionurl") or "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
            "url": info.get("url"), "thumb": info.get("thumburl") or info.get("url"), "width": w, "height": h, "license": lic,
            "license_url": m.get("LicenseUrl") or "", "author": author, "author_url": ("https:" + href.group(1) if href and href.group(1).startswith("//") else (href.group(1) if href else "")),
            "date": when, "description": desc[:200], "category": category, "categories": cats[:10], "credit": f"Photo: {author}, {lic}, via Wikimedia Commons"}


def score(p, name, now_year=None):
    """Higher is better: recent, large, landscape, about this person, rated by Commons."""
    now_year = now_year or datetime.now(timezone.utc).year
    ratio = p["width"] / p["height"]
    s = min(p["width"], 3000) / 1000
    s += 2 if 1.4 <= ratio <= 2.0 else 1 if 1.15 <= ratio < 1.4 else -1 if ratio < 0.8 else -1 if ratio > 2.4 else 0
    year = int(p["date"][:4]) if p["date"][:4].isdigit() else 0
    age = now_year - year if year else 99
    s += 2.5 if age <= 2 else 1.8 if age <= 4 else 1.0 if age <= 7 else 0.2 if age <= 10 else -0.8  # faces change: a 2012 photo does not look like the person now
    if name.lower() in f"{p['file']} {p['description']}".lower():
        s += 1.5
    s += max([v for k, v in MOOD.items() if any(k in c.lower() for c in p["categories"])] or [0])
    if re.search(r"cc0|public domain|pd", p["license"], re.I):
        s += 0.4
    return round(s, 2)


def blocked():
    """File titles the owner banned (data/photo_blocklist.json): never used, however well they rank."""
    try:
        from pathlib import Path
        return set(json.loads((Path(__file__).resolve().parent.parent / "data" / "photo_blocklist.json").read_text()).get("files", []))
    except (OSError, ValueError):
        return set()


def mentions(name, p):
    """Does the file's title or description name the person (full name or surname)? A file that does not is probably someone else or nobody."""
    text = f"{p['file']} {p['description']}".lower()
    last = name.split()[-1].lower()
    return name.lower() in text or (len(last) >= 3 and re.search(rf"\b{re.escape(last)}\b", text) is not None)


def small_url(thumb):
    """The same Commons thumbnail at CHECK_WIDTH px (Wikimedia makes any width on demand): enough to find faces, light to download."""
    return re.sub(r"/\d+px-", f"/{CHECK_WIDTH}px-", thumb or "", count=1)


def _iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix, iy = max(0, min(ax + aw, bx + bw) - max(ax, bx)), max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    return inter / float(aw * ah + bw * bh - inter) if inter else 0.0


def detect_faces(raw):
    """(width, height, faces, others) or None when OpenCV is not installed.
    faces  = faces found by the default detector AND confirmed by a second, stricter one (this removes mannequins, posters and textures that look like a face)
    others = every face a looser pass can see, to count the other people in the picture (crowds, groups, children next to the subject)"""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    gray = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        return (0, 0, [], [])
    if gray.shape[1] > CHECK_WIDTH:
        gray = cv2.resize(gray, None, fx=CHECK_WIDTH / gray.shape[1], fy=CHECK_WIDTH / gray.shape[1])
    h, w = gray.shape
    load = lambda n: cv2.CascadeClassifier(cv2.data.haarcascades + n)  # noqa: E731
    main = [tuple(int(v) for v in f) for f in load("haarcascade_frontalface_default.xml").detectMultiScale(gray, 1.08, 6, minSize=(max(24, int(w * 0.04)),) * 2)]
    strict = [tuple(int(v) for v in f) for f in load("haarcascade_frontalface_alt2.xml").detectMultiScale(gray, 1.08, 4, minSize=(max(24, int(w * 0.04)),) * 2)]
    confirmed = [f for f in main if any(_iou(f, g) >= 0.4 for g in strict)]
    loose = [tuple(int(v) for v in f) for f in load("haarcascade_frontalface_default.xml").detectMultiScale(gray, 1.08, 4, minSize=(max(20, int(w * 0.025)),) * 2)]
    return w, h, confirmed, loose


def judge_faces(w, h, faces, others=()):
    """(ok, reason, face width as a fraction of the picture). One clear subject: big enough, alone, not at the edge."""
    if not faces or not w:
        return False, "no face", 0.0
    faces = sorted(faces, key=lambda f: -f[2] * f[3])
    x, y, fw, fh = faces[0]
    frac = fw / w
    if frac < FACE_MIN:
        return False, f"face too small ({frac:.2f})", frac
    everyone = sorted(set(faces) | set(others), key=lambda f: -f[2] * f[3])
    rest = [f for f in everyone if _iou(f, faces[0]) < 0.4]  # everybody except the subject
    if rest and rest[0][2] * rest[0][3] >= FACE_SECOND * fw * fh:
        return False, "several faces", frac
    if len(rest) >= 2:
        return False, "a group or crowd", frac
    cx = (x + fw / 2) / w
    if w / h >= 1.2 and not 0.15 <= cx <= 0.85:
        return False, "face near the edge", frac
    return True, "", frac


def face_gate(p):
    """(ok, face fraction) for one candidate, by downloading a small copy. A photo that cannot be checked (download failed) is NOT ok: a wrong face is worse than none."""
    _sleep(IMG_PAUSE)
    try:
        res = detect_faces(_get(small_url(p["thumb"]) or p["thumb"]))
    except CommonsError:
        return False, 0.0
    if res is None:
        raise FaceCheckUnavailable("OpenCV is not installed (pip install opencv-python-headless numpy); set PHOTO_FACE_CHECK=off to skip the face check")
    ok, why, frac = judge_faces(*res)
    return ok, round(frac, 3)


def find_category(name):
    """The person's main Commons category through Wikidata (P373), or None."""
    found = api(WIKIDATA, action="wbsearchentities", search=name, language="en", type="item", limit=6).get("search", [])
    ids = [r["id"] for r in found]
    if not ids:
        return None
    ents = api(WIKIDATA, action="wbgetentities", ids="|".join(ids), props="claims|labels", languages="en").get("entities", {})
    fallback = None
    for i in ids:
        e = ents.get(i) or {}
        if not any((c.get("mainsnak", {}).get("datavalue", {}).get("value") or {}).get("id") == "Q5" for c in (e.get("claims", {}).get("P31") or [])):
            continue
        cat = next((c["mainsnak"]["datavalue"]["value"] for c in (e.get("claims", {}).get("P373") or []) if c.get("mainsnak", {}).get("datavalue")), None)
        if cat and ((e.get("labels") or {}).get("en") or {}).get("value", "").lower() == name.lower():
            return cat
        fallback = fallback or cat
    return fallback


def files_in(cat, pages=3):
    out, cont = [], {}
    for _ in range(pages):
        d = api(COMMONS, action="query", generator="categorymembers", gcmtitle="Category:" + cat, gcmtype="file", gcmlimit=50, prop="imageinfo",
                iiprop="url|size|mime|extmetadata", iiurlwidth=THUMB_WIDTH, iiextmetadatafilter=META_FIELDS, **cont)
        out += d.get("query", {}).get("pages", [])
        cont = d.get("continue") or {}
        if not cont:
            break
    return out


def sub_categories(cat, name, limit=8):
    """Year and event sub-categories of this person, newest year first ("Name in 2025", "Name at the 2024 Venice Film Festival")."""
    d = api(COMMONS, action="query", list="categorymembers", cmtitle="Category:" + cat, cmtype="subcat", cmlimit=200)
    titles = [m["title"].split(":", 1)[1] for m in d.get("query", {}).get("categorymembers", [])]
    last = name.split()[-1].lower()
    mine = [t for t in titles if last in t.lower()]

    def year(t):
        m = re.search(r"(20\d{2}|19\d{2})", t)
        return int(m.group(1)) if m else 0

    return sorted(mine, key=year, reverse=True)[:limit]


def refresh(name):
    """{status, category, photos[]}: the best KEEP photos of this person, ranked. status is 'ok' or 'no_free_photo'. Raises CommonsError when throttled."""
    cat = find_category(name) or name
    sources = [cat] + sub_categories(cat, name) + [f"{name} in {y}" for y in (2026, 2025) if f"{name} in {y}" != cat]
    seen, photos = set(), []
    for i, c in enumerate(dict.fromkeys(sources)):
        try:
            pages = files_in(c, pages=3 if i == 0 else 1)
        except CommonsError as e:
            if "HTTP 404" in str(e):
                continue
            raise
        for pg in pages:
            p = parse_photo(pg, "Category:" + c)
            if p and p["file"] not in seen:
                seen.add(p["file"])
                p["score"] = score(p, name)
                photos.append(p)
    ban = blocked()
    photos = [p for p in photos if mentions(name, p) and p["file"] not in ban]
    photos.sort(key=lambda p: -p["score"])
    kept, unchecked = [], 0
    check_faces = os.environ.get("PHOTO_FACE_CHECK", "on").lower() != "off"
    for p in photos[:CHECK]:
        if not check_faces:  # explicit opt-out: metadata ranking only, flagged as unverified
            p["face"], unchecked = None, unchecked + 1
            kept.append(p)
            continue
        ok, frac = face_gate(p)
        if ok:
            p["face"] = frac
            p["score"] = round(p["score"] + (2.0 if frac >= 0.25 else 1.5 if frac >= 0.15 else 1.0), 2)  # a clear, close face beats a small one
            kept.append(p)
    kept.sort(key=lambda p: -p["score"])
    return {"status": "ok" if kept else "no_free_photo", "v": VERSION, "category": cat, "examined": min(len(photos), CHECK), "unverified": unchecked, "photos": kept[:KEEP]}
