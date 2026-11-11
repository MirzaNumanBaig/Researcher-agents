"""Movies in the news: release date, cast, budget, box office, scope and what critics say (standard library only).

Run:  python3 agents/movies.py [--max N]
Needs data/trending.json (agents/trending_people.py) and config.json. Writes
  data/movies.json          one entry per film
  data/research/MOVIES.md   readable table

Which films: the films (released in the last 4 months or coming in the next 14) of the people in the "hot" lists plus every celebrity tracked in config.json.
Where the facts come from (all public, each entry links its sources):
  Wikidata   release date, director, main cast, producer, budget (P2769), box office (P2142), Rotten Tomatoes / Metacritic scores (P444), language, countries
  Wikipedia  the film's infobox (budget and box office are usually more up to date than Wikidata) and the first paragraphs of its "Reception" section
             (the aggregate scores and the critics' consensus line). Wikipedia text is CC BY-SA 4.0: we keep only short factual lines and link the page.
Scope = how big the film is: scale from the budget (Blockbuster >= $150M, Big >= $60M, Mid >= $15M, Indie below) and reach (countries, language).
Verdict = gross / budget: Hit (>= 2.5x), Modest (>= 1.5x), Weak (below), "Too early" within 3 weeks of release, "Upcoming" before release.
"""
import html
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_celebrities as rc  # noqa: E402  (Wikidata helpers with polite retry)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "movies.json"
REPORT = ROOT / "data" / "research" / "MOVIES.md"
WP = "https://en.wikipedia.org/w/api.php"
FILM_KINDS = "wd:Q11424 wd:Q24869 wd:Q202866"
SCORE_BY = {"Q105584": "rotten_tomatoes", "Q150248": "metacritic", "Q37312": "imdb"}
UNITS = {"Q4917": "USD", "Q4916": "EUR", "Q25224": "GBP", "Q25236": "AUD"}


# ---------- money and verdicts (pure functions, tested) ----------
def money(text):
    """USD amount in dollars from infobox text like '$150 million', 'US$1.2 billion', '$12,345,678'. None when unclear (other currencies are not guessed)."""
    t = html.unescape(re.sub(r"<[^>]+>|\[\d+\]", "", text or "")).replace(",", "")
    m = re.search(r"(?:US|USD)?\s*\$\s*([\d.]+)\s*(billion|million|bn|m)?", t, re.I)
    if not m:
        m2 = re.search(r"\{\{\s*(?:US\$|USD|\$)\s*\|\s*([\d.]+)\s*\|?\s*(billion|million)?", text or "", re.I)
        m = m2
    if not m:
        return None
    try:
        n = float(m.group(1))
    except ValueError:
        return None
    unit = (m.group(2) or "").lower()
    return int(n * (1e9 if unit in ("billion", "bn") else 1e6 if unit in ("million", "m") else 1))


def fmt_money(n):
    if not n:
        return ""
    return f"${n / 1e9:.2f}B" if n >= 1e9 else f"${n / 1e6:.0f}M" if n >= 1e7 else f"${n / 1e6:.1f}M" if n >= 1e6 else f"${n / 1e3:.0f}k"


def scale(budget):
    if not budget:
        return ""
    return "Blockbuster" if budget >= 150e6 else "Big studio" if budget >= 60e6 else "Mid-budget" if budget >= 15e6 else "Indie / low budget"


def parse_date(text):
    """date from 'YYYY-MM-DD', or None for year-only / impossible dates such as 2026-00-00 (Wikidata uses those for unknown months)."""
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def verdict(release, gross, budget, today=None):
    today = today or date.today()
    if not release:
        return ""
    d = parse_date(release)
    if not d:
        return ""
    if d > today:
        return "Upcoming"
    if (today - d).days < 21 or not gross:
        return "Too early" if (today - d).days < 21 else "No figures yet"
    if not budget:
        return f"Grossed {fmt_money(gross)}"
    r = gross / budget
    return "Hit" if r >= 2.5 else "Modest" if r >= 1.5 else "Weak"


# ---------- Wikipedia ----------
def wp(**params):
    import urllib.parse
    return rc.fetch(WP + "?format=json&formatversion=2&" + urllib.parse.urlencode(params))


def clean(text):
    text = re.sub(r"<style.*?</style>|<sup.*?</sup>|<[^>]+>", "", text or "", flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def infobox(page):
    """{'budget': dollars|None, 'gross': dollars|None} from the film's infobox wikitext."""
    try:
        w = wp(action="parse", page=page, prop="wikitext", section=0, redirects=1)["parse"]["wikitext"]
    except Exception:
        return {}
    out = {}
    for key, names in (("budget", ("budget",)), ("gross", ("gross", "box_office"))):
        for n in names:
            m = re.search(rf"\|\s*{n}\s*=\s*(.+?)(?=\n\s*\||\n\}}\}})", w, re.S)
            if m:
                v = money(m.group(1))
                if v:
                    out[key] = v
                    break
    return out


def reception(page):
    """{'rotten_tomatoes': text, 'metacritic': text, 'consensus': text, 'overview': text} from the Reception section, best effort ({} when absent)."""
    try:
        secs = wp(action="parse", page=page, prop="sections", redirects=1)["parse"]["sections"]
        pick = next((s for s in secs if re.search(r"critical (response|reception)|^reception$", s["line"], re.I)), None)
        if not pick:
            return {}
        text = clean(wp(action="parse", page=page, prop="text", section=pick["index"], redirects=1)["parse"]["text"])
    except Exception:
        return {}
    out = {}
    rt = re.search(r"Rotten Tomatoes[^.]*?(\d{1,3}%)[^.]*?(\d[\d,]*)\s+(?:critic )?reviews?", text, re.I) or re.search(r"Rotten Tomatoes[^.]*?(\d{1,3}%)", text, re.I)
    if rt:
        out["rotten_tomatoes"] = rt.group(1) + (f" from {rt.group(2)} reviews" if rt.lastindex and rt.lastindex >= 2 else "")
    mc = re.search(r"Metacritic[^.]*?(?:score of |weighted average (?:score )?of )?(\d{1,3}) out of 100[^.]*?(\d+) critics?", text, re.I) or re.search(r"Metacritic[^.]*?(\d{1,3}) out of 100", text, re.I)
    if mc:
        out["metacritic"] = mc.group(1) + "/100" + (f" from {mc.group(2)} critics" if mc.lastindex and mc.lastindex >= 2 else "")
    cons = re.search(r"consensus[^\"“”]{0,60}[\"“]([^\"”]{20,320})[\"”]", text, re.I)
    if cons:
        out["consensus"] = cons.group(1).strip()
    sents = [s for s in re.split(r"(?<=[.!?])\s+", text) if 40 < len(s) < 330 and not re.search(r"Rotten Tomatoes|Metacritic|CinemaScore|reviews? from|based on \d", s)]
    if sents:
        out["overview"] = " ".join(sents[:2])[:480]
    return out


# ---------- Wikidata ----------
def amount(claims, pid):
    """Largest amount recorded for a property, as (USD dollars, was it USD)."""
    best = 0
    for c in rc.claim_values(claims, pid):
        v = c["mainsnak"]["datavalue"]["value"]
        unit = (v.get("unit") or "").rsplit("/", 1)[-1]
        if UNITS.get(unit) == "USD":
            try:
                best = max(best, int(float(v["amount"])))
            except (KeyError, ValueError):
                pass
    return best or None


def scores(claims):
    out = {}
    for c in rc.claim_values(claims, "P444"):
        by = [q["datavalue"]["value"].get("id") for q in c.get("qualifiers", {}).get("P447", []) if "datavalue" in q]
        for b in by:
            if b in SCORE_BY:
                out[SCORE_BY[b]] = str(c["mainsnak"]["datavalue"]["value"])
    return out


def film_details(qids):
    ents = rc.entities(qids, "claims|labels|sitelinks|descriptions")
    ids = set()
    for e in ents.values():
        for pid in ("P57", "P161", "P162", "P364", "P495", "P136"):
            ids |= {c["mainsnak"]["datavalue"]["value"]["id"] for c in rc.claim_values(e.get("claims", {}), pid)[:6]}
    names = {q: rc.label(e) for q, e in rc.entities(ids, "labels").items()}
    out = {}
    for q, e in ents.items():
        cl = e.get("claims", {})
        ids_of = lambda pid, n=6: [names.get(c["mainsnak"]["datavalue"]["value"]["id"], "") for c in rc.claim_values(cl, pid)[:n]]  # noqa: E731
        dates = sorted(rc.time_of([c["mainsnak"]]) for c in rc.claim_values(cl, "P577") if rc.time_of([c["mainsnak"]]))
        out[q] = {"qid": q, "title": rc.label(e), "release": dates[0] if dates else "", "director": [n for n in ids_of("P57", 3) if n],
                  "cast": [n for n in ids_of("P161", 6) if n], "producers": [n for n in ids_of("P162", 4) if n],
                  "language": [n for n in ids_of("P364", 2) if n], "countries": [n for n in ids_of("P495", 4) if n], "genres": [n for n in ids_of("P136", 3) if n],
                  "budget": amount(cl, "P2769"), "gross": amount(cl, "P2142"), "scores": scores(cl),
                  "wikipedia": (e.get("sitelinks", {}).get("enwiki") or {}).get("title", "")}
    return out


def tracked_films(names):
    """Film ids for celebrities tracked in config.json (acting, directing, producing), same window as the hot list."""
    since, until = (date.today() - timedelta(days=120)).isoformat(), (date.today() + timedelta(days=425)).isoformat()
    ids = []
    for i in range(0, len(names), 45):
        labels = " ".join('"' + n.replace('"', "") + '"@en' for n in names[i:i + 45])
        q = f"""SELECT DISTINCT ?f WHERE {{
          VALUES ?name {{ {labels} }} ?p rdfs:label ?name. ?p wdt:P31 wd:Q5.
          ?f (wdt:P161|wdt:P57|wdt:P162) ?p.
          ?f wdt:P31 ?kind. VALUES ?kind {{ {FILM_KINDS} }} ?f wdt:P577 ?pub.
          FILTER(?pub >= "{since}T00:00:00Z"^^xsd:dateTime && ?pub <= "{until}T00:00:00Z"^^xsd:dateTime) }}"""
        try:
            ids += [rc.qid_of(rc.val(b, "f")) for b in rc.sparql(q)]
        except Exception as e:
            print(f"  tracked film query failed: {e}", file=sys.stderr)
    return ids


def build(limit=60):
    trending = json.loads((ROOT / "data" / "trending.json").read_text()) if (ROOT / "data" / "trending.json").exists() else {}
    cfg = json.loads((ROOT / "config.json").read_text())
    who = {}  # film qid -> people who link it to our lists
    for key in ("hot_now", "always_popular", "filmmakers"):
        for p in trending.get(key, []):
            for f in p.get("films", []):
                who.setdefault(f["qid"], set()).add(p["name"])
    for q in tracked_films(cfg["celebrities"]):
        who.setdefault(q, set())
    qids = list(who)
    if not qids:
        return None
    details = film_details(qids)
    films = []
    for q, d in details.items():
        if not d["title"] or not parse_date(d["release"]):
            continue
        films.append(d)
    # rank: films with many tracked/hot people and recent/soon first
    today = date.today()
    films.sort(key=lambda d: (-len(who.get(d["qid"], ())), abs((parse_date(d["release"]) - today).days)))
    films = films[:limit]
    for d in films:
        page = d["wikipedia"]
        info = infobox(page) if page else {}
        d["budget"] = info.get("budget") or d["budget"]
        d["gross"] = info.get("gross") or d["gross"]
        rec = reception(page) if page and parse_date(d["release"]) <= today else {}
        d["critics"] = {**{k: v for k, v in d["scores"].items() if k in ("rotten_tomatoes", "metacritic")}, **rec}
        d["scale"] = scale(d["budget"])
        d["verdict"] = verdict(d["release"], d["gross"], d["budget"])
        d["multiple"] = round(d["gross"] / d["budget"], 2) if d["gross"] and d["budget"] else None
        d["people"] = sorted(who.get(d["qid"], ()))
        d["sources"] = {"wikidata": "https://www.wikidata.org/wiki/" + d["qid"], **({"wikipedia": "https://en.wikipedia.org/wiki/" + page.replace(" ", "_")} if page else {})}
        del d["scores"]
        print(f"  {d['title']:40} {d['release']} gross {fmt_money(d['gross']) or '-':>7} budget {fmt_money(d['budget']) or '-':>6} {d['verdict']}", flush=True)
    return {"updated": today.isoformat(), "films": films}


def report(data):
    lines = [f"# Movies ({data['updated']})", "", "Facts from Wikidata and Wikipedia (CC BY-SA); figures in US dollars when recorded.", "",
             "| Film | Release | Director | Budget | Box office | Scope | Verdict | Critics |", "|---|---|---|---|---|---|---|---|"]
    for d in data["films"]:
        c = d.get("critics", {})
        crit = "; ".join(x for x in (f"RT {c['rotten_tomatoes']}" if c.get("rotten_tomatoes") else "", f"MC {c['metacritic']}" if c.get("metacritic") else "") if x) or "-"
        lines.append(f"| {d['title']} | {d['release']} | {', '.join(d['director']) or '-'} | {fmt_money(d['budget']) or '-'} | {fmt_money(d['gross']) or '-'} | {d['scale'] or '-'} | {d['verdict'] or '-'} | {crit} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    limit = int(argv[argv.index("--max") + 1]) if "--max" in argv else 60
    data = build(limit)
    if not data:
        print("no films found; leaving the previous list in place", file=sys.stderr)
        return 1
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(report(data))
    print(f"{len(data['films'])} films written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
