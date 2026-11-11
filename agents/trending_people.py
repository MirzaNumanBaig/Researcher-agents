"""Who is hot right now, and who is always in the news: actors, directors, producers, writers, musicians (standard library only).

Run:  python3 agents/trending_people.py [--top N]
Writes  data/trending.json   hot_now / always_popular / filmmakers lists, each person with roles, views, trend and their upcoming + recent films
        data/research/TRENDING.md   the same as a readable report

How it decides (all public data, nothing scraped):
  - Wikipedia's own "most viewed articles" lists (Wikimedia Pageviews API): the last 7 days = what people look up NOW, the last full month = who is ALWAYS popular
  - Wikidata says which of those articles are people in film/TV/music (actor, director, producer, screenwriter, singer, comedian, model ...)
  - trend = views per day this week divided by views per day last month (above 1.3 = rising, 2+ = spiking)
  - Wikidata lists the films each person acts in, directs or produces that come out between ~4 months ago and ~14 months ahead
  - people not yet in config.json are flagged "not tracked", so the owner can add them (dashboard Setup, or the add_celebrity MCP tool)
"""
import json
import math
import re
import sys
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_celebrities as rc  # noqa: E402  (Wikidata helpers with polite retry)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "trending.json"
REPORT = ROOT / "data" / "research" / "TRENDING.md"
PV = "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/all-access"
SKIP = re.compile(r"^(Main_Page|Special:|Wikipedia:|Portal:|Help:|File:|Category:|Template:|Talk:|-$)")
ROLES = {  # occupation id -> role we show
    "Q33999": "actor", "Q10800557": "actor", "Q10798782": "actor", "Q2405480": "actor", "Q2259451": "actor", "Q622807": "actor", "Q1053574": "actor",
    "Q2526255": "director", "Q3455803": "director", "Q28389": "writer", "Q4263842": "writer", "Q3282637": "producer", "Q578109": "producer",
    "Q177220": "singer", "Q639669": "musician", "Q245068": "comedian",
}
FILM_KINDS = "wd:Q11424 wd:Q24869 wd:Q202866"  # film, feature film, animated film
AUSTRALIA = "Q408"
NOT_ENTERTAINER = re.compile(r"politician|senator|governor|president|minister|secretary|congress|businessperson|businessman|businesswoman|journalist|footballer|cricketer|athlete", re.I)


def days(n):
    return [date.today() - timedelta(days=i) for i in range(2, n + 2)]  # the last day or two may not be published yet


def top_articles(path):
    try:
        return {a["article"]: a["views"] for a in rc.fetch(f"{PV}/{path}")["items"][0]["articles"] if not SKIP.match(a["article"])}
    except Exception as e:  # a missing day must not stop the run
        print(f"  pageviews {path}: {e}", file=sys.stderr)
        return {}


def popularity():
    """({title: views in the last 7 days}, {title: views last full month}, days of data this week)."""
    week, n = {}, 0
    for d in days(7):
        t = top_articles(f"{d.year}/{d.month:02d}/{d.day:02d}")
        n += bool(t)
        for k, v in t.items():
            week[k] = week.get(k, 0) + v
    first = date.today().replace(day=1) - timedelta(days=1)  # last day of the previous month
    month = top_articles(f"{first.year}/{first.month:02d}/all-days")
    return week, month, n


WP_API = "https://en.wikipedia.org/w/api.php"


def qids_for(titles):
    """{wikipedia title: Wikidata id} through Wikipedia's own API (50 titles per call, generous limits): far lighter on Wikidata than fetching entities."""
    out = {}
    titles = list(titles)
    for i in range(0, len(titles), 50):
        chunk = [t.replace("_", " ") for t in titles[i:i + 50]]
        print(f"  finding ids {i}-{i + len(chunk)} of {len(titles)}", flush=True)
        try:
            data = rc.fetch(WP_API + "?format=json&formatversion=2&action=query&prop=pageprops&ppprop=wikibase_item&redirects=1&titles=" + urllib.parse.quote("|".join(chunk)))["query"]
        except Exception as e:  # one failed batch must not lose the whole run
            print(f"  batch skipped: {e}", file=sys.stderr, flush=True)
            continue
        back = {}  # final page title -> the titles we asked for
        for t in chunk:
            cur = t
            for step in ("normalized", "redirects"):
                cur = next((m["to"] for m in data.get(step, []) if m["from"] == cur), cur)
            back.setdefault(cur, []).append(t)
        for pg in data.get("pages", []):
            q = (pg.get("pageprops") or {}).get("wikibase_item")
            for t in back.get(pg.get("title"), []):
                if q:
                    out[t.replace(" ", "_")] = q
    return out


def people_for(titles):
    """{qid: {qid, page, name, description, roles, australian}} for the living film/TV/music people among the Wikipedia titles (ONE SPARQL query per 150)."""
    ids = qids_for(titles)
    page_of = {}
    for t, q in ids.items():
        page_of.setdefault(q, t)
    found = {}
    qs = list(page_of)
    occ = " ".join(f"wd:{o}" for o in ROLES)
    for i in range(0, len(qs), 150):
        vals = " ".join(f"wd:{q}" for q in qs[i:i + 150])
        query = f"""SELECT ?p ?pLabel ?pDescription ?occ (COUNT(?aus) AS ?au) WHERE {{
          VALUES ?p {{ {vals} }} ?p wdt:P31 wd:Q5; wdt:P106 ?occ. VALUES ?occ {{ {occ} }}
          FILTER NOT EXISTS {{ ?p wdt:P570 ?died }}
          OPTIONAL {{ ?p wdt:P27 ?aus. FILTER(?aus = wd:{AUSTRALIA}) }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }} }} GROUP BY ?p ?pLabel ?pDescription ?occ"""
        try:
            rows = rc.sparql(query)
        except Exception as e:
            print(f"  people query skipped: {e}", file=sys.stderr, flush=True)
            continue
        for b in rows:
            q = rc.qid_of(rc.val(b, "p"))
            page = page_of.get(q, "")
            desc = rc.val(b, "pDescription")
            if not rc.JOB.search(desc) or NOT_ENTERTAINER.search(desc):  # politicians and others whose Wikidata lists an acting/producing credit are not what this list is for
                continue
            e = found.setdefault(q, {"qid": q, "page": page, "name": (lambda n: page.replace("_", " ") if not n or re.fullmatch(r"Q\d+", n) else n)(rc.val(b, "pLabel")), "description": desc,
                                     "roles": [], "australian": False})
            r = ROLES.get(rc.qid_of(rc.val(b, "occ")))
            if r and r not in e["roles"]:
                e["roles"].append(r)
            e["australian"] = e["australian"] or rc.val(b, "au") not in ("", "0")
    return found


def films_for(people):
    """{person qid: [{title, qid, date}]}: films released between four months ago and 14 months ahead (acting, directing or producing)."""
    since, until = (date.today() - timedelta(days=120)).isoformat(), (date.today() + timedelta(days=425)).isoformat()
    out = {q: {} for q in people}
    ids = list(people)
    for i in range(0, len(ids), 45):
        vals = " ".join(f"wd:{q}" for q in ids[i:i + 45])
        query = f"""SELECT ?p ?f ?pub WHERE {{
          VALUES ?p {{ {vals} }} ?f (wdt:P161|wdt:P57|wdt:P162) ?p.
          ?f wdt:P31 ?kind. VALUES ?kind {{ {FILM_KINDS} }} ?f wdt:P577 ?pub.
          FILTER(?pub >= "{since}T00:00:00Z"^^xsd:dateTime && ?pub <= "{until}T00:00:00Z"^^xsd:dateTime)
          FILTER NOT EXISTS {{ ?f wdt:P577 ?early. FILTER(?early < "{since}T00:00:00Z"^^xsd:dateTime) }} }}"""
        try:
            rows = rc.sparql(query)
        except Exception as e:
            print(f"  film query failed: {e}", file=sys.stderr, flush=True)
            continue
        for b in rows:
            f = rc.qid_of(rc.val(b, "f"))
            d = rc.val(b, "pub")[:10]
            if f and re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])", d):
                out[rc.qid_of(rc.val(b, "p"))][f] = d
    labels = {q: rc.label(e) for q, e in rc.entities({f for fl in out.values() for f in fl}, "labels").items()}
    return {q: [{"title": labels[f], "qid": f, "date": d} for f, d in fl.items() if labels.get(f)] for q, fl in out.items()}


def build(top=40, pool_size=350):
    cfg = json.loads((ROOT / "config.json").read_text())
    tracked = {n.lower() for n in cfg["celebrities"]}
    week, month, n_days = popularity()
    print(f"pageviews: {len(week)} pages this week ({n_days} days), {len(month)} last month", flush=True)
    if not week and not month:
        print("no pageview data; leaving the previous list in place", file=sys.stderr)
        return None
    pool = [t for t, _ in sorted(week.items(), key=lambda kv: -kv[1])[:pool_size]] + [t for t, _ in sorted(month.items(), key=lambda kv: -kv[1])[:pool_size]]
    people = people_for(dict.fromkeys(pool))
    rows = []
    for p in people.values():
        t = p.pop("page")
        wk, mo = week.get(t, 0), month.get(t, 0)
        per_week = wk / max(n_days, 1) * 7
        per_month = mo / 30.0 * 7
        trend = round(per_week / per_month, 2) if per_month else None
        rows.append({**p, "wikipedia": "https://en.wikipedia.org/wiki/" + t, "views_7d": wk, "views_month": mo, "trend": trend, "tracked": p["name"].lower() in tracked})
    hot = sorted(rows, key=lambda r: -(r["views_7d"] or 0))[:top]
    always = sorted((r for r in rows if r["views_month"]), key=lambda r: -r["views_month"])[:top]
    makers = sorted((r for r in rows if {"director", "producer", "writer"} & set(r["roles"])), key=lambda r: -max(r["views_7d"] or 0, (r["views_month"] or 0) / 4))[:top]
    chosen = {r["qid"]: r for r in hot + always + makers}
    print(f"{len(chosen)} people chosen; looking up their films", flush=True)
    films = films_for(chosen)
    for q, r in chosen.items():
        r["films"] = sorted(films.get(q, []), key=lambda f: f["date"])
    data = {"updated": date.today().isoformat(), "pageview_days": n_days, "hot_now": hot, "always_popular": always, "filmmakers": makers,
            "not_tracked": [r["name"] for r in hot + always + makers if not r["tracked"]][:60]}
    data["not_tracked"] = list(dict.fromkeys(data["not_tracked"]))
    return data


def k(n):
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}k" if n >= 1e3 else str(n)


def report(data):
    lines = [f"# Hot people ({data['updated']})", "", "Source: Wikipedia most-viewed pages (last 7 days vs last full month) + Wikidata. Trend = views per day this week / last month.", ""]
    for key, title in (("hot_now", "In the news right now"), ("always_popular", "Always popular"), ("filmmakers", "Directors, producers and writers")):
        lines += [f"## {title}", "", "| Person | Roles | Views 7d | Views month | Trend | Tracked | Films (release date) |", "|---|---|---|---|---|---|---|"]
        for r in data[key][:25]:
            films = "; ".join(f"{f['title']} ({f['date']})" for f in r.get("films", [])[:4]) or "-"
            lines.append(f"| [{r['name']}]({r['wikipedia']}) | {', '.join(r['roles'])} | {k(r['views_7d'])} | {k(r['views_month'])} | {r['trend'] if r['trend'] is not None else '-'} | {'yes' if r['tracked'] else 'no'} | {films} |")
        lines.append("")
    if data["not_tracked"]:
        lines += ["## Not tracked yet (candidates to add to config.json)", "", ", ".join(data["not_tracked"][:40]), ""]
    return "\n".join(lines)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    top = int(argv[argv.index("--top") + 1]) if "--top" in argv else 40
    data = build(top, int(argv[argv.index("--pool") + 1]) if "--pool" in argv else 350)
    if not data:
        return 1
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(report(data))
    print(f"hot now: {len(data['hot_now'])}, always popular: {len(data['always_popular'])}, filmmakers: {len(data['filmmakers'])}, not tracked: {len(data['not_tracked'])}")
    for r in data["hot_now"][:10]:
        print(f"  {r['name']:28} {','.join(r['roles']):22} {k(r['views_7d']):>6} trend {r['trend']} {'(tracked)' if r['tracked'] else ''} films: {len(r.get('films', []))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
