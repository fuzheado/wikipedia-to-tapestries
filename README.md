# Wikipedia → Tapestry Visual Map Converter

Converts any Wikipedia article into a `.zip` file for import into
[Tapestries](https://tapestries.media) — an infinite canvas multimedia authoring platform.

The output is a visual map: **image gallery** at the top (center-aligned rows),
the **article itself** as an embedded webpage in the center, and **linked articles**
from the lead section below in either a grid or semicircle layout, connected with arrows.
Includes a guided presentation tour through all items and a dynamic start view.

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

# 4. Upload to Tapestries
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
The Tapestry Project is open source at
[github.com/internetarchive/tapestry-project](https://github.com/internetarchive/tapestry-project).
The Tapestry format skill is at
[github.com/fuzheado/tapestries-skill](https://github.com/fuzheado/tapestries-skill).
