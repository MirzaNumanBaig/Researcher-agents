---
name: article-featured-image
description: Build a realistic, article-specific featured image prompt for the Researcher-agents pipeline and generate it with Cloudflare klein4b. Use whenever a blog article needs a featured image.
---

# Article featured image (klein4b)

Goal: one realistic editorial-style featured image per article, driven by that article's own facts. Never a random or generic scene.

## Hard rules

1. Build the prompt only from details found in the article and its sources (event, venue, city, season, product, mood). If a detail is not in the sources, leave it out.
2. Never generate an image of a real, named person, and never try to copy a real person's face from reference photos. This applies to celebrities, politicians, athletes and private individuals.
3. If the article is about a named person, depict the setting instead (premiere, stage, venue, product, location), with people shown only as non-identifiable crowd or silhouettes seen from a distance or behind.
4. For named-person articles, set `needs_licensed_photo: true` in the log so a human can add a properly licensed, credited photo (press kit, studio publicity image, Wikimedia Commons with a usable licence).
5. Avoid readable text in the scene (signs, marquees, posters, banners). The model garbles lettering.
6. Do not paint logos, brand marks, or watermarks.

## Workflow

1. Read the article text, title, and listed sources.
2. Extract a fact sheet: event or topic, location, time of day or season, objects and setting, mood, any product or film being promoted.
3. Choose a mood from the mood-to-colour table below.
4. Write the prompt with the formula below.
5. Generate with klein4b (see "Model call").
6. Check the quality list. If it fails, change one thing and retry (max 3 tries).
7. Save the image and write a log entry (prompt, mood, fact sheet, tries, needs_licensed_photo).

## Prompt formula

Scene description, then lighting source, then camera and lens, then colour grade, then optional film-look reference. Put style words at the END; the scene comes first.

`[subject + setting from the article], [lighting source], [shot size and angle], [lens and aperture], [colour grade], [optional one film-look reference], photorealistic editorial photograph, no text, no logos, no watermark`

Rules of thumb:
- Name exact colours and where they appear. Do not write "colourful".
- Pick one mood and one palette. Do not stack several film references.
- Keep colour grade consistent with the lighting (no warm golden grade under harsh fluorescent light).
- Short and specific beats long. Do not specify RGB values.

## Mood to colour grade

| Mood | Grade words |
|---|---|
| Epic, heroic | warm golden highlights, deep blue shadows, rich cinematic grade |
| Dark, moody | desaturated tones, deep shadows, teal and orange palette |
| Romantic, dreamy | soft pink and gold tones, gentle haze |
| Sci-fi, tech | electric blue and magenta, dark backgrounds, high contrast |
| Vintage, nostalgic | faded warm tones, lifted blacks, fine film grain |
| Clean, corporate | bright, slightly cool, high-key lighting |
| Nature, documentary | rich greens, warm earth tones, natural saturation |
| Melancholy | desaturated blue-grey, cold tones, overcast |
| High energy, action | punchy contrast, vibrant saturation |
| Luxury, premiere, awards | deep rich blacks, golden accents, warm highlights |

Film-look shortcuts (use at most one): Dune (amber and sand, hazy), Blade Runner 2049 (orange and teal, smoky neon), La La Land (saturated primaries, golden hour), Barbie (hot pink, candy colours, high key), The Revenant (cold natural light, blue-grey).

## Camera vocabulary

- Shot size: extreme wide (tiny subject, big place), wide, full, medium-wide, medium, medium close-up, close-up, extreme close-up (details such as hands, objects).
- Angle: eye level (natural), low angle (powerful), high angle (small subject), overhead (patterns and layout), dutch angle (tension), over-the-shoulder, POV.
- Lens: 16-24mm wide (space, distortion up close), 50mm normal, 85mm portrait (flattering compression), 200mm telephoto (compressed background, big sun or moon).
- Aperture: f/1.4 melts the background; f/8 keeps everything sharp. Say how far the background is when using f/1.4.
- Camera and lens character words: ARRI Alexa (cinematic, soft highlights), Sony Venice 2 (low-light night), RED V-Raptor (sharp action, motion), Hasselblad medium format (product and luxury detail); clean modern, warm organic (Cooke), vintage, anamorphic (horizontal flares, oval bokeh).

## Article type to look

| Article type | Setting ideas (from the article) | Shot | Lens | Grade |
|---|---|---|---|---|
| Film premiere or red carpet | carpet, stanchions, photographers' flashes, venue entrance | wide, eye level | 35 to 50mm, f/2.8 | luxury, warm highlights |
| Awards or ceremony | stage, curtains, spotlights, empty seats | wide or medium-wide | 24 to 35mm | luxury or epic |
| Concert or festival | stage lights, crowd from behind, haze | wide, low angle | 24mm, f/2 | high energy, magenta and blue |
| Film or TV release | the genre's look, props, empty set | medium-wide | anamorphic | match genre mood |
| Product or tech | the product on a clean surface, detail | extreme close-up | 85mm macro feel | clean or Hasselblad look |
| Sports | stadium, field, equipment | wide or telephoto | 200mm | high energy |

## Model call (Cloudflare Workers AI)

- Model: `@cf/black-forest-labs/flux-2-klein-4b`
- klein models require multipart form input, not plain JSON. Send fields `prompt`, `width`, `height` as form data and pass the form body and its content-type through the `multipart` option of `env.AI.run` (or the equivalent REST multipart request).
- The response is JSON with a base64 `image` field. Decode and save it.
- Size: 1024x576 for 16:9 featured images.
- Credentials: `CF_ACCOUNT_ID` and `CF_API_TOKEN` come from environment secrets. Never print them or write them to files.

## Quality check before accepting an image

- Matches the fact sheet (setting, time of day, mood).
- Looks like a real photograph, not an illustration.
- No readable garbled text, no logos, no watermark.
- No recognisable real person; faces, if any, are small and non-specific.
- Hands, crowds and architecture look physically plausible.
- Not too dark or flat; subject readable at thumbnail size.

If it fails: change one thing (simplify the scene, drop signage, change the angle, swap the grade) and retry.

## Log entry (one per image)

```
article_slug, fact_sheet, mood, prompt, model, tries, needs_licensed_photo, file_name
```

## WordPress

Upload as the featured image with alt text beginning "AI-generated illustration for:". Save the post as a draft. Do not publish.
