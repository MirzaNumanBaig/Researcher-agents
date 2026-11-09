---
name: feedback-image-policy
description: Image rules - real open-licence Commons photos first (user, 2026-11-09: AI images are bad); AI only as a fallback; never copy publisher photos
type: feedback
---

UPDATE 2026-11-09 (user): AI images look bad (wrong faces, environment, camera angle) and hurt monetisation, so featured images are real open-licence Wikimedia Commons photos of the named celebrity (CC0/PD/CC BY/CC BY-SA, credit shown). A photo is reused (least recently used) before any AI picture is made; AI pictures are off (`ai_images: false`) unless a person has no free photo and the user turns them back on. Everything below applies only to the AI fallback.

Featured AI images must come from a free Cloudflare Workers AI model (inside 10,000 free neurons/day per account; default FLUX.2 klein 4B), generated from the story. People in a picture are ONLY fictional stand-ins from `agents/imagegen/cast.json`, never a real person's name, face or likeness. Do not reuse publisher/news photos on the site; the collected news image links are research references (blueprint of composition and body language) for the pipeline only. Alt text is a factual sentence. Since 2026-10-28 there is NO visible AI caption or credit by default (user decision, `IMG_CAPTION`); the AI flag stays in `articles/image-meta/*.json`. Sensitive stories (death, illness, legal, abuse, minors) get a calm symbolic scene with no people.

**Why:** Google Publisher Policies do not allow content that infringes copyright, so copying outlet photos risks ad blocking or account suspension; a credit or link-back is not permission. AI images of real celebrities risk misleading readers and right-of-publicity claims. Photorealistic stand-ins without a visible label could still be taken for the real people in a story (ad-policy and disclosure risk); the user was warned and chose no visible label, offering an invisible file tag or short credit as options.

**How to apply:** Only offer or enable free models (klein 4B, schnell); do not reword prompts to get past Cloudflare's safety filter. Recheck model licences (Black Forest Labs terms) before relying on them commercially.
