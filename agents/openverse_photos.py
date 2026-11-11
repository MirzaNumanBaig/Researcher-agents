"""Second photo source for the celebrity photo pool: Openverse (https://openverse.org), the open search of Creative Commons images. In practice this
is mostly Flickr, where photographers such as Gage Skidmore upload festival and premiere portraits under CC BY / CC BY-SA.

It is used only for people Wikimedia Commons could not fully cover (fewer than ENOUGH face-verified photos). Everything else is the same as Commons:
  - licences CC0, public domain, CC BY, CC BY-SA only (never NC or ND); the credit (photographer, licence, link to the photo page) is printed with the picture
  - the file title/tags must name the person; posters, screenshots, wax figures, memorials etc. are rejected (same word list as Commons)
  - the picture is downloaded and must pass the same OpenCV face check (one clear face, no crowd); an unchecked photo is never kept
  - photos on the owner's blocklist (data/photo_blocklist.json, key "Flickr:<id>") are never used
Entries have the same shape as Commons entries plus "source": "openverse", so generate_images.py needs no special case except the credit wording.
"""
import io
import json
import os
import re
import urllib.parse

import commons_photos as cp

API = os.environ.get("OPENVERSE_API_URL", "https://api.openverse.org/v1/images/")
VERSION = 1  # bump to search everybody again
ENOUGH = 3  # people with fewer verified Commons photos than this also get Openverse photos
MIN_SIDE, MIN_LONG = 640, 1000
KEEP, CHECK, PAGES = 8, 14, 2
MULTI = re.compile(r"(\band\b|&|\bwith\b|\bfeat\.?|\bplus\b|\bfeaturing\b|\bvs\.?\b|\bx\b|,)", re.I)  # "Miley Cyrus and Liam Hemsworth": a picture of two people is not this person's portrait
ALLOWED = {"cc0": "CC0 1.0", "pdm": "Public domain", "by": "CC BY", "by-sa": "CC BY-SA"}


def label(item):
    lic = (item.get("license") or "").lower()
    if lic not in ALLOWED:
        return ""
    if lic in ("cc0", "pdm"):
        return ALLOWED[lic]
    return f"{ALLOWED[lic]} {item.get('license_version') or ''}".strip()


def parse(item):
    """A pool entry from one Openverse result, or None when it cannot be used."""
    lic = label(item)
    page, url = item.get("foreign_landing_url") or "", item.get("url") or ""
    if not (lic and page.startswith("http") and url.startswith("http")) or item.get("mature"):
        return None
    if (item.get("filetype") or "jpg").lower() not in ("jpg", "jpeg"):
        return None
    w, h = item.get("width") or 0, item.get("height") or 0
    if w and h and (min(w, h) < MIN_SIDE or max(w, h) < MIN_LONG):
        return None
    title = re.sub(r"\s+", " ", item.get("title") or "").strip()
    tags = " ".join(t.get("name", "") for t in item.get("tags") or [])
    if cp.BAD_WORDS.search(f"{title} {tags}") or MULTI.search(title):
        return None
    prov = (item.get("source") or item.get("provider") or "").lower()
    author = (item.get("creator") or "").strip() or "Photographer"
    return {"file": f"{prov.capitalize()}:{page.rstrip('/').rsplit('/', 1)[-1] or item.get('id')}", "page": page, "url": url, "thumb": url,
            "width": w, "height": h, "license": lic, "license_url": item.get("license_url") or "", "author": author[:120],
            "author_url": item.get("creator_url") or "", "date": "", "description": title[:200], "category": "Openverse", "categories": [],
            "source": "openverse", "provider": prov.capitalize() or "Openverse", "tags": tags[:200],
            "credit": f"Photo: {author}, {lic}, via {prov.capitalize() or 'Openverse'}"}


def search(name):
    """Candidate photos for this person, newest search order of Openverse (its own relevance order)."""
    out = []
    for page in range(1, PAGES + 1):
        q = urllib.parse.urlencode({"q": f'"{name}"', "license": ",".join(ALLOWED), "extension": "jpg", "source": "flickr", "page_size": 20, "page": page, "mature": "false"})
        try:
            data = json.loads(cp._get(f"{API}?{q}"))
        except cp.CommonsError as e:
            if "HTTP 404" in str(e) or "HTTP 400" in str(e):  # past the last page
                break
            raise
        out += data.get("results") or []
        cp._sleep(1.0)
        if page >= (data.get("page_count") or 1):
            break
    return out


def named(name, p):
    """The title or tags must name the person (full name, or the surname when the title is short, e.g. 'Robbie at Cannes')."""
    text = f"{p['description']} {p.get('tags', '')}".lower()
    return name.lower() in text


def size_of(raw):
    try:
        from PIL import Image
        return Image.open(io.BytesIO(raw)).size
    except Exception:
        return 0, 0


def check(p):
    """(ok, face fraction) after downloading the picture; also fills in width/height. Not downloadable or too small = not ok."""
    cp._sleep(cp.IMG_PAUSE)
    try:
        raw = cp._get(p["url"])
    except cp.CommonsError:
        return False, 0.0
    w, h = size_of(raw)
    if w and h:
        if min(w, h) < MIN_SIDE or max(w, h) < MIN_LONG:
            return False, 0.0
        p["width"], p["height"] = w, h
    res = cp.detect_faces(raw)
    if res is None:
        raise cp.FaceCheckUnavailable("OpenCV is not installed (pip install opencv-python-headless numpy)")
    ok, _why, frac = cp.judge_faces(*res)
    return ok, round(frac, 3)


def refresh(name):
    """Up to KEEP face-verified, openly licensed photos of this person from Openverse (may be empty). Raises CommonsError when throttled."""
    ban = cp.blocked()
    seen, cands = set(), []
    for item in search(name):
        p = parse(item)
        if p and p["file"] not in seen and p["file"] not in ban and named(name, p):
            seen.add(p["file"])
            cands.append(p)
    kept = []
    check_faces = os.environ.get("PHOTO_FACE_CHECK", "on").lower() != "off"
    for p in cands[:CHECK]:
        if check_faces:
            ok, frac = check(p)
            if not ok:
                continue
            p["face"] = frac
            p["score"] = round(0.5 + (2.0 if frac >= 0.25 else 1.5 if frac >= 0.15 else 1.0) + (0.5 if max(p["width"], p["height"]) >= 1600 else 0), 2)
        else:
            p["face"], p["score"] = None, 0.5
        kept.append(p)
    kept.sort(key=lambda p: -p["score"])
    return kept[:KEEP]
