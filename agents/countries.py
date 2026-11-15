"""Countries of the people we follow, and the hot people of the countries the site is written for (Wikidata + Wikipedia pageviews).

The audience is Australia, the UK, Norway, Denmark and Canada. `config.json` `countries` maps each tracked name to one of them (or "USA" / "Other").
`hot_people(country)` = living actors/directors/writers/producers/musicians of that country with a film released from 60 days ago to 10 months ahead,
ranked by Wikipedia pageviews over the last 30 days (a proxy for "in the news"). Only recorded facts.
"""
import json
import re
import sys
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_celebrities as rc  # noqa: E402
import trending_people as tp  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SHOWN = ["Australia", "UK", "Norway", "Denmark", "Canada"]  # the audience; everyone else is "USA" or "Other"
CITIZEN = {  # Wikidata country id -> our label
    "Q408": "Australia", "Q145": "UK", "Q21": "UK", "Q22": "UK", "Q25": "UK", "Q26": "UK", "Q174193": "UK",
    "Q20": "Norway", "Q35": "Denmark", "Q756617": "Denmark", "Q16": "Canada", "Q30": "USA",
}
RANK = {c: i for i, c in enumerate(SHOWN + ["USA"])}


def label_for(country_ids):
    """The best label for a person's citizenships: an audience country wins over USA, USA over Other."""
    labels = [CITIZEN[c] for c in country_ids if c in CITIZEN]
    return min(labels, key=lambda l: RANK[l]) if labels else "Other"


def countries_of(qids):
    """{qid: label} for people (ONE query per 150)."""
    out, qs = {}, list(qids)
    for i in range(0, len(qs), 150):
        vals = " ".join(f"wd:{q}" for q in qs[i:i + 150])
        try:
            rows = rc.sparql(f"SELECT ?p ?c WHERE {{ VALUES ?p {{ {vals} }} ?p wdt:P27 ?c. }}")
        except Exception as e:
            print(f"  country query skipped: {e}", file=sys.stderr, flush=True)
            continue
        got = {}
        for b in rows:
            got.setdefault(rc.qid_of(rc.val(b, "p")), []).append(rc.qid_of(rc.val(b, "c")))
        out.update({q: label_for(c) for q, c in got.items()})
    return out


def fill_countries(cfg, names=None):
    """Add the country of every tracked name that has none yet to cfg['countries']; returns the names newly labelled."""
    have = cfg.setdefault("countries", {})
    todo = [n for n in (names or cfg["celebrities"]) if n not in have]
    if not todo:
        return []
    ids = tp.qids_for([n.replace(" ", "_") for n in todo])
    by_q = {q: n for n in todo for t, q in ids.items() if t == n.replace(" ", "_")}
    found = countries_of(by_q)
    done = []
    for q, label in found.items():
        have[by_q[q]] = label
        done.append(by_q[q])
    for n in todo:
        if n not in have and any(ids.get(n.replace(" ", "_")) for _ in [0]):
            have[n] = "Other"  # on Wikipedia but no citizenship recorded
    return done


def pageviews(titles, days=30):
    """{title: views over the last `days` days} through Wikipedia's API (50 titles per call)."""
    out = {}
    titles = list(titles)
    for i in range(0, len(titles), 50):
        chunk = titles[i:i + 50]
        try:
            data = rc.fetch(tp.WP_API + f"?format=json&formatversion=2&action=query&prop=pageviews&pvipdays={days}&redirects=1&titles=" + urllib.parse.quote("|".join(chunk)))
        except Exception as e:
            print(f"  pageviews batch skipped: {e}", file=sys.stderr, flush=True)
            continue
        for pg in data.get("query", {}).get("pages", []):
            out[pg.get("title", "")] = sum(v or 0 for v in (pg.get("pageviews") or {}).values())
        for step in data.get("query", {}).get("redirects", []) + data.get("query", {}).get("normalized", []):
            if step["to"] in out:
                out.setdefault(step["from"], out[step["to"]])
    return out


def hot_people(country, top=8, exclude=(), today=None):
    """[{name, qid, views_30d, film, release, description, country}] for one audience country, hottest first.
    Films released from 60 days ago to 10 months ahead -> their cast and directors of this country (one light query, ids only),
    then names, descriptions, Wikipedia titles and living/occupation checks through the entity API, then 30-day pageviews."""
    today = today or date.today()
    ids = [q for q, l in CITIZEN.items() if l == country]
    vals = " ".join(f"wd:{q}" for q in ids)
    rows = []
    step = 75 if country == "UK" else 360  # the UK has so many credits that the window is cut into slices the query service can answer
    start, end = today - timedelta(days=60), today + timedelta(days=300)
    while start < end:
        stop = min(start + timedelta(days=step), end)
        query = f"""SELECT ?p ?f ?pub WHERE {{
          ?f wdt:P31 ?kind; wdt:P577 ?pub. VALUES ?kind {{ {tp.FILM_KINDS} }}
          FILTER(?pub >= "{start.isoformat()}T00:00:00Z"^^xsd:dateTime && ?pub < "{stop.isoformat()}T00:00:00Z"^^xsd:dateTime)
          ?f (wdt:P161|wdt:P57) ?p. ?p wdt:P27 ?cit. VALUES ?cit {{ {vals} }} }} LIMIT 900"""
        try:
            rows += rc.sparql(query)
        except Exception as e:
            print(f"  {country}: slice {start} failed ({e})", file=sys.stderr, flush=True)
        start = stop
    if not rows:
        return []
    film_of = {}  # person -> (release, film qid): their first release in the window
    for b in rows:
        pq, fq, d = rc.qid_of(rc.val(b, "p")), rc.qid_of(rc.val(b, "f")), rc.val(b, "pub")[:10]
        if re.fullmatch(r"\d{4}-\d\d-\d\d", d) and (pq not in film_of or d < film_of[pq][0]):
            film_of[pq] = (d, fq)
    ents = rc.entities(film_of, "labels|descriptions|sitelinks|claims")
    films = {q: rc.label(e) for q, e in rc.entities({f for _, f in film_of.values()}, "labels").items()}
    ok_jobs = set(tp.ROLES)
    cand = {}
    skip = {e.lower() for e in exclude}
    for q, (d, f) in film_of.items():
        e = ents.get(q) or {}
        name, desc = rc.label(e), (e.get("descriptions", {}).get("en") or {}).get("value", "")
        title = (e.get("sitelinks", {}).get("enwiki") or {}).get("title", "")
        jobs = {c["mainsnak"]["datavalue"]["value"].get("id") for c in rc.claim_values(e.get("claims", {}), "P106")}
        if not (name and title and " " in name.strip() and jobs & ok_jobs) or rc.claim_values(e.get("claims", {}), "P570") or name.lower() in skip:
            continue
        if tp.NOT_ENTERTAINER.search(desc):
            continue
        cand[title] = {"name": name, "qid": q, "description": desc, "film": films.get(f, ""), "release": d, "country": country}
    views = pageviews(cand)
    out = []
    for t, c in cand.items():
        c["views_30d"] = views.get(t, 0)
        out.append(c)
    out.sort(key=lambda c: -c["views_30d"])
    print(f"  {country}: {len(out)} people with a film in the window; top: {', '.join(r['name'] for r in out[:top])}", flush=True)
    return out[:top]


NORDIC_CATEGORIES = {
    "Norway": ["Norwegian male film actors", "Norwegian film actresses", "Norwegian male television actors", "Norwegian film directors"],
    "Denmark": ["Danish male film actors", "Danish film actresses", "Danish male television actors", "Danish film directors"],
}


def category_people(country, cap=400):
    """Wikipedia titles in the country's actor/director categories (small enough for Norway and Denmark, where Wikidata's film credits are sparse)."""
    titles = []
    for cat in NORDIC_CATEGORIES.get(country, []):
        cont = ""
        while len(titles) < cap * 4:
            try:
                data = rc.fetch(tp.WP_API + "?format=json&formatversion=2&action=query&list=categorymembers&cmlimit=500&cmnamespace=0&cmtitle=" + urllib.parse.quote("Category:" + cat) + (f"&cmcontinue={urllib.parse.quote(cont)}" if cont else ""))
            except Exception as e:
                print(f"  category {cat} skipped: {e}", file=sys.stderr, flush=True)
                break
            titles += [m["title"] for m in data.get("query", {}).get("categorymembers", [])]
            cont = (data.get("continue") or {}).get("cmcontinue", "")
            if not cont:
                break
    return list(dict.fromkeys(titles))


def hot_nordic(country, top=8, exclude=(), today=None):
    """Norway / Denmark: most-viewed people of the actor and director categories (30-day pageviews) who have a film in the window, checked with the film query."""
    today = today or date.today()
    titles = [t for t in category_people(country) if " " in t and "(" not in t]
    views = pageviews(titles)
    ranked = sorted(titles, key=lambda t: -views.get(t, 0))[:40]
    ids = tp.qids_for([t.replace(" ", "_") for t in ranked])
    people = {q: {"title": t.replace("_", " ")} for t, q in ids.items()}
    since, until = (today - timedelta(days=60)).isoformat(), (today + timedelta(days=300)).isoformat()
    films = {}
    qs = list(people)
    for i in range(0, len(qs), 45):
        vals = " ".join(f"wd:{q}" for q in qs[i:i + 45])
        q = f"""SELECT ?p ?f ?pub WHERE {{ VALUES ?p {{ {vals} }} ?f (wdt:P161|wdt:P57) ?p; wdt:P577 ?pub.
          FILTER(?pub >= "{since}T00:00:00Z"^^xsd:dateTime && ?pub <= "{until}T00:00:00Z"^^xsd:dateTime) }}"""
        try:
            for b in rc.sparql(q):
                pq, d = rc.qid_of(rc.val(b, "p")), rc.val(b, "pub")[:10]
                if pq not in films or d < films[pq][0]:
                    films[pq] = (d, rc.qid_of(rc.val(b, "f")))
        except Exception as e:
            print(f"  nordic film query skipped: {e}", file=sys.stderr, flush=True)
    labels = {k: rc.label(e) for k, e in rc.entities({f for _, f in films.values()}, "labels").items()}
    skip = {e.lower() for e in exclude}
    out = []
    for q, (d, f) in films.items():
        t = people[q]["title"]
        ent = rc.entities([q], "claims").get(q, {})
        if rc.claim_values(ent.get("claims", {}), "P570") or t.lower() in skip:
            continue
        out.append({"name": t, "qid": q, "description": "", "film": labels.get(f, ""), "release": d, "country": country, "views_30d": views.get(t, 0)})
    if len(out) < top:  # Wikidata lists few Nordic film credits: top up with the most-viewed people of the category (no film listed yet)
        have = {r["name"] for r in out} | skip
        for t in ranked:
            if len(out) >= top + 6:
                break
            if t.replace("_", " ") not in have and views.get(t.replace("_", " "), 0) > 0:
                q = ids.get(t.replace(" ", "_")) or ids.get(t)
                if q:
                    out.append({"name": t.replace("_", " "), "qid": q, "description": "", "film": "", "release": "", "country": country, "views_30d": views.get(t.replace("_", " "), 0)})
    out.sort(key=lambda c: -c["views_30d"])
    print(f"  {country}: {len(out)} people (categories) with a film in the window; top: {', '.join(r['name'] for r in out[:top])}", flush=True)
    return out[:top]


def find(country, top=8, exclude=(), today=None):
    """The `top` hottest people of the country (hottest first), each checked against Wikidata citizenship so nobody of another country slips in."""
    rows = hot_people(country, top * 2, exclude, today)
    if country in NORDIC_CATEGORIES and len(rows) < top * 2:
        have = {r["name"] for r in rows}
        rows += [r for r in hot_nordic(country, top * 2, list(exclude) + list(have), today) if r["name"] not in have]
    real = countries_of([r["qid"] for r in rows])
    gone = {e.lower() for e in exclude}
    rows = [r for r in rows if real.get(r["qid"], country) == country and r["name"].lower() not in gone]
    rows.sort(key=lambda r: -r["views_30d"])
    return rows[:top]


def main(argv=None):
    """Label tracked people with their country; with --find, print the hot people of each audience country."""
    a = sys.argv[1:] if argv is None else argv
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import tracking
    cfg = tracking.load()
    done = fill_countries(cfg)
    if done:
        tracking.save(cfg)
    print(f"countries labelled: {len(done)}")
    if "--find" in a:
        for c in SHOWN:
            for r in find(c, 8, cfg["celebrities"]):
                print(f"{c}: {r['name']} ({r['views_30d']} views) - {r['film']} {r['release']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
