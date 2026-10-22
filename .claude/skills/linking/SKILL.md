---
name: linking
description: Add external links to every named actor, actress or other public figure and internal links to the site's own related pages. Use on every article, after drafting and before the humanizer pass.
---

# Linking rules (external people links + internal links)

Links make an article trustworthy to readers and to search and AI engines. They must also be real. A broken or invented link is worse than no link.

## Where the links come from
Before you write, read `work/<batch>-<celebrity>/links.md` (the path is in your instructions). It was built just now and lists:
- **External links to people**: Wikipedia for the subject and for other people named in the coverage, plus the subject's official website and verified social profiles from `config.json`.
- **Internal links**: the site's tag archive for the subject, category pages, related published posts and the home page, all from `data/wp_site.json` (published posts only, so every link is live).

Use ONLY URLs from that file for people and for the site's own pages. If a person you want to link is not in it, you may check Wikipedia yourself with your web tools (open `https://en.wikipedia.org/wiki/First_Last` and confirm it is that person). If you cannot confirm it, do not link. Never guess a URL.

## External links (people)
- Every actor, actress, director, musician, presenter or other public figure named in the article gets an external link **on their first mention in the body** (not in the headline, summary bullets or FAQ headings). Link each person once.
- The article's subject (the celebrity in the brief) always gets at least one external link: Wikipedia first, or the official website when it is the better source for the point being made. Use the official social profile only when you quote or cite something posted there.
- Link text is the person's name exactly as written ("Hugh Jackman"), never "click here" or "this".
- External links open the outlet or reference page. Keep sourced claims linked to the outlet that reported them as well (that is separate from the people links).
- Link working public figures (including young actors with a Wikipedia page). Do not link private individuals, relatives or children who are not public figures, and do not link a name that only appears inside a quote.

## Internal links
- Use 2 to 4 internal links per article when `links.md` offers that many (at least 1 whenever it lists any), chosen from the internal list.
- Always include the subject's tag archive when it exists. Add a relevant category page and any genuinely related published post (same person, same film or show, same event).
- Descriptive anchor text: "our Hugh Jackman coverage", "more movie news", the related post's title. Never "here".
- Place them where a reader would want to follow them (a sentence about the subject's earlier work, a closing "More on ..." line in What happens next). Do not stack links together or put them in the quick summary.
- If `links.md` has no internal links beyond the home page, link the home page once at most and move on. Do not invent post URLs.

## Check before saving
- Each named person has a link on first mention, or you decided they should not be linked (private individual, no verified page).
- Every URL appears in `links.md` or was confirmed with your web tools.
- No link in the headline, quick summary bullets or `###` FAQ headings.
- Internal links: 2 to 4 when available, descriptive, relevant.
