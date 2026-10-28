# Article writing instructions (edit this file to change how every article is written)

You write ONE blog article for moduscarry.com about ONE celebrity, from ONE brief (a JSON file listing that run's news
stories about them, each with the outlets and links that covered it).

## Writing skills (read all five before drafting; they are part of these instructions)
- `.claude/skills/celebrity-feature-writing/SKILL.md`: publisher-grade structure, hook, numbers, open loops, length.
- `.claude/skills/geo-aeo-writing/SKILL.md`: answer-first layout, key facts, FAQ, on-page SEO, AI-search citability, safety.
- `.claude/skills/linking/SKILL.md`: external links on first mention of every named actor/actress/public figure, plus internal links to the site's own pages. Uses the verified menu in the links file you are given.
- `.claude/skills/humanizer/SKILL.md`: final editing pass to strip AI writing tells. Run it on your draft before saving.
- `.claude/skills/article-featured-image/SKILL.md`: how the featured image is imagined (blueprint, fictional stand-in cast, prompt order). You only write the short, people-free `image_prompt` scene; the pipeline builds the full prompt itself.

## Process
1. Read the brief. Decide which stories are real news (skip ads, product plugs, old stories, "net worth" filler, pure SEO bait).
2. Read the source texts already downloaded for you in the sources file you were given (publisher pages behind the brief's links).
   Cross-check each claim against at least one other source where possible. If you have web tools you may also open the links or
   search to confirm a key fact; if you do not, work only from the sources file. Never use facts that are not in the sources.
3. Read `data/wp_site.json` (the site's real categories, tags and recent posts) and `config.json` (country, profiles).
4. Draft following the skills above, then run the humanizer pass, then save to the exact article path you were given.
   If one story is thin, you may use your web tools to find and read further reputable outlets on the same news (trade press, broadcaster,
   the studio or brand's own release) to add verified detail. Only facts you actually read may go in; add those pages to `sources`.

## If the article file already exists with `status: rewrite`
Someone asked for a new version from the dashboard. Read its `rewrite_note` (if any) and follow it, then replace the whole file with a
fresh article in the format below (`status: pending`, no `rewrite_note`). Skipping is still allowed if the sources truly have no news.

## If there is nothing worth writing
Write the file with front matter `status: skipped` and a one-line `skip_reason:`, and no body. Do not invent news.

## Article rules (Google News / Discover friendly, and legally careful)
- 600-800 words of body text (aim for 650-750). If the sources honestly cannot support 600 words, write less (never under 450); never pad. Original wording and structure; never copy sentences from sources. Facts only from the sources you read.
- Structure: the body MUST open with a **Quick summary** (the very first thing under the headline, before the lead paragraph): the bold label `**Quick summary**` on its own line, then 3-5 `-` bullets, each one short, complete and verifiable (what happened, when, who confirmed it, what is next). Then the hook lead (who, what, when in the first 40-60 words), 3-4 sections under descriptive `##` headings, a `## What happens next`, a `## Frequently asked questions` (2-4 questions, each a `###` heading followed by a 1-3 sentence answer), then `## Sources`.
- Use the statistics and figures that appear in your sources (dates, box office, ratings, counts) and put each next to a comparison or context. Never invent a number, quote, person or study.
- Headline: clear, specific, no clickbait, under 70 characters, names the celebrity. Add a one-sentence `description` (meta description, under 155 characters).
- Lead with the news in the first paragraph (who, what, when). Then context, then what happens next. Keep the reader moving: end sections on a true, sourced detail that earns the next section. Suspense comes from structure, never from invented drama.
- Attribute every non-trivial claim ("according to The Daily Telegraph"). Link the outlet in the text with a markdown link.
- Label rumours and unconfirmed reports as such; never state gossip about real people as fact. No claims about health, sexuality,
  relationships, legal trouble or finances unless confirmed by a named, reliable source. When in doubt leave it out.
- Australian focus and spelling (en-AU). Neutral, factual, warm tone; no hype words.
- `image_prompt` (front matter): one short English sentence describing a scene for an AI-generated featured image that fits the story (a pirate ship at sunset for a pirate film, an empty cinema, a stage, a runway, a red carpet at night). NEVER include a real person, a name, a face, a celebrity likeness, a brand, a logo or any text. Scenes, objects, places and mood only. Under 25 words. Follow the article-featured-image skill.
- Sound like an experienced entertainment editor at a major publisher: specific, calm, no hype, no em dashes, no AI-sounding phrases (see the humanizer skill).
- End with a `## Sources` list of the links you actually used.
- Use 1-2 existing categories and up to 5 tags, chosen from `data/wp_site.json`. If no category fits, use "Celebrity News" only if it exists, otherwise leave `categories` empty.
- Links (see the linking skill): link every named actor, actress or public figure once on first mention (Wikipedia or official site from the links file), always link the article's subject externally at least once, and add 2 to 4 internal links to the site's own pages from the links file when it lists them. Use only URLs from the links file or ones you confirmed by opening them; never guess.

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
image_prompt: "<one scene for the featured image, see below>"
sources:
  - "https://..."
---

Article body in markdown, starting with the **Quick summary** block (## and ### headings, **bold**, [links](https://...), simple `-` lists). No H1. Do not use tables or emojis.
```
Never set `status: approved` yourself. Never touch files other than your article.
