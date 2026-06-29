# Wikipedia → Tapestry Visual Map Converter

Converts any Wikipedia article into a `.zip` file for import into
[Tapestries](https://tapestries.media) — an infinite canvas multimedia authoring platform.

The output is a visual map: **image gallery** at the top (center-aligned rows),
the **article itself** as an embedded webpage in the center, and **linked articles**
from the lead section below in either a grid or semicircle layout, connected with arrows.
Includes a guided presentation tour through all items and a dynamic start view.

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
| `--output`, `-o` | auto | Output `.zip` file path |

### What It Does

Each VideoWiki section becomes a **slide** on the canvas. Sections with multiple
images create consecutive slides, one per image.

```
┌──────────────────────────┐
│  Section image (600px)   │
├──────────────────────────┤
│  Section heading         │
│  Narration text          │
│  (the spoken script)     │
├──────────────────────────┤
│ 🌐 View on Commons  │  ← opens the file's Commons page
└──────────────────────────┘
```

### How It Works

1. **Fetch wikitext** — retrieves the raw VideoWiki script via `action=raw`
2. **Parse sections** — finds `==Section==` headings, extracts narration text,
   collects `[[File:...]]` image references, strips wiki markup and templates
3. **Fetch Commons image info** — thumbnail URL and dimensions per image
4. **Build slideshow** — same group-based layout as the image slideshow converter

### What's Different from the Image Converter

| Image slideshow | VideoWiki slideshow |
|---|---|
| Auto-extracts all images from an article | Images are **hand-curated** per section |
| Needs `is_useful_image()` filter | No filtering needed |
| Commons metadata as captions | **Narration text** IS the caption |
| Single image per slide | **Multiple images** per section (one per slide) |

### Examples

```bash
# 8 slides, one per section
python3 videowiki-to-tapestry.py "Wikipedia:VideoWiki/Birthday_cake"

# 17 slides (15 sections, 2 have multiple images)
python3 videowiki-to-tapestry.py "Wikipedia:VideoWiki/A._P._J._Abdul_Kalam" --image-width 500

# From URL
python3 videowiki-to-tapestry.py "https://en.wikipedia.org/wiki/Wikipedia:VideoWiki/Birthday_cake"
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

**Playwright CLI** (only for `--screenshots`):
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
