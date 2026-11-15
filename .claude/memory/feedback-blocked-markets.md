---
name: feedback-blocked-markets
description: Owner removed Tamil/Indian (low-CPM market) people, films and posts on 2026-11-15; keep such people out
type: feedback
---

User (2026-11-15): remove Tamil/Indian and any other low-CPM-country actors, directors and celebrities from the dashboard and the blog, and trash their posts. Done: Sai Pallavi, Ravi Dubey, Nitesh Tiwari, Jithu Madhavan and the film "Ramayana: Rise of a Legend" removed from `config.json`; 29 of their WordPress posts trashed; their articles set to `status: removed`. `config.json` `blocked` lists them so `discover.py` (weekly add and Find trending) never re-adds them or films they direct or star in.

**Why:** AdSense CPM is low for those audiences; the site targets Australia and other high-CPM markets.
**How to apply:** when adding people or films, skip low-CPM-country industries (Indian film industries, etc.) and put anyone who slips in into `blocked`. A country filter in `trending_people.py` (Wikidata citizenship) is not built yet.
