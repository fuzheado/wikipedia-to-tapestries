# Wikipedia → Tapestry Converters

Convert Wikipedia articles into `.zip` files for import into
[Tapestries](https://tapestries.media) — an infinite canvas multimedia authoring platform.

Four converters are included, each serving a different use case:

| Script | What it does |
|---|---|
| `wikipedia-to-tapestry.py` | **Visual map** — image gallery, article embed, linked articles in grid/semicircle |
| `wikipedia-images-to-tapestry.py` | **Image slideshow** — article images as a navigable photo mosaic |
| `videowiki-to-tapestry.py` | **VideoWiki slideshow** — narrated scripts with TTS audio |
| [`wikipedia-citation-graph.py`](#wikipedia--citation-graph) | **Citation graph** — article as full-page screenshot with all references flanking it |

> **🧪 Instant testing:** Use **[viewer.tapestries.media](https://viewer.tapestries.media)** to preview any `.zip` file
> immediately — **no sign-in, no upload, no account needed.** Just drag the file onto the page.
> You can also load a hosted zip via URL:
> `viewer.tapestries.media?source=https://example.com/chess.zip`
> This works for all three converters below.

## Quick Start

```bash
# 1. Set up Python
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Convert a Wikipedia article
python3 wikipedia-to-tapestry.py "Chess" -o chess.zip

# 3. Validate the output
python3 validate-tapestry.py chess.zip

# 4. Preview locally (no sign-in needed)
#    Go to https://viewer.tapestries.media and drag chess.zip onto the page
#    Or host the zip somewhere and load it programmatically:
#    https://viewer.tapestries.media?source=https://example.com/chess.zip
#
# 5. Upload to Tapestries
#    Drag chess.zip onto https://tapestries.media
```

## Usage

```bash
python3 wikipedia-to-tapestry.py "Article Title" [options]
python3 wikipedia-to-tapestry.py "https://en.wikipedia.org/wiki/Article_Title"
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--max-links N` | 10 | Number of linked articles from the lead section |
| `--max-gallery N` | 50 | Max images in the gallery |
| `--gallery-height N` | 160 | Gallery image height in pixels |
| `--packed` | off | Hide filenames on gallery images, tighter spacing |
| `--layout` | `grid` | Linked article layout: `grid` or `semicircle` |
| `--screenshots` | off | Capture real browser screenshots as webpage thumbnails |
| `--lang LANG` | `en` | Wikipedia language code |
| `--output`, `-o` | auto | Output `.zip` file path |

### Output Layout

Default (`--layout grid`):
```
┌──────────────────────────────────────────┐
│  Image Gallery (center-aligned rows)     │
├──────────────────────────────────────────┤
│  Main Article (webpage embed)            │
│         ──────────┬──────────            │
│                   │                      │
│              ┌──────┐  ┌──────┐          │
│              │Link 1│  │Link 2│          │
│              │500x400│ │500x400│         │
│              └──────┘  └──────┘          │
└──────────────────────────────────────────┘
```

`--layout semicircle` fans linked articles in a smile-shaped arc below the main
article, centered on the same centerline.

### Gallery image sizing

Gallery images are **not downloaded** for the zip. Their Commons URLs are used
directly as item `source`, keeping the file small (typically 100-200 KB regardless
of gallery count). Dimensions are fetched from the Wikimedia API (`iiprop=size`)
in a single lightweight call per image — no image data is transferred during sizing.
Each image is displayed at the specified `--gallery-height` with proportional width
matching its real aspect ratio.

All gallery rows share the same centerline as the main article. Rows wider than
the article extend into negative x territory (fine on an infinite canvas); the
dynamic `startView` zooms out to show everything.

> **Image discovery quirk:** The converter uses `action=parse&prop=images` to
> discover images, which processes the fully-rendered page and finds ~2× more
> images than `prop=images` (which only catches direct wikitext transclusions).
> Example: Stockholm returned 8 images with `prop=images` vs 36 with `parse+images`.

### Screenshot thumbnails

By default, webpage items use the article's lead image as a thumbnail. For actual
page screenshots, pass `--screenshots`:

```bash
python3 wikipedia-to-tapestry.py "Chess" --screenshots -o chess.zip
```

This uses [Playwright CLI](https://github.com/microsoft/playwright-cli) to render
each page in a headless browser at 500×500 and capture a PNG. Requires:

```bash
npm install -g @playwright/cli@latest
playwright-cli install
```

Note: `--screenshots` requires an active Playwright browser session. The script
spawns `playwright-cli` subprocesses to capture each page.

### Linked article filtering

- **Disambiguation pages** are filtered out automatically (detected via the REST API
  summary `type` field). A message is shown for each skipped page.
- Links are limited by `--max-links` (default 10).

### Presentation tour

The file includes a `presentation` array for guided navigation:
**main article → all gallery images → all linked articles** in sequence.
The `startView` is calculated dynamically from the bounding box of all items.

### Wikipedia mobile view

Webpage URLs use `?useformat=mobile` to activate the mobile stylesheet,
producing a cleaner embed without sidebars, collapsed ToC, or desktop chrome.

---

## Wikipedia → Image Slideshow

A companion script that turns **all useful images** from a Wikipedia article into a
navigable photo mosaic on the infinite canvas — like a visual narrative overview
of the article.

```bash
python3 wikipedia-images-to-tapestry.py "Article" [options]
python3 wikipedia-images-to-tapestry.py "https://en.wikipedia.org/wiki/Article"
```

### Quick Start

```bash
python3 wikipedia-images-to-tapestry.py "Great Barrier Reef" -o reef_slideshow.zip
python3 validate-tapestry.py reef_slideshow.zip
# Preview: go to https://viewer.tapestries.media and drag the zip onto the page
#    Or host the zip and load via URL: https://viewer.tapestries.media?source=https://...
# Import: drag the zip onto https://tapestries.media

# Full thumbnails of pages and nice arrangement
python3 wikipedia-to-tapestry.py "2024 Sundance Film Festival" --layout semicircle --screenshots --max-links 8 --max-gallery 40 --gallery-height 150
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--max-images N` | 50 | Max images to include |
| `--image-width N` | 600 | Display width of each image in pixels |
| `--lang LANG` | `en` | Wikipedia language code |
| `--output`, `-o` | auto | Output `.zip` file path |

### What It Produces

Each useful image becomes a **slide** on the canvas with three items bundled
into a group:

```
┌──────────────────────────┐
│      Image (600px)       │
├──────────────────────────┤
│  Caption text            │
│  (SDC label + Commons    │
│   description + artist)  │
├──────────────────────────┤
│ 🌐 View on Commons  │  ← clickable button
└──────────────────────────┘
```

**Layout:** Images are arranged in a center-aligned grid with roughly equal
rows and columns (`round(sqrt(N))`). For 49 images you get 7×7; for 25 you get 5×5.
This produces a roughly square/round shape on the canvas, with ragged left/right
edges since each row is centered independently.

**Groups for presentation focus:** Each image, its caption text, and its Commons
link button share a single `groupId`. The presentation tour targets the group
(rather than the individual image), which tells Tapestries to zoom the viewport
wide enough to show the image **and** its caption text together — so you see the
full slide, not just a tightly-cropped image.

**Navigation:** The presentation steps walk through groups (slide → slide → …).
There are no visual arrows; the presentation's built-in next/prev controls
handle the flow. Clicking the blue "View on Wikimedia Commons" button opens the
file's Commons page in a new tab.

### Commons Metadata

Images are enriched with data from **two** Commons API calls (cached to disk):

| Source | What it provides |
|---|---|
| `prop=imageinfo&iiprop=extmetadata` | `ImageDescription`, `Artist`, `DateTimeOriginal`, `ObjectName` (from the file's Information template) |
| `wbgetentities` (SDC) | Multilingual structured caption (the file's label on Commons) |

The caption HTML combines the SDC label (bold heading), the Commons description
(body), and the artist/date (gray attribution line).

### Image Filtering

Uses the same `is_useful_image()` filter as the visual map converter — skips
icons, logos, lock symbols, UI badges, flags, and Wikimedia project logos.

### Disk Cache

Image metadata is cached to `~/.cache/tapestry-converter/<Article>_<lang>.json`.
Re-running the same article loads from cache instantly (shown with a 💾 indicator).
Clear the cache directory to force a fresh fetch.

### No Image Downloads

Like the visual map converter, images use their Commons thumbnail URLs directly
as item `source`. The zip stays small (~15-20 KB for 50 images) — no image data
is embedded.

### Examples

```bash
# 49 images, 7×7 grid
python3 wikipedia-images-to-tapestry.py "Philadelphia"

# 50 images, 7×7+1 grid, larger display
python3 wikipedia-images-to-tapestry.py "Elephant" --image-width 700

# Custom output name
python3 wikipedia-images-to-tapestry.py "https://en.wikipedia.org/wiki/Coral_reef" -o coral_reef_slideshow.zip
```

---

## VideoWiki → Slideshow

Converts a [VideoWiki](https://meta.wikimedia.org/wiki/VideoWiki) script page into a
Tapestry slideshow. VideoWiki scripts structure Wikipedia content into sections,
each with a hand-picked image and narration text written to be read aloud.
This converter preserves that narrative flow as an interactive Tapestry.

```bash
python3 videowiki-to-tapestry.py "Wikipedia:VideoWiki/Birthday_cake" [options]
python3 videowiki-to-tapestry.py "https://en.wikipedia.org/wiki/Wikipedia:VideoWiki/Birthday_cake"
```

### Quick Start

```bash
python3 videowiki-to-tapestry.py "Wikipedia:VideoWiki/Birthday_cake" -o birthday_cake_videowiki.zip
python3 validate-tapestry.py birthday_cake_videowiki.zip
# Preview: https://viewer.tapestries.media?source=https://example.com/birthday_cake_videowiki.zip
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--max-slides N` | 50 | Max slides to include |
| `--image-width N` | 600 | Display width of each image in pixels |
| `--tts` | off | Generate spoken narration audio via edge-tts |
| `--tts-voice` | `en-US-JennyNeural` | TTS voice for narration |
| `--text-scale` | 1.0 | Scale caption text height (e.g. 1.5 for more room) |
| `--button-color` | `#dce8f5` | Action button background hex color |
| `--layout` | `grid` | Layout: `grid`, `horizontal`, or `vertical` |
| `--output`, `-o` | auto | Output `.zip` file path |

### What It Produces

Each VideoWiki section becomes one **group** on the canvas with all its images
in a centered sub-row. Sections with multiple images (e.g., "Early life" with
3 photos) keep them together in one group, sharing the narration text.

```
┌──────────────────────────────────┐
│  🏷️ Title card (auto-generated) │
├──────────────────────────────────┤
│  ┌──────┐ ┌──────┐              │
│  │Img 1 │ │Img 2 │  ← sub-row  │
│  └──────┘ └──────┘              │
│  ┌──────┐ ┌──────┐              │
│  │btn 1 │ │btn 2 │  per-image  │
│  └──────┘ └──────┘              │
├──────────────────────────────────┤
│  Section heading + narration    │
│  text (the spoken script)       │
├──────────────────────────────────┤
│ ▶️ Audio player (if --tts)    │
└──────────────────────────────────┘
        ... more groups ...
┌──────────────────────────────────┐
│  References (clickable URLs)     │
├──────────────────────────────────┤
│  Credit footer                   │
└──────────────────────────────────┘
```

### Layout Modes

| Mode | Shape | Use case |
|---|---|---|
| `grid` (default) | Roughly square (`round(sqrt(N))` columns) | General purpose |
| `horizontal` | Single row of all slides | Filmstrip / slideshow bar |
| `vertical` | Single column, stacked | Story / timeline scroll |

### TTS Audio Narration

Pass `--tts` to generate spoken narration for each slide using Microsoft's
neural TTS voice (edge-tts). Each slide gets an audio player embedded in its
group — visible when the presentation focuses on the group. Click play to hear
the narration for that slide.

Requires `edge-tts`:
```bash
source venv/bin/activate
pip install edge-tts
```

### How It Works

1. **Fetch wikitext** — retrieves the raw VideoWiki script via `action=raw`
2. **Parse sections** — finds `==Section==` headings, extracts narration text,
   collects `[[File:...]]` image references, strips wiki markup and templates,
   extracts {{ReadShow}} display/speech text, saves citations with URLs
3. **Fetch Commons image info** — thumbnail URL and dimensions (handles video too)
4. **Build slideshow** — same group-based layout with sqrt(N) grid positioning
5. **References section** — all citations collected globally, numbered 1..N,
   rendered as clickable `<a href>` links at the bottom of the canvas
6. **Title card** — auto-generated from the page name at the top
7. **Credit footer** — links to the source script and github.com/fuzheado/wikipedia-to-tapestries

### Examples

```bash
# Basic 8-slide grid
python3 videowiki-to-tapestry.py "Wikipedia:VideoWiki/Birthday_cake"

# Vertical strip with spoken narration
python3 videowiki-to-tapestry.py "Wikipedia:VideoWiki/Urinary_tract_infection" \
    --layout vertical --tts

# Grid with narration (requires edge-tts)
python3 videowiki-to-tapestry.py "https://en.wikipedia.org/wiki/Wikipedia:VideoWiki/Birthday_cake" \
    --tts

# Horizontal filmstrip, larger captions
python3 videowiki-to-tapestry.py "Wikipedia:VideoWiki/A._P._J._Abdul_Kalam" \
    --layout horizontal --text-scale 1.3
```

---

## Wikipedia → Citation Graph

Renders any Wikipedia article as a **star graph** on the infinite canvas:
the full article as a full-page screenshot image in the center, flanked on
both sides by its cited references, each rendered according to its type
(webpage embed, PDF viewer, book cover, DOI resolver, or text card), with
arrows connecting the citation positions in the article to each source.

```bash
python3 wikipedia-citation-graph.py "Article Title" [options]
python3 wikipedia-citation-graph.py "https://en.wikipedia.org/wiki/Article_Title"
```

### Quick Start

```bash
# Small article, default U-shape layout (refs flank article on both sides)
python3 wikipedia-citation-graph.py "Seven dirty words" -o seven-words-cites.zip

# With source page screenshots as thumbnails
python3 wikipedia-citation-graph.py "Ada Lovelace" --screenshots --max-refs 30

# Medium article with full ring layout
python3 wikipedia-citation-graph.py "Supreme Court of the United States" \
    --layout ring --max-refs 80 -o scotus-cites.zip

# Validate and preview
python3 validate-tapestry.py seven-words-cites.zip
# → https://viewer.tapestries.media
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--layout MODE` | `u` | Layout: `u` (positioned, both sides), `ring` (full ring), `grid` (grid below) |
| `--max-refs N` | 50 | Maximum references to include (0 = all) |
| `--max-height N` | none | Cap article image height in pixels |
| `--height-ratio N` | 1.0 | Scale article height by factor |
| `--article-width N` | 800 | Article screenshot width in pixels |
| `--ref-width N` | 450 | Reference embed width in pixels |
| `--screenshots` | off | Capture Playwright screenshots as thumbnails |
| `--probe` | off | Probe URLs with HEAD request to detect dead links |
| `--no-cache` | off | Bypass screenshot cache |
| `--clear-cache` | — | Delete all cached screenshots and exit |
| `--output`, `-o` | auto | Output `.zip` file path |

### What It Produces

The converter generates a self-contained v7 Tapestry zip with:

```
              ┌─────────────────────────┐
   ┌── Ref 1 ─┤  ARTICLE FULL SCREEN    ├── Ref 2 ──┐
   │          │  (800×6777px image)     │           │
   │ ┌──Ref 3─┤  no scrolling needed    ├── Ref 4──┐│
   │ │        │                         │         ││
   │ │┌─Ref 5─┤                         ├─Ref 6──┐││
   │ ││       │                         │        │││
   └─┘└───────┘                         └────────┘┘
```

- **Article:** A full-page screenshot (800px wide, full height) — the entire
  article visible at once, no scrolling. Captured via Playwright CLI with
  `fullPage: true`.
- **References:** Up to `--max-refs` (default 50) placed at their approximate
  citation position in the article. Clustered refs (multiple citations close
  together) fan outward horizontally with vertical stagger.
- **Both sides:** Refs alternate left and right of the article for visual
  balance. Arrows originate from the correct article edge at the citation's
  Y position.
- **Type detection:** Each reference is classified and rendered appropriately:
  - **Webpage URL** → `webpage` embed (live iframe)
  - **PDF** → `pdf` embed (embedded PDF viewer)
  - **Book (ISBN)** → Google Books embed
  - **DOI / PubMed / arXiv** → Resolved webpage embed
  - **Bare citation** → Text card with citation text
  - **Dead link** → Red placeholder card (with `--probe`)
- **Numbered badges:** Each reference has a colored circle badge showing its
  citation number.
- **Action buttons:** "Open ↗" button on each URL-bearing reference.
- **Presentation:** Guided tour through article → each reference in order.

### Citation Position Mapping

The converter uses **Playwright's DOM API** to measure exact citation positions:

```javascript
// Each citation <sup> element's getBoundingClientRect().top is recorded
const anchors = document.querySelectorAll("sup.reference a");
for (const a of anchors) {
  const rect = a.getBoundingClientRect();
  positions[baseRefName] = Math.round(rect.top);
}
```

This is far more accurate than HTML character-offset heuristics — it accounts
for images, tables, infoboxes, and variable line heights in the rendered page.

### Reference Verification

If [`mwparserfromhell`](https://github.com/earwig/mwparserfromhell) is installed,
the converter cross-verifies reference names from the raw wikitext against the
HTML-extracted references for additional accuracy.

```bash
pip install mwparserfromhell  # optional, but recommended
```

### Screenshot Cache

All screenshots (article + source pages) are cached to `.screenshot_cache/`
in the project directory. Cached screenshots are reused on subsequent runs:

```bash
# First run — captures everything (~5s article, ~30s with --screenshots)
python3 wikipedia-citation-graph.py "Ada Lovelace" --screenshots

# Second run — instant from cache (~3s)
python3 wikipedia-citation-graph.py "Ada Lovelace" --screenshots

# Clear cache
python3 wikipedia-citation-graph.py --clear-cache

# Bypass cache for one run
python3 wikipedia-citation-graph.py "Ada Lovelace" --no-cache
```

### Layout Modes

| Mode | `--layout` | Description |
|---|---|---|
| **Positioned** (default) | `u` | Refs flank article on both sides, placed at citation Y positions |
| **Ring** | `ring` | Refs encircle the article in an ellipse (double ring for >30 refs) |
| **Grid below** | `grid` | Refs arranged in a centered grid below the article |

### Examples

```bash
# All 16 refs from Seven dirty words with source screenshots
python3 wikipedia-citation-graph.py "Seven dirty words" --screenshots \
    -o samples/Seven_dirty_words_citation_graph.zip

# Alan Greenspan, cap at 40 refs, 8000px article height
python3 wikipedia-citation-graph.py "Alan Greenspan" --max-refs 40 \
    --max-height 8000 -o greenspan-cites.zip

# Supreme Court in ring layout with 80 refs
python3 wikipedia-citation-graph.py "Supreme Court of the United States" \
    --layout ring --max-refs 80 --max-height 10000 -o scotus-cites.zip

# Probe dead links, include all refs
python3 wikipedia-citation-graph.py "Ada Lovelace" --max-refs 0 --probe
```

---

## File Format

The output conforms to the **v7 Tapestry export format** as deployed on
`tapestries.media`. The full format specification, validator, and test files
are available at:

**https://github.com/fuzheado/tapestries-skill**

Locally at `~/.pi/agent/skills/tapestries/` if installed.

Key rules enforced by the converter:
- `version: 7` with `parentId`, `presentation`, `startView`, `thumbnail` at root
- File naming: `items/<uuid> (<name>).ext` (parentheses required — the import parser uses `/.*\(.*\)/`)
- Text items: `title: ""`, `backgroundColor: "#ffffff00"`, no `customThumbnail`
- Media items: no `customThumbnail`, no `internallyHosted`, `title: ""`
- `.000Z` date format on `createdAt` and `updatedAt`
- `User-Agent` must include "bot" identifier

## Validation

```bash
# Validate any .zip file
python3 validate-tapestry.py file.zip

# Verbose mode: show all items, assets, rels, presentation
python3 validate-tapestry.py -v file.zip
```

## Requirements

**Python** (always required):
- Python 3.10+
- `requests` library (see `requirements.txt`)

**Optional Python:**
- `mwparserfromhell` — cross-verifies reference names in the citation graph converter
  (`pip install mwparserfromhell`)
- `edge-tts` — TTS audio narration for the VideoWiki converter
  (`pip install edge-tts`)

**Playwright CLI** (required for `--screenshots` and the citation graph converter):
- Node.js 18+
- `npm install -g @playwright/cli@latest`
- `playwright-cli install` (downloads browser binaries)

**Internet connection** — fetches article data and images from Wikipedia & Commons APIs.
Wikimedia API requests use a `User-Agent` with bot identifier and `andrew.lih@gmail.com`
contact. Requests are rate-limited with 300ms delays between image downloads.

## Credits

Built by reverse-engineering the Tapestry v7 export format from production
`.zip` files downloaded from `tapestries.media`.
The Tapestry Project is open source — the active development fork is at
[github.com/asteasolutions/tapestry-project](https://github.com/asteasolutions/tapestry-project)
(the original [Internet Archive mirror](https://github.com/internetarchive/tapestry-project)
contains schemas up to v6 only).
The Tapestry format skill is at
[github.com/fuzheado/tapestries-skill](https://github.com/fuzheado/tapestries-skill).
