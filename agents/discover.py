"""Find popular people and films that are not tracked yet and add them to config.json (people -> "celebrities", films -> "movies").

Reads data/trending.json (Wikipedia most-viewed pages + Wikidata roles, built by trending_people.py) and data/movies.json (built by movies.py).
Ranking is by Wikipedia page views this week ("how much people are looking them up"); a film scores the views of the people attached to it.
Every addition is stamped in config.json "added" so the dashboard can show a "New" tag; collect.yml then searches news for it like for anyone else.

  python agents/discover.py [--mode all|movies] [--people 8] [--movies 10]
mode "movies" (the weekly run) adds only films that have a tracked or hot person in them; mode "all" (the dashboard button) also adds hot people.
"""
import json
import sys
from datetime import date, timedelta

import tracking

MAX_MOVIES = 40  # films tracked at once; films released more than KEEP_DAYS ago drop out of the list
KEEP_DAYS = 120


def decent_title(t):
    """One-word titles ("It", "Us", "Butterfly") would match unrelated headlines; only titles of two or more words are followed."""
    return len(t.split()) >= 2


def pick_people(trend, cfg, n):
    have = {c.lower() for c in cfg["celebrities"]} | {b.lower() for b in cfg.get("blocked", [])}  # blocked = the owner removed them (low-CPM markets); never re-added
    pool, seen = [], set()
    for key in ("hot_now", "always_popular", "filmmakers"):
        for p in trend.get(key, []):
            if p["qid"] in seen or p["name"].lower() in have or " " not in p["name"].strip():
                continue
            seen.add(p["qid"])
            pool.append(p)
    pool.sort(key=lambda p: -(p.get("views_7d") or 0))
    return pool[:n]


def film_score(f, views, tracked):
    names = set(f.get("people", [])) | set(f.get("director", [])) | set(f.get("cast", []))
    return sum(views.get(n, 0) for n in names), bool(names & tracked)


def pick_movies(movies, trend, cfg, n, need_tracked, today):
    views = {p["name"]: p.get("views_7d") or 0 for k in ("hot_now", "always_popular", "filmmakers") for p in trend.get(k, [])}
    tracked, have = set(cfg["celebrities"]), {m.lower() for m in cfg.get("movies", [])} | {b.lower() for b in cfg.get("blocked", [])}
    blocked = {b.lower() for b in cfg.get("blocked", [])}
    out = []
    for f in movies.get("films", []):
        d = f.get("director") or []
        names = ([d] if isinstance(d, str) else list(d)) + list(f.get("cast") or [])
        if any(str(n).lower() in blocked for n in names):
            continue  # a film made by or starring someone the owner blocked
        try:
            rel = date.fromisoformat(f["release"])
        except ValueError:
            continue
        if f["title"].lower() in have or not decent_title(f["title"]) or not (today - timedelta(days=60) <= rel <= today + timedelta(days=300)):
            continue
        score, has_tracked = film_score(f, views, tracked)
        if need_tracked and not has_tracked:
            continue
        if score or has_tracked:
            out.append((score, f))
    out.sort(key=lambda x: (-x[0], x[1]["release"]))
    return [f for _, f in out[:n]]


def run(mode="all", people=4, movies=10, today=None):  # people = per country
    today = today or date.today()
    cfg = tracking.load()
    trend = json.loads((tracking.ROOT / "data" / "trending.json").read_text()) if (tracking.ROOT / "data" / "trending.json").exists() else {}
    films = json.loads((tracking.ROOT / "data" / "movies.json").read_text()) if (tracking.ROOT / "data" / "movies.json").exists() else {}
    added = cfg.setdefault("added", {})
    log = {"people": [], "movies": [], "dropped": []}

    if mode == "all":  # people only from the audience countries (Australia, UK, Norway, Denmark, Canada): hot now + a film coming out
        import countries
        taken = list(cfg["celebrities"]) + list(cfg.get("blocked", []))
        for country in countries.SHOWN:
            for p in countries.find(country, people, taken):
                cfg["celebrities"].append(p["name"])
                cfg.setdefault("countries", {})[p["name"]] = country
                taken.append(p["name"])
                added[p["name"]] = today.isoformat()
                log["people"].append(p["name"])
                if p["name"].split()[-1].lower() in {"hall", "cook", "grace", "hardy", "fox", "short"}:
                    cfg.setdefault("headline_full_name_only", []).append(p["name"])
        countries.fill_countries(cfg)  # label anyone still without a country

    for f in pick_movies(films, trend, cfg, movies, mode != "all", today):
        cfg.setdefault("movies", []).append(f["title"])
        added[f["title"]] = today.isoformat()
        log["movies"].append(f["title"])

    release = {f["title"]: f["release"] for f in films.get("films", [])}  # old films leave the list so it stays current
    keep = []
    for m in cfg.get("movies", []):
        r = release.get(m)
        if r and r < (today - timedelta(days=KEEP_DAYS)).isoformat() and m not in log["movies"]:
            log["dropped"].append(m)
        else:
            keep.append(m)
    cfg["movies"] = keep[-MAX_MOVIES:]
    if len(keep) > MAX_MOVIES:
        log["dropped"] += keep[:-MAX_MOVIES]
    live = set(cfg["celebrities"]) | set(cfg["movies"])
    cfg["added"] = {k: v for k, v in added.items() if k in live and v >= (today - timedelta(days=30)).isoformat()}
    if log["people"] or log["movies"] or log["dropped"] or cfg.get("countries") != tracking.load().get("countries"):
        tracking.save(cfg)
    return log


def main(argv=None):
    a = sys.argv[1:] if argv is None else argv
    opt = lambda k, d: a[a.index(k) + 1] if k in a else d  # noqa: E731
    log = run(opt("--mode", "all"), int(opt("--people", 4)), int(opt("--movies", 10)))
    print(f"added people: {', '.join(log['people']) or '-'}")
    print(f"added films:  {', '.join(log['movies']) or '-'}")
    print(f"dropped films: {', '.join(log['dropped']) or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
