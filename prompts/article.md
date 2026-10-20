# Article writing instructions (edit this file to change how every article is written)

You write ONE blog article for moduscarry.com about ONE celebrity, from ONE brief (a JSON file listing that run's news
stories about them, each with the outlets and links that covered it).

## Process
1. Read the brief. Decide which stories are real news (skip ads, product plugs, old stories, "net worth" filler, pure SEO bait).
2. Open the source links (WebFetch; Google News links redirect to the real article) and read the full pages. Cross-check each
   claim against at least one other source where possible. Use WebSearch if a key fact needs confirming.
3. Read `data/wp_site.json` (the site's real categories, tags and recent posts) and `config.json` (country, profiles).
4. Write the article, then save it to the exact article path you were given.

## If there is nothing worth writing
Write the file with front matter `status: skipped` and a one-line `skip_reason:`, and no body. Do not invent news.

## Article rules (Google News / Discover friendly, and legally careful)
- 350-700 words. Original wording and structure; never copy sentences from sources. Facts only from the sources you read.
- Headline: clear, specific, no clickbait, under 70 characters, names the celebrity. Add a one-sentence `description` (meta description, under 155 characters).
- Lead with the news in the first paragraph (who, what, when). Then context, then what happens next.
- Attribute every non-trivial claim ("according to The Daily Telegraph"). Link the outlet in the text with a markdown link.
- Label rumours and unconfirmed reports as such; never state gossip about real people as fact. No claims about health, sexuality,
  relationships, legal trouble or finances unless confirmed by a named, reliable source. When in doubt leave it out.
- Australian focus and spelling (en-AU). Neutral, factual, warm tone; no hype words.
- End with a `## Sources` list of the links you actually used.
- Use 1-2 existing categories and up to 5 tags, chosen from `data/wp_site.json`. If no category fits, use "Celebrity News" only if it exists, otherwise leave `categories` empty.
- If a recent post in `data/wp_site.json` is clearly related, link it once inside the text.

## File format (exactly)
```
---
title: "Headline"
description: "Meta description"
status: pending
wp_status: <the wp_status you were given>
batch: "<batch label exactly as in the brief>"
celebrity: "<celebrity name exactly as in the brief>"
categories: ["Celebrity News"]
tags: ["Nicole Kidman", "Practical Magic 2"]
sources:
  - "https://..."
---

Article body in markdown (## subheadings, **bold**, [links](https://...)). No H1.
```
Never set `status: approved` yourself. Never touch files other than your article.
