"""Celebrity research agent (standard library only): builds a research file per celebrity from Wikidata, plus a ranked list of people to add next.

Run:  python3 agents/research_celebrities.py [--only "Name"] [--max N] [--refresh]
Writes  data/research/<slug>.json   one file per celebrity in config.json (people already done are skipped unless --refresh)
        data/research/index.json    combined summary + expansion candidates
        data/research/REPORT.md     readable report: upcoming projects, relationships, family, directors, co-stars, anime, who to add next

What it collects (all from Wikidata's public records, each fact with its Wikidata id so it can be checked):
  profile       birth date/place, occupations, how well known they are (Wikipedia language editions)
  relationships marriages and recorded partnerships with start/end dates (only what Wikidata records; never rumours or affairs)
  family        number of children; a child is NAMED only when that child is an adult with their own Wikidata page. Minors are never named.
  projects      upcoming (release date in the future) and recent (last 4 years) films/series, with director and type
  directors     who they work with most; co-stars they appear with most
  anime/voice   voice roles in anime and animation
  expansion     people connected to the tracked group (partners, directors, co-stars) who are not in config.json yet, ranked by connections x fame
Gossip, unconfirmed relationships and anything about minors are out of scope on purpose: articles must still be written from the news sources.
"""
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "research"
UA = {"User-Agent": "Researcher-agents/1.0 (celebrity news research; https://github.com/MirzaNumanBaig/Researcher-agents)", "Accept": "application/json"}
RECENT_YEARS = 4
ANIME_TYPES = "wd:Q1107 wd:Q20650540 wd:Q63952888 wd:Q100269041 wd:Q581714"  # anime, anime film, anime TV series, anime web series, animated film
JOB = re.compile(r"actor|actress|singer|film|model|musician|rapper|comedian|director|presenter|songwriter|producer", re.I)


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def fetch(url, tries=6):
    """GET JSON. Wikimedia rate-limits politely (429 + Retry-After; the query service can be as strict as 1 request a minute), so wait as told and try again."""
    for i in range(tries):
        wait = 5 * (i + 1)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=70) as r:
                time.sleep(1.5)
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or i == tries - 1:
                raise
            ra = e.headers.get("Retry-After", "")
            wait = min(int(ra), 90) + 2 if ra.isdigit() else max(wait, 62 if e.code == 429 else wait)
        except (urllib.error.URLError, TimeoutError):
            if i == tries - 1:
                raise
        time.sleep(wait)


def api(**params):
    return fetch("https://www.wikidata.org/w/api.php?format=json&" + urllib.parse.urlencode(params))


def sparql(query):
    data = fetch("https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(query))
    return data["results"]["bindings"]


def val(b, k):
    return b.get(k, {}).get("value", "")


def qid_of(uri):
    return uri.rsplit("/", 1)[-1] if uri else ""


def claim_values(claims, pid):
    return [c for c in claims.get(pid, []) if c.get("rank") != "deprecated" and "datavalue" in c.get("mainsnak", {})]


def time_of(snak_list):
    for s in snak_list or []:
        v = s.get("datavalue", {}).get("value", {})
        if isinstance(v, dict) and v.get("time"):
            return v["time"].lstrip("+")[:10]
    return ""


def entities(ids, props):
    """{qid: entity} for a list of ids, 50 per request."""
    found = {}
    ids = sorted({i for i in ids if i})
    for i in range(0, len(ids), 50):
        found.update(api(action="wbgetentities", ids="|".join(ids[i:i + 50]), props=props, languages="en")["entities"])
    return found


def label(ent):
    return (ent.get("labels", {}).get("en") or {}).get("value", "")


def find_person(name):
    """Wikidata id of the human with this name, best-known first. '' when nothing confident is found."""
    hits = api(action="wbsearchentities", search=name, language="en", type="item", limit=8)["search"]
    ents = entities([h["id"] for h in hits], "claims|sitelinks|descriptions")
    best, best_fame = "", -1
    for h in hits:
        e = ents.get(h["id"], {})
        if not any(c["mainsnak"]["datavalue"]["value"].get("id") == "Q5" for c in claim_values(e.get("claims", {}), "P31")):
            continue
        desc = (e.get("descriptions", {}).get("en") or {}).get("value", "")
        if name.lower() not in (h.get("label", "") or "").lower() or not JOB.search(desc):
            continue
        fame = len(e.get("sitelinks", {}))
        if fame > best_fame:
            best, best_fame = h["id"], fame
    return best


def person_file(name, qid):
    ent = entities([qid], "claims|sitelinks|descriptions|labels")[qid]
    claims = ent.get("claims", {})
    ids = lambda pid: [c["mainsnak"]["datavalue"]["value"]["id"] for c in claim_values(claims, pid)]  # noqa: E731
    rel = {}
    for pid, kind in (("P26", "spouse"), ("P451", "partner")):
        for c in claim_values(claims, pid):
            q = c["mainsnak"]["datavalue"]["value"]["id"]
            quals = c.get("qualifiers", {})
            rel[(kind, q)] = {"kind": kind, "qid": q, "start": time_of(quals.get("P580")), "end": time_of(quals.get("P582")),
                              "end_cause": ",".join(x["datavalue"]["value"]["id"] for x in quals.get("P1534", []) if "datavalue" in x)}
    kids = ids("P40")
    related = entities(list(ids("P19")) + ids("P106") + [r["qid"] for r in rel.values()] + kids, "labels|claims|sitelinks")
    today = date.today().isoformat()
    spouses = []
    for r in sorted(rel.values(), key=lambda x: x["start"] or "9999"):
        e = related.get(r["qid"], {})
        spouses.append({"name": label(e), "qid": r["qid"], "kind": r["kind"], "start": r["start"], "end": r["end"],
                        "ended_by": {"Q99521170": "divorce", "Q3184138": "death of spouse", "Q24037741": "annulment"}.get(r["end_cause"], r["end_cause"]),
                        "fame": len(e.get("sitelinks", {}))})
    adult_kids = []
    for q in kids:
        e = related.get(q, {})
        born = time_of([c["mainsnak"] for c in claim_values(e.get("claims", {}), "P569")])
        if born and born[:4].isdigit() and int(born[:4]) <= date.today().year - 18 and e.get("sitelinks"):
            adult_kids.append({"name": label(e), "qid": q})  # an adult with their own public page; minors are never named
    birth = time_of([c["mainsnak"] for c in claim_values(claims, "P569")])
    place = label(related.get((ids("P19") or [""])[0], {}))
    works = sparql(f"""SELECT ?w ?wLabel ?date ?typeLabel ?dirLabel ?dir WHERE {{
      ?w wdt:P161 wd:{qid}; wdt:P577 ?date. FILTER(?date >= "{date.today().year - RECENT_YEARS}-01-01T00:00:00Z"^^xsd:dateTime)
      OPTIONAL {{ ?w wdt:P57 ?dir }} OPTIONAL {{ ?w wdt:P31 ?type }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }} }} ORDER BY DESC(?date) LIMIT 150""")
    projects = {}
    for b in works:
        q = qid_of(val(b, "w"))
        p = projects.setdefault(q, {"title": val(b, "wLabel"), "qid": q, "date": val(b, "date")[:10], "type": val(b, "typeLabel"), "directors": []})
        d = val(b, "dirLabel")
        if d and d not in p["directors"]:
            p["directors"].append(d)
    projects = [p for p in projects.values() if p["title"] and not re.fullmatch(r"Q\d+", p["title"])]
    upcoming = sorted([p for p in projects if p["date"] > today], key=lambda p: p["date"])
    recent = sorted([p for p in projects if p["date"] <= today], key=lambda p: p["date"], reverse=True)[:25]
    directors = Counter(d for p in projects for d in p["directors"])
    costars = sparql(f"""SELECT ?co ?coLabel (COUNT(DISTINCT ?w) AS ?n) (MAX(?sl) AS ?fame) WHERE {{
      ?w wdt:P161 wd:{qid}, ?co; wdt:P577 ?date. FILTER(?co != wd:{qid} && ?date >= "2010-01-01T00:00:00Z"^^xsd:dateTime)
      ?co wikibase:sitelinks ?sl. FILTER(?sl >= 15)
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }} }} GROUP BY ?co ?coLabel ORDER BY DESC(?n) LIMIT 15""")
    anime = sparql(f"""SELECT ?w ?wLabel ?date ?typeLabel WHERE {{
      ?w wdt:P725 wd:{qid}; wdt:P31 ?type. VALUES ?type {{ {ANIME_TYPES} }} OPTIONAL {{ ?w wdt:P577 ?date }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }} }} LIMIT 25""")
    return {
        "name": name, "qid": qid, "description": (ent.get("descriptions", {}).get("en") or {}).get("value", ""),
        "wikipedia_editions": len(ent.get("sitelinks", {})), "born": birth, "birthplace": place,
        "occupations": [label(related.get(q, {})) for q in ids("P106") if label(related.get(q, {}))],
        "relationships": spouses,
        "family": {"children_recorded": len(kids), "adult_children_public": adult_kids,
                   "note": "Minors are never named. Only relationships and children recorded on Wikidata are listed; no rumours."},
        "upcoming": upcoming, "recent": recent,
        "directors": [{"name": d, "projects": n} for d, n in directors.most_common(8)],
        "costars": [{"name": val(b, "coLabel"), "qid": qid_of(val(b, "co")), "projects": int(val(b, "n")), "fame": int(val(b, "fame"))} for b in costars],
        "anime_voice_roles": [{"title": val(b, "wLabel"), "type": val(b, "typeLabel"), "date": val(b, "date")[:10]} for b in anime if not re.fullmatch(r"Q\d+", val(b, "wLabel"))],
        "researched": today,
    }


def expansion(people, tracked):
    """People connected to the tracked group but not tracked yet, ranked: connections to tracked celebrities first, then fame."""
    names = {n.lower() for n in tracked}
    score = {}
    for p in people:
        for s in p["relationships"]:
            if s["name"] and s["name"].lower() not in names:
                c = score.setdefault(s["name"], {"name": s["name"], "via": [], "fame": s["fame"], "why": set()})
                c["via"].append(p["name"]); c["why"].add("partner/spouse")
        for s in p["costars"]:
            if s["name"] and s["name"].lower() not in names:
                c = score.setdefault(s["name"], {"name": s["name"], "via": [], "fame": s["fame"], "why": set()})
                c["via"].append(p["name"]); c["why"].add("co-star"); c["fame"] = max(c["fame"], s["fame"])
        for d in p["directors"]:
            if d["name"].lower() not in names:
                c = score.setdefault(d["name"], {"name": d["name"], "via": [], "fame": 0, "why": set()})
                c["via"].append(p["name"]); c["why"].add("director")
    out = [{"name": c["name"], "connected_to": sorted(set(c["via"])), "links": len(set(c["via"])), "roles": sorted(c["why"]), "wikipedia_editions": c["fame"]} for c in score.values()]
    return sorted(out, key=lambda c: (-c["links"], -c["wikipedia_editions"]))[:60]


def report(people, candidates):
    L = ["# Celebrity research report", f"Built {date.today().isoformat()} from Wikidata. Relationships and children are only what Wikidata records; minors are never named.\n"]
    L.append("## Upcoming projects (release date in the future)")
    up = sorted(((p["upcoming"][i]["date"], p["name"], p["upcoming"][i]) for p in people for i in range(len(p["upcoming"]))), key=lambda x: x[0])
    L += [f"- {d}: **{pr['title']}** ({pr['type'] or 'project'}) with {n}" + (f", directed by {', '.join(pr['directors'])}" if pr["directors"] else "") for d, n, pr in up] or ["- none recorded"]
    L.append("\n## Relationships on record")
    for p in people:
        rows = [f"{s['name'] or s['qid']} ({s['kind']}, {s['start'][:4] or '?'}" + (f"-{s['end'][:4]}" if s["end"] else "-now") + (f", {s['ended_by']}" if s["ended_by"] else "") + ")" for s in p["relationships"]]
        if rows:
            L.append(f"- **{p['name']}**: " + "; ".join(rows))
    L.append("\n## Family")
    for p in people:
        f = p["family"]
        if f["children_recorded"]:
            adults = ", ".join(k["name"] for k in f["adult_children_public"])
            L.append(f"- **{p['name']}**: {f['children_recorded']} child(ren) recorded" + (f"; adult and public: {adults}" if adults else ""))
    L.append("\n## Most frequent directors")
    for p in people:
        if p["directors"]:
            L.append(f"- **{p['name']}**: " + ", ".join(f"{d['name']} ({d['projects']})" for d in p["directors"][:5]))
    L.append("\n## Anime and animation voice roles")
    for p in people:
        if p["anime_voice_roles"]:
            L.append(f"- **{p['name']}**: " + ", ".join(a["title"] for a in p["anime_voice_roles"][:6]))
    L.append("\n## Who to add next (connected to your celebrities, not tracked yet)")
    L += [f"{i}. **{c['name']}** ({', '.join(c['roles'])}; linked to {', '.join(c['connected_to'][:4])})" for i, c in enumerate(candidates[:40], 1)]
    return "\n".join(L) + "\n"


def main():
    cfg = json.loads((ROOT / "config.json").read_text())
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    limit = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 999
    OUT.mkdir(parents=True, exist_ok=True)
    done = 0
    for name in cfg["celebrities"]:
        path = OUT / f"{slug(name)}.json"
        if (only and name != only) or (path.exists() and "--refresh" not in sys.argv) or done >= limit:
            continue
        try:
            qid = find_person(name)
            if not qid:
                print(f"skip {name}: no confident Wikidata match")
                continue
            path.write_text(json.dumps(person_file(name, qid), indent=1, ensure_ascii=False))
            done += 1
            print(f"ok   {name} ({qid})", flush=True)
        except Exception as e:  # one failure (rate limit, timeout) must not lose the others; it is retried on the next run
            print(f"FAIL {name}: {e}", file=sys.stderr, flush=True)
    people = [json.loads((OUT / f"{slug(n)}.json").read_text()) for n in cfg["celebrities"] if (OUT / f"{slug(n)}.json").exists()]
    cands = expansion(people, cfg["celebrities"])
    (OUT / "index.json").write_text(json.dumps({"built": date.today().isoformat(), "celebrities": [
        {"name": p["name"], "qid": p["qid"], "upcoming": len(p["upcoming"]), "relationships": len(p["relationships"]),
         "children_recorded": p["family"]["children_recorded"], "wikipedia_editions": p["wikipedia_editions"]} for p in people],
        "expansion_candidates": cands}, indent=1, ensure_ascii=False))
    (OUT / "REPORT.md").write_text(report(people, cands))
    print(f"{done} researched this run, {len(people)} on file, {len(cands)} expansion candidates")


if __name__ == "__main__":
    main()
