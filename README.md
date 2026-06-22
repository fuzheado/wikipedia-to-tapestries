# Wikipedia → Tapestry Visual Map Converter

Converts any Wikipedia article into a `.zip` file for import into
[Tapestries](https://tapestries.media) — an infinite canvas multimedia authoring platform.

The output arranges the article as a visual map: **image gallery** at the top,
the **article itself** as an embedded webpage in the center, and **linked articles**
from the lead section below, connected with arrows. Includes a guided presentation
tour through all items.

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
| `--screenshots` | off | Capture real browser screenshots as webpage thumbnails |
| `--lang LANG` | `en` | Wikipedia language code |
| `--output`, `-o` | auto | Output `.zip` file path |

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

Screenshots make the file ~3× larger but give a much better preview of each page.

## Output Layout

```
┌──────────────────────────────────────────┐
│  Image Gallery (rows of thumbnails)       │
├──────────────────────────────────────────┤
│  Main Article (webpage embed)             │
│  ───────────────┬───────────────          │
│                  │              │
│              ┌──────┐    ┌──────┐         │
│              │Link 1│    │Link 2│         │
│              │500×400│   │500×400│        │
│              └──────┘    └──────┘         │
└──────────────────────────────────────────┘
```

The file includes a `presentation` array for guided navigation:
main article → all gallery images → all linked articles.

## File Format

The output conforms to the **v7 Tapestry export format** as deployed on
`tapestries.media`. The full format specification and validator live at:

**`~/.pi/agent/skills/tapestries/`** (Tapestry skill)

Key rules enforced by the converter:
- `version: 7` with `parentId`, `presentation`, `startView`, `thumbnail` at root
- File naming: `items/<uuid> (<name>).ext` (parentheses required)
- Text items: `title: ""`, `backgroundColor: "#ffffff00"`, no `customThumbnail`
- Media items: no `customThumbnail`, no `internallyHosted`, `title: ""`
- `.000Z` date format on `createdAt` and `updatedAt`
- Webpage URLs use `?useformat=mobile` for cleaner mobile embeds

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

## Credits

Built by reverse-engineering the Tapestry v7 export format from production
`.zip` files downloaded from `tapestries.media`. The Tapestry Project is
open source at [github.com/internetarchive/tapestry-project](https://github.com/internetarchive/tapestry-project).
