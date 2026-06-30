# Handoff — Wikipedia → Tapestry Converters

**Date:** June 29, 2026
**Status:** Three converters, actively used

## What This Is

A collection of Python scripts that convert Wikipedia content into `.zip` files
for import into [Tapestries](https://tapestries.media) — an infinite canvas
multimedia authoring platform.

## File Structure

```
~/Documents/ai/tapestry-converter/
├── wikipedia-to-tapestry.py              # Original visual map converter
├── wikipedia-images-to-tapestry.py       # Image slideshow converter
├── videowiki-to-tapestry.py              # VideoWiki script slideshow converter
├── wikipedia-citation-graph.py           # ⭐ Citation graph converter (new)
├── validate-tapestry.py                  # Symlink → skill dir validator
├── PRD-CITATION-GRAPH.md                # Citation graph feature spec
├── README.md                             # Full usage docs
├── HANDOFF.md                            # This file
├── IDEAS.md                              # General future project ideas
├── IDEAS-WIKIPORTRAITS.md               # WikiPortraits-specific ideas
├── requirements.txt                      # Python deps (requests)
├── samples/                              # Example .zip outputs
├── .screenshot_cache/                    # Playwright screenshot cache
└── .gitignore                            # *.zip, playwright cache
```

The companion skill ([github.com/fuzheado/tapestries-skill](https://github.com/fuzheado/tapestries-skill))
contains the full v7 format specification, validator, and test files.

## Converters

### 1. Visual Map (`wikipedia-to-tapestry.py`)

The original converter. Turns any Wikipedia article into a visual map:
image gallery at top, article embed in the center, linked articles below.

**Architecture:**
1. Page summary via REST API
2. Lead section links via Action API
3. Linked article summaries via REST API
4. Article images via `parse&prop=images`
5. Image dimensions via `prop=imageinfo&iiprop=url|size`
6. Tapestry builder — v7-compliant JSON

**Key features:** grid/semicircle layout, browser screenshots, disambiguation filtering,
icon filtering, packed mode, mobile Wikipedia URLs.

### 2. Image Slideshow (`wikipedia-images-to-tapestry.py`)

Extracts all useful images from any Wikipedia article into a navigable photo
mosaic. sqrt(N) grid layout, Commons metadata as captions (SDC + extmetadata),
group-based presentation, Commons link buttons, disk caching.

### 3. VideoWiki Slideshow (`videowiki-to-tapestry.py`)

Converts VideoWiki scripts into interactive slideshows with hand-picked images,
narration text, TTS audio, and clickable references. Latest and most feature-rich.

**Key features:**
- Parses VideoWiki wikitext (sections, narration, images, {{ReadShow}}, citations)
- Multi-image sub-rows within a single group
- TTS narration via edge-tts (`--tts`)
- Three layout modes: grid, horizontal, vertical
- Global citation numbering with clickable URL references section
- Auto-generated title card and credit footer
- Configurable button color, text scale, image width

### 4. Citation Graph (`wikipedia-citation-graph.py`)

Newest converter. Renders any Wikipedia article as a **star graph**:
a full-page screenshot of the article in the center, with all its cited
references flanking it on both sides, connected by arrows from the exact
citation positions in the article.

**Architecture:**
1. Fetch rendered HTML via `action=parse&prop=text`
2. Parse references from `<ol class="references">` (HTML entity `&#95;` for underscores)
3. Optional: cross-verify with `mwparserfromhell` (wikitext parsing)
4. Capture full-page screenshot via Playwright CLI (`fullPage: true`)
5. Measure citation positions via `document.querySelectorAll("sup.reference a")`
   with `getBoundingClientRect().top` — accurate to the pixel
6. Detect clusters of refs at similar Y positions and fan them outward
7. Build v7 Tapestry with article as `image` item, refs as appropriate types

**Key features:**
- Three layout modes: positioned (both sides), ring, grid
- Full-page article screenshot — no scrolling needed on the canvas
- References at their approximate article positions (Playwright-measured)
- Reference type detection: webpage, PDF, book/ISBN, DOI, PubMed, arXiv, text
- Optional URL probing (`--probe`) for dead link detection
- Playwright screenshots as article + source page thumbnails (`--screenshots`)
- Numbered circle badges on each reference
- Action buttons to open URLs externally
- Screenshot cache (`.screenshot_cache/`) — 2nd run is instant

## Key Design Decisions

### Images use URLs, not embedded files
All converters use Wikimedia Commons URLs directly as `source`. Zips stay under
~20 KB without audio, ~350-750 KB with TTS audio.

### Group-based presentation
Each slide's items (image, text, button, audio) share a `groupId`. Presentation
steps target the group, zooming the viewport to show all items together.

### VideoWiki narration as caption
Unlike the image slideshow (which uses Commons metadata), the VideoWiki converter
uses the script's narration text — already written to be spoken alongside visuals.

## Feature Checklist — VideoWiki Converter

| Feature | Status | Notes |
|---|---|---|
| Wikitext parsing (sections, images, narration) | ✅ | |
| Citation extraction with URLs | ✅ | |
| {{ReadShow}} display/speech separation | ✅ | |
| Multi-image sub-rows | ✅ | Sections with 2-3 images stay in one group |
| Video file support | ✅ | .webm, .mp4, .ogv → video items |
| TTS narration (edge-tts) | ✅ | `--tts` flag, per-slide MP3 audio |
| Three layout modes | ✅ | `--layout grid|horizontal|vertical` |
| Global citation numbering | ✅ | 1..N across all slides |
| References section with clickable URLs | ✅ | |
| Title card | ✅ | Auto-generated from page name |
| Credit footer | ✅ | Links to source and converter repo |
| Configurable button color | ✅ | `--button-color` hex option |
| Text scale | ✅ | `--text-scale` for caption height |

## Feature Checklist — Citation Graph Converter

| Feature | Status | Notes |
|---|---|---|
| Rendered HTML reference parsing | ✅ | `<ol class="references">` with `&#95;` entity support |
| mwparserfromhell cross-verification | ✅ | Optional, auto-detected |
| Full-page article screenshot | ✅ | Playwright `fullPage: true`, cached |
| Playwright-measured citation positions | ✅ | `getBoundingClientRect().top` on `<sup>` elements |
| Cluster detection + fan-out | ✅ | Refs within 150px get staggered horizontally |
| Both-sides layout (default `u`) | ✅ | Alternating left/right, arrows from article edges |
| Ring layout | ✅ | Full ellipse, double ring for >30 refs |
| Grid layout | ✅ | Centered grid below article |
| Reference type detection | ✅ | webpage, PDF, book/ISBN, DOI, PubMed, arXiv, text |
| URL probing | ✅ | `--probe` flag, HEAD requests to detect dead links |
| Source page screenshots | ✅ | `--screenshots`, thumbnail for each reference |
| Numbered badges | ✅ | Colored circle with citation number |
| Action buttons | ✅ | "Open ↗" on each URL-bearing reference |
| Article height control | ✅ | `--max-height`, `--height-ratio` |
| Overflow summary card | ✅ | When refs exceed `--max-refs` |
| Screenshot cache | ✅ | `.screenshot_cache/`, `--no-cache`, `--clear-cache` |

## Known Limitations

1. **No built-in auto-play for audio** — TTS audio plays manually; the viewer
   doesn't support auto-advance or auto-play during presentation navigation.
2. **TTS requires edge-tts** — Not included in requirements.txt; must be
   installed separately (`pip install edge-tts`).
3. **Citation URL resolution** — Extracts URLs from cite templates but doesn't
   resolve shortDOIs or handle all citation format variants.
4. **No batch mode** — Each article converted individually; no multi-article
   or category-level batch processing.
5. **X-Frame-Orictions on source pages** — Some sites block iframe embedding;
   the webpage embed shows blank. Action button still opens in new tab.
6. **Mobile screenshot width** — Article screenshot uses mobile view (~450px
   content width within 800px viewport). Desktop rendering not supported yet.

## Future Directions

See `IDEAS.md` and `IDEAS-WIKIPORTRAITS.md` for detailed project ideas.
Key areas:

- Batch convert all VideoWiki scripts from `Category:Videowiki_scripts`
- Auto-play audio on presentation step (viewer-side feature)
- WikiPortraits integration (portrait galleries, career evolution, event maps)
- Wikidata enrichment for images (subject QID lookup)
- HTML/PDF export option alongside Tapestry zip
- Citation clustering by section — group refs by which section cites them
- DOI → CrossRef metadata enrichment (author, year, journal)

## Who Built This

Developed June 2026 by reverse-engineering the Tapestry v7 export format from
production `.zip` files. The canonical v7 Zod schema is at
[github.com/asteasolutions/tapestry-project](https://github.com/asteasolutions/tapestry-project).
The Tapestry format skill is at
[github.com/fuzheado/tapestries-skill](https://github.com/fuzheado/tapestries-skill).
