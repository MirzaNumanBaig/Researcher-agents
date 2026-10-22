---
name: geo-aeo-writing
description: Structure and write news articles so they rank in Google (SEO, Discover, Top Stories) and get cited by AI answer engines (Google AI Overviews and AI Mode, ChatGPT search, Perplexity). Use on every article.
---

# SEO + AEO + GEO writing rules

Google's own position: optimising for AI search is still SEO. The same fundamentals apply: helpful, original, well-sourced, clearly structured pages. Do not use tricks (keyword stuffing, hidden text, fake freshness, `llms.txt` games). Pass the "Who / How / Why" test: who wrote it (byline), how it was made (sourced from named outlets), why it exists (to inform readers).

## Answer-first structure (what AI engines extract)
1. **Lead (first 40-60 words)**: who, what, when, where, in plain words. A reader and an AI engine should get the whole story from this paragraph.
2. **Key facts block** straight after the lead: a short list of 3-5 verifiable facts (date, place, figure, who confirmed it). Short, self-contained lines.
3. **Self-contained sections of about 100-170 words**, each under a descriptive H2 that could stand alone as an answer. Open each section with its direct answer, then support it. Prefer question-style H2s where natural ("When is Treasure Island released?", "Who is in the cast?").
4. **Context and numbers**: figures, dates, box-office, ratings, career milestones, with the source named in the sentence.
5. **What happens next**: dated, sourced next steps only.
6. **FAQ** (2-4 questions) near the end: real questions a reader would type, each answered in 1-3 sentences that repeat the key fact with the celebrity's full name (AI engines lift these). Answers must be fully supported by the article above.
7. **Sources** list.

## On-page SEO
- Primary keyword = the celebrity name + the news topic. Put it in the title, the first sentence and one H2. Use natural variants; no stuffing.
- Title under 70 characters; `description` under 155 characters, written as a promise of the news, not clickbait.
- 3-4 short internal links to related posts from `data/wp_site.json` where genuinely related (never forced). External links only to the outlets you cite.
- Short paragraphs (2-4 sentences). Scannable. Sentence-case headings.
- Name entities in full on first mention (full name, film or show title, brand, place) so search and AI engines can match them. Add the production or brand names that appear in the sources.
- Freshness: put the event date in the text ("on 22 October"), not just "today".

## Citability
- One claim per sentence where possible, each with its source in the sentence ("according to Variety").
- Prefer concrete numbers over adjectives. Never invent numbers; use only what the sources contain.
- Original angle without inventing facts: compare the new news with earlier, sourced events from the brief or the site's recent posts (a release slip, a previous role, a past announcement).

## E-E-A-T and safety (celebrity niche is high-risk)
- Attribute everything non-trivial. Label rumours as reports, not facts.
- Nothing about health, relationships, sexuality, legal trouble, finances or children unless confirmed by a named, reliable outlet and clearly newsworthy. Minors: keep it to what the parent or child said publicly in a sourced interview.
- No copying: original wording, short quotes only (a sentence at most) and always attributed.
