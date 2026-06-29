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
├── wikipedia-to-tapestry.py           # Original visual map converter
├── wikipedia-images-to-tapestry.py    # Image slideshow converter
├── videowiki-to-tapestry.py           # VideoWiki script slideshow converter
├── validate-tapestry.py               # Symlink → skill dir validator
├── README.md                          # Full usage docs
├── HANDOFF.md                         # This file
├── IDEAS.md                           # General future project ideas
├── IDEAS-WIKIPORTRAITS.md            # WikiPortraits-specific ideas
├── requirements.txt                   # Python deps (requests)
├── samples/                           # Example .zip outputs
└── .gitignore                         # *.zip, playwright cache
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

## Known Limitations

1. **No built-in auto-play for audio** — TTS audio plays manually; the viewer
   doesn't support auto-advance or auto-play during presentation navigation.
2. **TTS requires edge-tts** — Not included in requirements.txt; must be
   installed separately (`pip install edge-tts`).
3. **Citation URL resolution** — Extracts URLs from cite templates but doesn't
   resolve shortDOIs or handle all citation format variants.
4. **No batch mode** — Each article converted individually; no multi-article
   or category-level batch processing.

## Future Directions

See `IDEAS.md` and `IDEAS-WIKIPORTRAITS.md` for detailed project ideas.
Key areas:

- Batch convert all VideoWiki scripts from `Category:Videowiki_scripts`
- Auto-play audio on presentation step (viewer-side feature)
- WikiPortraits integration (portrait galleries, career evolution, event maps)
- Wikidata enrichment for images (subject QID lookup)
- HTML/PDF export option alongside Tapestry zip

## Who Built This

Developed June 2026 by reverse-engineering the Tapestry v7 export format from
production `.zip` files. The canonical v7 Zod schema is at
[github.com/asteasolutions/tapestry-project](https://github.com/asteasolutions/tapestry-project).
The Tapestry format skill is at
[github.com/fuzheado/tapestries-skill](https://github.com/fuzheado/tapestries-skill).
