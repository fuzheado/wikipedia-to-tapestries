# PRD: Citation Graph — Wikipedia Article with Surrounding References

**Status:** ✅ Built and tested — v2
**Date:** 2026-06-29
**Feature:** Wikipedia → Tapestry Citation Graph
**File:** `wikipedia-citation-graph.py`

---

## 1. Executive Summary

A new Tapestry converter that renders any Wikipedia article as a **star graph**: 
the full article as a scrollable webpage embed in the center, surrounded by 
all its cited references, each rendered according to its type (webpage embed, 
PDF viewer, book embed, text card), with arrows connecting the article to 
each source.

The result is a **visual bibliography** — seeing all sources at once on an 
infinite canvas, with the article at the center and its evidence radiating 
outward. This makes the article's sourcing instantly visible: which claims 
are well-supported, which are bare text, and how the evidence is distributed.

---

## 2. User Story

> As a Wikipedia reader or editor, I want to see a Wikipedia article displayed 
> on an infinite canvas with every citation it uses laid out around it, so I 
> can visually explore the article's sources, see which are real webpages vs. 
> bare citations, and get a sense of the article's evidence landscape at a glance.

---

## 3. Design

### 3.1 Layout — "Star Graph" with U-Shaped References

The layout places the article at center stage with references arranged in a 
**U-shape** (or elongated semicircle) below and to the sides. Arrows connect 
the article item to each reference item.

```
┌────────────────────────────────────────────────────┐
│                                                    │
│                    ┌──────────────────┐            │
│                    │    ARTICLE       │            │
│                    │  (800px wide,    │            │
│                    │   tall scroll,   │            │
│                    │   mobile view)   │            │
│                    └────────┬─────────┘            │
│                             │                      │
│        ┌────rel 1───────────┤────────────rel 2───┐ │
│        │                    │                    │ │
│   ┌────┴────┐         ┌────┴────┐         ┌────┴────┐
│   │ Ref 1   │         │ Ref 2   │         │ Ref 3   │
│   │ (webpage│         │ (PDF)   │         │ (text)  │
│   │  embed) │         │  embed  │         │  card   │
│   └─────────┘         └─────────┘         └─────────┘
│                                                    │
│       ┌─────────┐      ┌─────────┐      ┌─────────┐
│       │ Ref 4   │      │ Ref 5   │      │ Ref 6   │
│       │ (book)  │      │(webpage)│      │ (text)  │
│       └─────────┘      └─────────┘      └─────────┘
│                                                    │
│           ┌─────────┐            ┌─────────┐      │
│           │ Ref 7   │            │ Ref 8   │      │
│           │ (webpage│            │ (ISBN)  │      │
│           └─────────┘            └─────────┘      │
└────────────────────────────────────────────────────┘
     ← infinite canvas → references wrap as needed
```

#### 3.1.1 Article Sizing
- **Width:** 800px — wider than the current visual map's 700px to show more text per line
- **Height:** 1200–2000px — tall enough to show a substantial portion of the article
  before scrolling; the full `useformat=mobile` view means dense content compresses
- **Position:** Centered horizontally at x=400 (center of canvas), y=MARGIN (top of canvas)
- **URL:** `https://{lang}.wikipedia.org/wiki/{title}?useformat=mobile` — mobile view for
  cleaner embed (no sidebars, no desktop chrome)
- **Thumbnail:** Article's lead image used as webpage thumbnail (matching existing pattern)

#### 3.1.2 Reference Sizing
- **Webpage items:** 450×350px — readable viewport for external URLs
- **PDF items:** 450×500px — taller to show more of the document
- **Book items:** 400×400px — square format for book covers
- **Text citation items:** 400×150px — compact text cards for non-URL citations
- **Placeholder items:** 400×120px — dimmed cards for unresolvable references

#### 3.1.3 Layout Algorithm

The references are arranged in a **U-shape** below the article using a semicircle 
layout with additional rows:

1. **First row (main arc):** Up to 8 references arranged in a semicircle below the
   article, connected by visible arrows. The arc has radius ~700px, centered on the
   article's centerline.
2. **Subsequent rows:** Additional references wrap into rows below the arc, using a
   centered grid layout with 3–4 columns per row.
3. **Spacing:** 40px between items, 60px between rows.

The U-shape keeps the article visually centered while the references cascade
outward — emulating a star graph where the center node has radiating spokes.

#### 3.1.4 Arrows (Rels)
- Each reference gets a `rel` from the article item to the reference item
- Arrow style: `color="#36c"` (Wikimedia blue), `weight="light"`, arrowhead at reference end
- This visually asserts "the article cites this source"

---

### 3.2 Reference Type Detection and Rendering

Each reference from the Wikipedia page is classified and rendered appropriately.

| Detected Type | Detection Criteria | Tapestry Item Type | Fallback |
|---|---|---|---|
| **Webpage URL** | URL begins `http://` or `https://`, doesn't match other types | `webpage` item with `source: <url>` | — |
| **PDF** | URL ends `.pdf` or contains `/pdf/` or `pdf?` | `pdf` item with `source: <url>` | `webpage` item if PDF fails |
| **ISBN** | Reference text contains `ISBN` or `Special:BookSources` | `book` item with `source` pointing to Google Books or Open Library API lookup | `text` item with ISBN shown |
| **DOI** | Reference text contains `doi:` or `doi.org` | `webpage` item resolving to `https://doi.org/{doi}` | `text` item with DOI shown |
| **PubMed / PMC** | Reference contains `PMID` or `PMCID` or text contains `ncbi.nlm.nih.gov` | `webpage` item pointing to PubMed abstract | `text` item with PMID shown |
| **arXiv** | URL contains `arxiv.org` | `webpage` item pointing to arXiv abstract page | `text` item with arXiv ID |
| **Bare citation** | No URL found — just citation template text (author, title, publisher) | `text` item with the citation rendered as HTML | — |
| **Unresolvable** | URL returns 404 or timeout on probe | `text` item with "⚠️ Dead link: [original URL]" | — |
| **Commons file** | URL points to `commons.wikimedia.org` | `image` or `webpage` item for the Commons file | `webpage` item |

#### 3.2.1 URL Probing (Optional — Behind `--probe` flag)

For reliable classification, optionally probe each URL with a HEAD request:
- **200 OK** → Resolvable webpage/PDF
- **404/410** → Dead link (show placeholder card)
- **Redirects to login/captcha** → Treat as unresolvable
- **Connection timeout/DNS failure** → Treat as dead

Default behavior (no `--probe`) uses URL pattern matching only.

---

### 3.3 Data Pipeline

```
1. Fetch rendered HTML  ──→  action=parse&page=TITLE&prop=text
2. Parse references     ──→  Extract <ol class="references"> → each <li>
3. Classify each ref    ──→  URL detection, PDF/ISBN/DOI/arXiv matching
4. Probe URLs (opt)     ──→  HEAD requests to verify liveness
5. Fetch Commons info   ──→  Lead image for article thumbnail
6. Build Tapestry       ──→  Article webpage + reference items + rels + presentation
7. Package .zip         ──→  v7-compliant zip output
```

#### 3.3.1 Step 1: Fetch Rendered HTML

```
GET https://en.wikipedia.org/w/api.php?action=parse&page=TITLE&prop=text&format=json
```

The `parse` response includes `parse.text.*` which contains the fully-rendered HTML
of the entire page, including the expanded `<ol class="references">` section.

#### 3.3.2 Step 2: Parse References

Use regex or `html.parser` (Python stdlib) to parse the references:

```python
import html.parser  # or re

def parse_references(rendered_html: str) -> list[dict]:
    """Extract all <li id="cite_note-..."> from the references section."""
    # Strategy: find the <ol class="references"> block, then find each
    # <li id="cite_note-..."> within it.
    # For each <li>:
    #   - Extract citation HTML from .mw-reference-text or .reference-text
    #   - Find first <a rel="nofollow"> for URL
    #   - Check for ISBN / DOI / PMID / arXiv patterns in text
    #   - Strip HTML tags for display text
```

**Known references HTML structure:**

```html
<div class="mw-references-wrap">
  <ol class="mw-references references">
    <li about="#cite_note-ABC-1" id="cite_note-ABC-1">
      <a href="#cite_ref-ABC_1-0"><span class="mw-linkback-text">↑ </span></a>
      <span id="mw-reference-text-cite_note-ABC-1" class="mw-reference-text">
        <cite class="citation web">
          <a rel="nofollow" class="external text" href="https://example.com">Title</a>
          ...
        </cite>
      </span>
    </li>
    ...
  </ol>
</div>
```

#### 3.3.3 Step 3: Classify References

```python
def classify_reference(ref_text: str, url: str | None) -> str:
    """Return one of: 'webpage', 'pdf', 'book', 'doi', 'pubmed', 'arxiv', 'text', 'dead'."""
    if url:
        if url.endswith('.pdf') or '/pdf/' in url.lower():
            return 'pdf'
        if 'doi.org' in url.lower():
            return 'doi'
        if 'arxiv.org' in url.lower():
            return 'arxiv'
        if 'ncbi.nlm.nih.gov' in url.lower() or 'pubmed' in url.lower():
            return 'pubmed'
        return 'webpage'
    if 'ISBN' in ref_text:
        return 'book'
    return 'text'
```

#### 3.3.4 Step 5: Fetch Lead Image (existing pattern)

Uses the REST API `/page/summary/{title}` to get thumbnail, then downloads it
for the root-level `thumbnail` field in the Tapestry zip (same pattern as
`wikipedia-to-tapestry.py`).

---

### 3.4 Presentation (Guided Tour)

The presentation steps walk the viewer through the graph:

1. **Start:** Full view showing all items (startView calculated from bounding box)
2. **Step 1:** Focus on the article (webpage item)
3. **Step 2–N:** Focus on each reference in citation order, one by one

The `startView` is dynamically calculated from item bounding boxes with padding.

---

### 3.5 Color Coding

Each reference type gets a colored border or header to make the graph
visually scannable at a glance:

| Type | Visual Cue |
|---|---|
| Webpage | Blue header strip (`#36c`) |
| PDF | Red header strip (`#d33`) |
| Book | Green header strip (`#14866d`) |
| DOI / Academic | Purple header strip (`#6b4ba1`) |
| Bare text citation | Grey/no header (`#72777d`) |
| Dead link | Red tinted, ⚠️ icon |

The coloring system is implemented as a small text item above each reference
that acts as a colored label tag (not an actual header on the item itself, 
since Tapestry items don't support colored headers natively).

---

### 3.6 Item Naming Convention

All items follow the existing v7 file naming convention:
- `items/<uuid> (<citation-index> <type-shortcut> <short-title>).ext`
- Example: `items/550e8400-e29b-41d4-a716-446655440000 (1 webpage World Health Organization.md)`

---

## 4. Command-Line Interface

```bash
python3 wikipedia-citation-graph.py "Article Title" [options]
python3 wikipedia-citation-graph.py "https://en.wikipedia.org/wiki/Article_Title"
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--lang LANG` | `en` | Wikipedia language code |
| `--max-refs N` | 50 | Maximum references to include (0 = all) |
| `--article-width N` | 800 | Article embed width in pixels |
| `--article-height N` | 1500 | Article embed height in pixels |
| `--ref-width N` | 450 | Reference embed width in pixels |
| `--probe` | off | Probe URLs with HEAD request to detect dead links |
| `--probe-timeout N` | 10 | Timeout in seconds for URL probing |
| `--output`, `-o` | auto | Output `.zip` file path |
| `--min-refs` | 2 | Minimum references needed to generate output (skip articles with < N) |

---

## 5. Output Example

```bash
python3 wikipedia-citation-graph.py "Chess" -o chess-citations.zip
```

Expected output:
```
📄 Fetching Wikipedia article: Chess
────────────────────────────────────────────────────
   Title:       Chess
   Lead image:  yes
   References found: 173
   Including up to: 50

🔍 Classifying references...
   [1/50] https://www.fide.com/... → webpage
   [2/50] https://example.com/book.pdf → PDF
   [3/50] ISBN 978-0-13-000... → book
   [4/50] doi:10.1126/... → DOI
   ...

🎨 Building Citation Graph layout...
   Article (800×1500)
   Ref 1: webpage at (1030, 500)
   Ref 2: PDF at (470, 500)
   ...

✅ Tapestry saved to: chess-citations.zip
   Items: 51 (1 article + 50 references)
   Rels:  50 arrows
   References types: 32 webpage, 8 PDF, 5 book, 3 DOI, 2 bare text
```

---

## 6. Edge Cases & Constraints

### 6.1 References That Reuse Named Refs (`<ref name="...">`)
Wikipedia often uses the same citation multiple times. The rendered HTML uses
the same `cite_note` anchor ID. We deduplicate by extracting the `cite_note`
base name and only creating one Tapestry item per unique reference.

### 6.2 Articles With No References
Show a single text card: "ℹ️ This article has no citations."

### 6.3 Articles With Too Many References (e.g., 800+)
- Hard cap at `--max-refs` (default 50)
- Beyond 50, show a summary card: "📄 +247 more references not shown (use --max-refs N)"
- The layout for large numbers causes the canvas to become very wide; the 
  U-shape gracefully degrades into a horizontal scroll rather than wrapping,
  which is acceptable on an infinite canvas.

### 6.4 Reference URLs That Don't Load in iframes (X-Frame-Options)
Many sites block iframe embedding (`X-Frame-Options: DENY` or `SAMEORIGIN`).
For these, the `webpage` item in Tapestry will show a blank/grey screen. 
We **do not attempt to detect this** (it would require a full browser render) — 
the user sees the blank embed and can still open the URL in a new tab using
an action button overlay (future enhancement).

### 6.5 Multi-column References
Some articles use `{{Reflist|colwidth=30em}}` which renders multi-column
references. The HTML parser handles this transparently since the `<ol>` 
structure is the same regardless of CSS columns.

### 6.6 Grouped References (`{{efn}}` / `{{notelist}}`)
Footnotes and explanatory notes may appear in separate `<ol>` groups. 
We extract from **all** `<ol class="mw-references references">` blocks.

### 6.7 Non-English Wikipedia
The parser works for any language — the HTML structure of the references
section is identical across all Wikimedia wikis. The `--lang` flag already
handles this.

---

## 7. Technical Architecture

### 7.1 File Structure

```
~/Documents/ai/tapestry-converter/
├── wikipedia-citation-graph.py       # NEW — the Citation Graph converter
├── citation_graph_renderers.py       # NEW (optional) — separate reference
│                                     # type rendering helpers if complex
└── (reuses SESSION, wiki_request,
     make_id, TapestryBuilder
     patterns from existing code)
```

### 7.2 Reuse Strategy
The new converter reuses the following patterns from existing code:

| Pattern | Source | Notes |
|---|---|---|
| `SESSION` / `wiki_request` | All converters | Shared UA, rate-limiting, retry |
| `make_id()` | All converters | UUID generation |
| `TapestryBuilder.add_webpage_item()` | `wikipedia-to-tapestry.py` | Adapt for reusability |
| `TapestryBuilder.add_rel()` | `wikipedia-to-tapestry.py` | Arrow from article to ref |
| `fetch_page_summary()` | `wikipedia-to-tapestry.py` | Lead image + description |
| `download_image()` | `wikipedia-to-tapestry.py` | Thumbnail binary fetch |
| StartView calculation | All converters | Bounding box |
| Presentation pattern | All converters | Step-by-step tour |
| Rate-limiting | All converters | 300ms delays, 429 retry |

Rather than duplicating the class, the citation graph builder can be a new
standalone class `CitationGraphBuilder` that follows the same API surface
as `TapestryBuilder` but adds reference-type-specific rendering methods.

### 7.3 Builder Class Design

```python
class CitationGraphBuilder:
    """Builds a v7 Tapestry with article + citation star graph layout."""

    def __init__(self, title, description="", thumbnail_url=""):
        # Standard v7 root + binary files dict

    def add_article(self, x, y, w, h, source_url, thumb_url=""):
        """Add the main article as a scrolling webpage item."""
        pass

    def add_webpage_ref(self, x, y, w, h, url, label=""):
        """Add a webpage reference embed."""
        pass

    def add_pdf_ref(self, x, y, w, h, url, label=""):
        """Add a PDF reference embed."""
        pass

    def add_book_ref(self, x, y, w, h, isbn, label=""):
        """Add a book reference (Google Books embed or ISBN text)."""
        pass

    def add_text_ref(self, x, y, w, h, citation_html):
        """Add a bare-text citation as a text card."""
        pass

    def add_placeholder_ref(self, x, y, w, h, message):
        """Add a placeholder for unresolvable references."""
        pass

    def add_ref_label(self, x, y, w, h, type_label, color=""):
        """Add a colored type label above a reference."""
        pass

    def add_rel(self, from_id, to_id):
        """Connect article ref → reference item."""
        pass

    def set_presentation(self, article_id, ref_ids):
        """Build presentation tour: article first, then each ref in order."""
        pass

    def save_zip(self, output_path):
        """Write .zip (identical pattern to existing builders)."""
        pass
```

---

## 8. Implementation Plan

### Phase 1 (Core — this PRD)
- ✅ Spec and PRD written
- 🔲 `wikipedia-citation-graph.py` — reference parser (HTML-based)
- 🔲 `CitationGraphBuilder` — article + reference layout
- 🔲 CLI with all options
- 🔲 U-shape layout algorithm
- 🔲 Rels with arrows from article to each reference
- 🔲 Presentation tour
- 🔲 Validation with sample output

### Phase 2 (Polish)
- 🔲 `--probe` flag for URL liveness detection
- 🔲 Color-coded type labels on references
- 🔲 Dead link indicators
- 🔲 Action buttons on each reference ("Open in new tab")

### Phase 3 (Advanced)
- 🔲 DOI → CrossRef metadata enrichment (author, year, journal)
- 🔲 ISBN → Open Library / Google Books cover images
- 🔲 Full-reference citation count summary card
- 🔲 Batch mode (convert list of articles)

---

## 9. Acceptance Criteria


1. **Given** a Wikipedia article title, **when** the converter runs, **then** a valid v7 `.zip` is produced containing:
   - 1 `webpage` item for the article
   - N reference items (one per unique reference found)
   - N `rel` arrows connecting article → each reference
   - A `presentation` array stepping through the article then each reference
   - A `startView` showing all items

2. **Given** an article with 173 references and `--max-refs 50`, **when** the converter runs, **then** exactly 50 reference items are included plus a summary card noting 123 more.

3. **Given** an article with no references, **when** the converter runs, **then** the zip contains 1 article item + 1 "no references" text card.

4. **Given** a `--probe` flag, **when** a reference URL returns 404, **then** it is classified as "dead" and rendered as a placeholder card.

5. **Given** the output zip, **when** validated with `validate-tapestry.py`, **then** it passes all v7 format checks.

---

## 10. Test Articles
Three articles of escalating size for iterative testing and validation:

| Generated File | Size | Refs | Layout | Notes |
|---|---|---|---|---|
| `samples/Seven_dirty_words_citation_graph.zip` | 644 KB | 16/16 | Positioned U | Latest — refs at article positions, screenshots, numbered badges |
| `samples/Alan_Greenspan_citation_graph.zip` | 75 KB | 40/180 | U-shape | Medium article |
| `samples/Supreme_Court_citation_graph.zip` | 236 KB | 80/386 | Ring | Large article, stress test |

### Current Implementation Status

- **Positioned layout (default `u`):** Each reference is placed at the approximate vertical position where its citation first appears in the article. Arrows shoot from the article's right edge at that Y position to the reference card. Clustered citations (multiple refs at the same article location) fan out horizontally with staggered Y offsets.
- **Ring/grid layouts:** Alternative layouts that don't use article positioning.
- **Numbered badges:** Each reference has a colored circle badge with its citation number.
- **Thumbnails:** `--screenshots` captures real browser screenshots via Playwright CLI for both the article and source pages, used as item thumbnails in Tapestry.
- **Overflow cap:** `--max-refs N` limits references; overflow items get a summary card.

## 11. Future Directions

- **Auto-play article-to-ref cycling** — Presentation could auto-advance through references
- **Citation clustering by section** — Group references by which section cites them,
  creating multiple sub-clusters around the article
- **Citation strength indicators** — Color-code refs by how many times they're cited
  in the article (named ref reuse count)
- **Interactive mode** — Click a reference to see which sections cite it (requires
  viewer-side support)
- **Reference sidebar** — A text panel listing all citations as an index, with
  action buttons to jump to each reference's position
- **Cross-article citation overlay** — When multiple articles share the same source,
  show network overlap
