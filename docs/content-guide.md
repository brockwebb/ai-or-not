# Content Guide — AI or Not?

This guide explains how to contribute items to the AI or Not? content library (`content.json`), the single source of truth for all game content.

---

## Adding New Items

### 1. Fork the repo and edit `content.json`

All game content lives in `/content.json`. To add items, append new entries to the `items` array and submit a PR. Do not remove or reorder existing items — the `id` field is the stable reference used in session data.

### 2. Assign the next available ID

IDs follow the pattern `img-NNN` (zero-padded to 3 digits). Check the last entry in `content.json` and increment. For example, if the last item is `img-020`, your first new item is `img-021`.

If video support is added in the future, video items will use `vid-NNN`.

### 3. Fill in every field

All fields are required. There are no optional fields. Partial entries will be rejected in review.

---

## Schema Reference

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier. Format: `img-NNN` for images, `vid-NNN` for videos. Never reuse an ID, even if the original item was removed. |
| `media_type` | string | `"image"` or `"video"`. Currently only `"image"` is supported. |
| `url` | string | Direct URL to the media file. Must be stable (not a temporary or session-based URL) and hotlinkable. See URL requirements below. |
| `is_ai` | boolean | `true` if AI-generated, `false` if a real photograph or video. |
| `source` | string | The model name (for AI) or photographer/platform (for real). Examples: `"Midjourney v6"`, `"Unsplash — Jane Doe"`. |
| `attribution` | string | Full attribution string suitable for display. Even if the license doesn't require attribution, we include it as good practice. |
| `license` | string | SPDX license identifier or platform license name. See licensing section below. |
| `explanation` | string | 1-2 sentences explaining why the image is or isn't AI, and what visual clues to look for. This is the educational core of the game — make it count. |
| `category` | string | One of: `"person"`, `"animal"`, `"landscape"`, `"object"`, `"scene"`. See category notes below. |
| `generation_method` | string | One of: `"midjourney"`, `"dall-e"`, `"stable-diffusion"`, `"flux"`, `"photograph"`, or another specific model name. Use `"photograph"` for real images. |
| `prior_difficulty` | number | Curator's Bayesian prior estimate of how hard the item is to classify correctly, from `0.0` (trivially easy) to `1.0` (nearly impossible). See difficulty guidelines below. |
| `tags` | array of strings | Lowercase, hyphenated descriptive tags. Used for filtering and analysis. At least 2 tags per item. |

---

## URL Requirements

URLs must be:

- **Stable**: The same URL must return the same image months or years later. No session tokens, no expiring links, no URLs that rotate content.
- **Hotlinkable**: The URL must load directly in an `<img>` tag without requiring authentication, cookies, or referrer headers.
- **HTTPS**: All URLs must use HTTPS.

### Recommended sources for real photographs

| Source | URL Format | Notes |
|--------|-----------|-------|
| Unsplash | `https://images.unsplash.com/photo-{ID}?w=800&q=80` | Stable, hotlinkable, free. Preferred source. |
| Pexels | `https://images.pexels.com/photos/{ID}/pexels-photo-{ID}.jpeg?w=800` | Stable, hotlinkable, free. |
| Wikimedia Commons | Direct file URL from the file page | Stable, but URLs can be long. Use the direct image URL, not the wiki page URL. |

### Recommended sources for AI-generated images

| Source | URL Format | Notes |
|--------|-----------|-------|
| Lexica.art | `https://image.lexica.art/full_jpg/{hash}` | Stable archive of Stable Diffusion outputs. |
| Wikimedia Commons | Direct file URL | Some AI-generated images are uploaded with CC licenses. |
| Self-generated | Host in the repo's `/assets/` directory or a stable CDN | Generate your own with Midjourney, DALL-E, Stable Diffusion, Flux, etc. |

### Sources to avoid

- **thispersondoesnotexist.com** — Generates a new image on every page load. Not stable.
- **Social media hotlinks** — Twitter, Instagram, Reddit image URLs break regularly.
- **Google Drive / Dropbox share links** — Not reliably hotlinkable.
- **Any URL requiring JavaScript** — The game loads images in `<img>` tags.

If you cannot find a stable URL, use the placeholder `"PLACEHOLDER_REPLACE_WITH_REAL_URL"` and describe the intended image in the explanation field. The maintainer will source a stable URL before merging.

---

## Licensing

Every item must have a valid license. Here are the common cases:

| Content Type | License | Notes |
|-------------|---------|-------|
| Unsplash photos | `"Unsplash License"` | Free to use, attribution not required but appreciated. |
| Pexels photos | `"Pexels License"` | Free to use, attribution not required but appreciated. |
| Wikimedia CC content | Use the exact CC license, e.g. `"CC-BY-SA-4.0"` | Check the file page for the correct license. |
| AI-generated images | `"CC0-1.0"` | AI outputs are generally not copyrightable in the US. Use CC0 unless the platform's ToS impose restrictions, in which case note the platform in the attribution field. |
| Self-hosted originals | `"CC-BY-4.0"` or `"CC0-1.0"` | Your choice. CC0 is simpler for an educational project. |

Never use images with restrictive licenses (e.g., "editorial use only," "no derivatives") or images of unclear provenance. When in doubt, don't include it.

---

## Content Safety Rules

This game is designed for children ages 6 and up. All content must be safe for that audience. These rules are non-negotiable.

1. **No identifiable real people.** No faces that could be recognized as a specific individual. This protects privacy and avoids consent issues. Landscapes, animals, objects, and scenes are preferred.
2. **No violence, gore, or disturbing imagery.** No weapons, injuries, blood, or frightening content.
3. **No sexual or suggestive content.** Nothing that a reasonable parent would object to showing a 6-year-old.
4. **No hate symbols, slurs, or offensive text.** If an AI image contains visible text, verify it doesn't accidentally spell something offensive (AI text generation is unpredictable).
5. **No images that mock, stereotype, or demean any group.**
6. **No content that promotes illegal activity.**

If you are unsure whether an image meets these standards, err on the side of exclusion. There are plenty of safe, interesting images to choose from.

---

## Category Guidelines

| Category | Use for | Avoid |
|----------|---------|-------|
| `person` | Full-body silhouettes, AI-generated faces that are clearly not real people. | Identifiable real people. Use sparingly due to privacy concerns with AI-generated faces. |
| `animal` | Wildlife, pets, insects, marine life. | Graphic predation or animal distress. |
| `landscape` | Natural scenery: mountains, oceans, skies, forests, deserts. | Nothing specific to avoid. Great category for tricky items. |
| `object` | Food, flowers, books, tools, vehicles, architecture details. | Objects that are weapons or could be disturbing. |
| `scene` | Multi-element compositions: cityscapes, underwater scenes, interiors, markets. | Scenes with identifiable people or unsafe content. |

---

## Difficulty Guidelines

The `prior_difficulty` field is the curator's estimate of how hard the item is to classify. It is NOT a confidence score — it's a prediction about player accuracy.

| Range | Meaning | Examples |
|-------|---------|---------|
| 0.0 - 0.2 | Very easy. Almost everyone gets it right. | Obvious AI text artifacts, clearly normal photo. |
| 0.2 - 0.4 | Easy. Most players get it right. | AI images with visible artifacts (extra fingers, blurry edges). Clear, well-lit real photos. |
| 0.4 - 0.6 | Medium. About half of players get it right. | Photorealistic AI or unusually dramatic real photos. |
| 0.6 - 0.8 | Hard. Most players get it wrong. | Very high-quality AI or surreal-looking real phenomena (auroras, macro crystals, deep-sea creatures). |
| 0.8 - 1.0 | Very hard. Almost everyone gets it wrong. | State-of-the-art AI in domains where real photos already look unreal. |

These priors will be updated with Bayesian methods as real player data comes in. Don't overthink the initial estimate — a rough calibration is fine.

---

## Writing Good Explanations

The explanation field is the most important educational component. After a player guesses, they see the explanation. It should teach them something.

### For AI images, explain what to look for:

- Specific artifacts: "Look at the hands — the left one has six fingers."
- Texture issues: "The fur looks painted rather than individual hairs."
- Physics violations: "The reflection in the water doesn't match the scene above."
- Semantic errors: "Text on the signs is gibberish."
- Pattern repetition: "The background trees are the same shape copied multiple times."

### For real images, explain why they look unusual:

- Photography technique: "Long-exposure photography makes waterfalls look silky smooth."
- Natural phenomena: "Auroras genuinely produce these vivid green and purple colors."
- Rare subjects: "This is a real species — the mandrill has one of the most colorful faces in the animal kingdom."
- Scale or perspective: "Macro photography reveals details invisible to the naked eye."

### General writing guidance:

- Write for a 12-year-old. Clear, concrete, no jargon.
- Keep it to 1-3 sentences. Respect the player's time.
- Be specific, not generic. "Look at the eyes" is worse than "The pupils are different shapes — real cat pupils are vertical slits."
- Make it memorable. A good explanation teaches a heuristic the player can reuse.

---

## Review Process

All content additions go through PR review by the project maintainer.

### What the reviewer checks:

1. **URL stability**: Is the URL likely to remain valid? Can it be loaded in an `<img>` tag?
2. **Content safety**: Does the image meet all safety rules above?
3. **Accuracy**: Is `is_ai` correct? Is the `generation_method` accurate?
4. **Explanation quality**: Does it teach something useful? Is it age-appropriate?
5. **License validity**: Is the license correctly identified?
6. **Schema compliance**: Are all fields present and correctly typed?
7. **Balance**: Does the addition maintain a reasonable balance of AI/real, easy/hard, and categories?

### Common rejection reasons:

- Unstable or broken URL
- Missing or incorrect license
- Explanation is generic or doesn't teach a useful heuristic
- Content not appropriate for ages 6+
- Duplicate or near-duplicate of existing item
- `is_ai` flag is wrong

---

## Tips for Finding Good Content

### Real photos that look AI-generated:

- Search Unsplash for: "surreal nature," "macro photography," "aurora borealis," "bioluminescence," "fractal patterns in nature," "unusual animals"
- Long-exposure, HDR, and macro photography often produce results that look unreal
- Rare natural phenomena: nacreous clouds, lenticular clouds, rainbow eucalyptus, volcanic lightning

### AI images that look real:

- Browse Lexica.art with photorealistic prompts
- Look for AI images that were initially shared as "real" and later debunked
- Focus on subjects where the "uncanny valley" is narrowest: landscapes, food, flowers, architecture
- The harder it is for YOU to tell, the better the item is for the game

### The best items are the ones that surprise players.

A dramatic real photo that everyone guesses as AI, or a subtle AI image that fools everyone — those are the items that teach the most. Aim for a mix of "aha!" moments and genuine challenges.
