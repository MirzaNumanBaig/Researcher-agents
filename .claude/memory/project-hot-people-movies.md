---
name: project-hot-people-movies
description: 2026-11-11 additions - Openverse + credited news photos, hot people list, movies list with box office and critics
type: project
---

User asked (2026-11-11): more sources for featured images (credit in caption with source link is fine), a list of celebrities/directors/producers who are always popular or hot with their coming projects, and a movies list with box office, scope and critics overview.

**Built (branch feature/more-sources-hot-movies):** Openverse photo source, credited news-picture fallback (`credited_news_images`), `trending_people.py`, `movies.py`, workflow `hot-people-movies.yml`, dashboard tabs Hot people / Movies. Details in AGENTS.md.

**Why:** AI faces were poor; user wants real, correct faces and more coverage (13 of 40 celebrities had no Commons photo).
**How to apply:** crediting a news outlet is not a licence; the user accepted that risk. Wikidata SPARQL can be limited to 1 query a minute; keep queries few and batched. The sandbox IP gets throttled by Wikimedia; test heavy runs on GitHub Actions, not locally.
