"""Fill config.json profiles (photo + official social links) from Wikidata / Wikimedia Commons.
Only empty fields are filled, so hand-edited values are never overwritten. Run manually when adding someone."""
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Researcher-agents/1.0 (news dashboard; contact via GitHub)"}
PROPS = {  # Wikidata property -> (profile key, URL template)
    "P2003": ("instagram", "https://www.instagram.com/{}/"),
    "P7085": ("tiktok", "https://www.tiktok.com/@{}"),
    "P2002": ("x", "https://x.com/{}"),
    "P2013": ("facebook", "https://www.facebook.com/{}"),
    "P2397": ("youtube", "https://www.youtube.com/channel/{}"),
    "P856": ("website", "{}"),
}


def get(url):
    for wait in (2, 8, 20, 40, 0):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                time.sleep(1)
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code != 429 or not wait:
                raise
            time.sleep(wait)


def api(**params):
    return json.loads(get("https://www.wikidata.org/w/api.php?format=json&" + urllib.parse.urlencode(params)))


def first(claims, pid):
    for c in claims.get(pid, []):
        if c.get("rank") != "deprecated" and "datavalue" in c.get("mainsnak", {}):
            return c["mainsnak"]["datavalue"]["value"]
    return None


def main():
    cfg = json.loads((ROOT / "config.json").read_text())
    (ROOT / "docs" / "img").mkdir(parents=True, exist_ok=True)
    for name in cfg["celebrities"]:
        prof = cfg.setdefault("profiles", {}).setdefault(name, {})
        hits = api(action="wbsearchentities", search=name, language="en", type="item", limit=5)["search"]
        hit = next((h for h in hits if re.search(r"actor|actress|singer|film|model", h.get("description", ""), re.I)), None)
        if not hit:
            print(f"skip {name}: no confident Wikidata match")
            continue
        claims = api(action="wbgetentities", ids=hit["id"], props="claims")["entities"][hit["id"]]["claims"]
        for pid, (key, tpl) in PROPS.items():
            val = first(claims, pid)
            if val and not prof.get(key):
                prof[key] = tpl.format(val)
        img = first(claims, "P18")
        if img and not prof.get("photo"):
            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            url = "https://commons.wikimedia.org/wiki/Special:FilePath/" + urllib.parse.quote(img) + "?width=300"
            (ROOT / "docs" / "img" / f"{slug}.jpg").write_bytes(get(url))
            prof["photo"] = f"img/{slug}.jpg"
            prof["photo_credit"] = f"https://commons.wikimedia.org/wiki/File:{urllib.parse.quote(img.replace(' ', '_'))}"
        print(name, hit["id"], {k: bool(v) for k, v in prof.items()})
        (ROOT / "config.json").write_text(json.dumps(cfg, indent=2) + "\n")  # save per person


if __name__ == "__main__":
    main()
