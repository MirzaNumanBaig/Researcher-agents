---
name: feedback-image-policy
description: Image rules (user, 2026-11-15) - every post needs a real featured image, no AI images, reference/news pictures credited, no image = not live
type: feedback
---

CURRENT RULES (user, 2026-11-15, these win over everything below):
1. Every post must have a featured image. A post without one must NOT be live: it is held as Pending review and goes live by itself once its image is added (`publish_wordpress.py`: `has_image()`, new posts sent as pending, live ones without an image moved back to pending; the check runs hourly).
2. NO AI images. Not now, not as a fallback (`ai_images: false`). The user will say later when AI images are to be removed for good.
3. Use the article's own reference image (the picture of the news pages it cites, and the blog's image) when there is no free photo. Order: free-licence Commons photo, Openverse photo, the brief's news picture (face-checked), then `source_photo()` = lead picture (og:image, at least 400 px, no face check) of the cited pages. Always credit the outlet with a link to its story in the caption (user, earlier: "credit in the caption using their source link").
4. Fix missing images for every post, old ones too: sent posts without a picture are retried for 7 days (`RETRY_HOURS` 168) and the hourly send run fills them.
5. Remove a picture when its owner asks.

Older notes follow.

UPDATE 2026-11-09 (user): AI images look bad (wrong faces, environment, camera angle) and hurt monetisation, so featured images are real open-licence Wikimedia Commons photos of the named celebrity (CC0/PD/CC BY/CC BY-SA, credit shown). A photo is reused (least recently used) before any AI picture is made; AI pictures are off (`ai_images: false`) unless a person has no free photo and the user turns them back on. Everything below applies only to the AI fallback.

Featured AI images must come from a free Cloudflare Workers AI model (inside 10,000 free neurons/day per account; default FLUX.2 klein 4B), generated from the story. People in a picture are ONLY fictional stand-ins from `agents/imagegen/cast.json`, never a real person's name, face or likeness. Do not reuse publisher/news photos on the site; the collected news image links are research references (blueprint of composition and body language) for the pipeline only. Alt text is a factual sentence. Since 2026-10-28 there is NO visible AI caption or credit by default (user decision, `IMG_CAPTION`); the AI flag stays in `articles/image-meta/*.json`. Sensitive stories (death, illness, legal, abuse, minors) get a calm symbolic scene with no people.

**Why:** Google Publisher Policies do not allow content that infringes copyright, so copying outlet photos risks ad blocking or account suspension; a credit or link-back is not permission. AI images of real celebrities risk misleading readers and right-of-publicity claims. Photorealistic stand-ins without a visible label could still be taken for the real people in a story (ad-policy and disclosure risk); the user was warned and chose no visible label, offering an invisible file tag or short credit as options.

**How to apply:** Only offer or enable free models (klein 4B, schnell); do not reword prompts to get past Cloudflare's safety filter. Recheck model licences (Black Forest Labs terms) before relying on them commercially.
