#!/usr/bin/env python3
"""
Wikipedia Article → Citation Graph Tapestry

Renders any Wikipedia article as a star graph on Tapestry's infinite canvas:
the full article as a full-page screenshot image in the center, flanked on
both sides by its cited references, each rendered according to its type
(webpage embed, PDF viewer, book cover, DOI resolver, or text card), with
arrows connecting the citation positions in the article to each source.

Three layout modes:
  u (default) — Positioned layout: refs flank the article on both left and
                right sides at their citation positions in the article
  ring        — Full ring around the article center
  grid        — Centered grid below the article

Usage:
  python3 wikipedia-citation-graph.py "Article Title" [options]
  python3 wikipedia-citation-graph.py "https://en.wikipedia.org/wiki/Article_Title"

Examples:
  python3 wikipedia-citation-graph.py "Seven dirty words" -o seven-words-cites.zip
  python3 wikipedia-citation-graph.py "Seven dirty words" --screenshots -o seven-words-screenshots.zip
  python3 wikipedia-citation-graph.py "Alan Greenspan" --max-refs 40 -o greenspan-cites.zip
  python3 wikipedia-citation-graph.py "Supreme Court of the United States" \
      --layout ring --max-refs 80 -o scotus-cites.zip
"""

import argparse
import html as html_mod
import io
import json
import math
import os
import re
import sys
import time
import uuid
import zipfile
from urllib.parse import quote, unquote

import requests

# ── Configuration ──────────────────────────────────────────────────────────

USER_AGENT = (
    "WikipediaCitationGraphBot/1.0 (andrew.lih@gmail.com) WikiCitationGraph"
)
REST_API = "https://{lang}.wikipedia.org/api/rest_v1"
ACTION_API = "https://{lang}.wikipedia.org/w/api.php"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})

# Layout constants (pixels)
MARGIN = 60
ARTICLE_WIDTH = 800
REF_WIDTH = 450
REF_COL_GAP = 24
REF_ROW_GAP = 36
ARC_RADIUS = 700
ARC_MAX = 10          # Max refs on the main arc
ARC_ROW_COLS = 4      # Columns in overflow rows (U-shape)
RING_RADIUS_INNER = 650
RING_RADIUS_OUTER = 900
GRID_MAX_COLS = 6

# Reference type display sizes
REF_HEIGHTS = {
    "webpage": 320,
    "pdf": 460,
    "book": 380,
    "doi": 320,
    "pubmed": 320,
    "arxiv": 320,
    "text": 140,
    "dead": 100,
}

# Label tag dimensions
LABEL_HEIGHT = 22
LABEL_GAP = 4

# Type label colors
TYPE_COLORS = {
    "webpage": "#36c",      # Wikimedia blue
    "pdf": "#d33",          # Red
    "book": "#14866d",      # Green
    "doi": "#6b4ba1",       # Purple
    "pubmed": "#e07020",    # Orange
    "arxiv": "#a01e6f",     # Magenta
    "text": "#72777d",      # Grey
    "dead": "#b32424",      # Dark red
}

TYPE_LABELS = {
    "webpage": "🌐 Webpage",
    "pdf": "📄 PDF",
    "book": "📖 Book",
    "doi": "🔗 DOI",
    "pubmed": "🏥 PubMed",
    "arxiv": "📋 arXiv",
    "text": "📝 Citation",
    "dead": "⚠️ Dead Link",
}

# Screenshot cache
SCREENSHOT_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    ".screenshot_cache",
)
SCREENSHOT_CACHE_ENABLED = True


def _clear_cache():
    """Delete all cached screenshots."""
    import shutil
    if os.path.exists(SCREENSHOT_CACHE_DIR):
        shutil.rmtree(SCREENSHOT_CACHE_DIR)
        print("🗑️  Screenshot cache cleared")


def _cache_key(url: str, w: int, h: int, full: bool) -> str:
    """Generate a deterministic cache filename for a screenshot."""
    import hashlib
    raw = f"{url}|{w}x{h}|full={full}"
    return hashlib.sha256(raw.encode()).hexdigest()[:20] + ".png"


def _cache_get(url: str, w: int, h: int, full: bool) -> bytes | None:
    """Return cached screenshot bytes, or None if not cached."""
    if not SCREENSHOT_CACHE_ENABLED:
        return None
    path = os.path.join(SCREENSHOT_CACHE_DIR, _cache_key(url, w, h, full))
    if os.path.exists(path):
        with open(path, "rb") as f:
            data = f.read()
        if len(data) > 1000:
            return data
    return None


def _cache_put(url: str, w: int, h: int, full: bool, data: bytes):
    """Store screenshot bytes in cache."""
    if not SCREENSHOT_CACHE_ENABLED:
        return
    os.makedirs(SCREENSHOT_CACHE_DIR, exist_ok=True)
    path = os.path.join(SCREENSHOT_CACHE_DIR, _cache_key(url, w, h, full))
    with open(path, "wb") as f:
        f.write(data)

# ── Helpers ────────────────────────────────────────────────────────────────


def make_id() -> str:
    return str(uuid.uuid4())


def wiki_request(url, params=None, max_retries=3):
    """Generic Wikimedia API request with retry, UA, and rate-limit handling."""
    for attempt in range(max_retries):
        resp = SESSION.get(url, params=params, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 10))
            print(f"  ⏳ Rate limited — waiting {retry_after}s...", file=sys.stderr)
            time.sleep(retry_after)
            continue
        if resp.status_code == 403:
            raise PermissionError(
                "403 Forbidden — check User-Agent header. "
                + resp.text
            )
        resp.raise_for_status()
    raise RuntimeError(f"Failed after {max_retries} retries")


def fetch_page_summary(lang: str, title: str) -> dict:
    """Get page summary via REST API — includes title, description, extract, thumbnail."""
    url = REST_API.format(lang=lang) + f"/page/summary/{quote(title, safe='')}"
    return wiki_request(url)


def download_image(url: str, name_hint: str = "img") -> bytes | None:
    """Download image bytes, return None on failure with rate limiting."""
    time.sleep(0.3)
    try:
        resp = SESSION.get(url, timeout=30)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        print(f"  ⚠️  Could not download {name_hint}: {e}", file=sys.stderr)
        return None


def capture_page_screenshot(url: str, output_path: str,
                             viewport_w: int = 800,
                             viewport_h: int = 600,
                             full_page: bool = False) -> bytes | None:
    """Capture a webpage screenshot using Playwright CLI.

    If full_page is True, uses playwright-cli run-code to capture the
    entire page from top to bottom with no scrolling (fullPage: true).
    Otherwise captures the current viewport.

    Returns PNG bytes, or None on failure.
    """
    import subprocess
    import tempfile

    # Check cache first
    cached = _cache_get(url, viewport_w, viewport_h, full_page)
    if cached is not None:
        # Still write to output_path if caller expects it there
        with open(output_path, "wb") as f:
            f.write(cached)
        return cached

    try:
        if full_page:
            # Full-page screenshot via run-code (set viewport, then fullPage: true)
            code = (
                f'async page => {{\n'
                f'  await page.setViewportSize({{ width: {viewport_w}, height: {viewport_h} }});\n'
                f'  await page.goto("{url}", {{ waitUntil: "networkidle", timeout: 45000 }});\n'
                f'  await page.screenshot({{ path: "{output_path}", fullPage: true }});\n'
                f'  return "done";\n'
                f'}}'
            )
            subprocess.run(
                ["playwright-cli", "run-code", code],
                capture_output=True, timeout=120, check=False
            )
        else:
            subprocess.run(
                ["playwright-cli", "goto", url],
                capture_output=True, timeout=30, check=False
            )
            subprocess.run(
                ["playwright-cli", "resize", str(viewport_w), str(viewport_h)],
                capture_output=True, timeout=10, check=False
            )
            subprocess.run(
                ["playwright-cli", "screenshot", "--filename", output_path],
                capture_output=True, timeout=30, check=False
            )
        if os.path.exists(output_path):
            with open(output_path, "rb") as f:
                data = f.read()
            os.remove(output_path)
            if len(data) > 1000:
                _cache_put(url, viewport_w, viewport_h, full_page, data)
                return data
        return None
    except Exception as e:
        print(f"  ⚠️  Screenshot failed for {url}: {e}", file=sys.stderr)
        return None


def capture_article_with_positions(
    url: str,
    output_path: str,
    viewport_w: int = 800,
    viewport_h: int = 600,
) -> tuple[bytes | None, dict[str, int]]:
    """Capture full-page article screenshot and actual citation Y positions.

    Uses Playwright to navigate to the article, take a fullPage screenshot,
    and measure each citation <sup> element's exact Y position from the
    top of the page via client-side JS.

    Returns (screenshot_bytes, {ref_name: pixel_y_from_top}).
    The pixel Y is 0-based from the top of the full page image.
    """
    import subprocess
    import json

    # Step 1: Capture screenshot (cached via capture_page_screenshot)
    screenshot_data = capture_page_screenshot(
        url, output_path,
        viewport_w=viewport_w, viewport_h=viewport_h,
        full_page=True,
    )
    if not screenshot_data or len(screenshot_data) < 1000:
        return None, {}

    # Step 2: Measure citation positions (separate, fast JS call)
    q = chr(34)
    measure_js = (
        "async page => {\n"
        + '  await page.setViewportSize({ width: ' + str(viewport_w)
        + ', height: ' + str(viewport_h) + ' });\n'
        + '  await page.goto(' + q + url + q
        + ', { waitUntil: "networkidle", timeout: 45000 });\n'
        + '  await page.waitForSelector(' + q + 'sup.reference a' + q
        + ', { timeout: 10000 }).catch(() => {});\n'
        + '  const pos = await page.evaluate(() => {\n'
        + '    const r = {};\n'
        + '    const as = document.querySelectorAll(\"sup.reference a\");\n'
        + '    for (const a of as) {\n'
        + '      const h = a.getAttribute(\"href\");\n'
        + '      if (!h || !h.startsWith(\"#cite_note-\")) continue;\n'
        + '      const n = h.replace(\"#cite_note-\", \"\");\n'
        + '      const b = n.replace(/-\\d+$/, \"\");\n'
        + '      if (!r[b]) r[b] = Math.round(a.getBoundingClientRect().top);\n'
        + '    }\n'
        + '    return r;\n'
        + '  });\n'
        + '  return JSON.stringify(pos);\n'
        + "}"
    )
    try:
        result = subprocess.run(
            ["playwright-cli", "run-code", measure_js],
            capture_output=True, timeout=120, text=True, check=False
        )
        positions_raw = {}
        if result.stdout:
            out = result.stdout.strip()
            in_result = False
            for line in out.split("\n"):
                line = line.strip()
                if line.startswith("### Result"):
                    in_result = True
                    continue
                if in_result and line:
                    try:
                        outer = json.loads(line)
                        if isinstance(outer, str):
                            positions_raw = json.loads(outer)
                        elif isinstance(outer, dict):
                            positions_raw = outer
                    except (json.JSONDecodeError, TypeError):
                        pass
                    break
        positions = {k: int(v) for k, v in positions_raw.items()}
        return screenshot_data, positions
    except Exception as e:
        print(f"  \u26a0\ufe0f  Position measurement failed: {e}", file=sys.stderr)
        return screenshot_data, {}



def strip_html(html_text: str) -> str:
    """Strip HTML tags, decode entities, collapse whitespace."""
    text = re.sub(r"<[^>]+>", "", html_text)
    text = html_mod.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def estimate_article_height(rendered_html: str) -> int:
    """Estimate article height from rendered HTML content length.

    Heuristic: ~1px per 2.5 characters of visible body text, plus padding,
    giving a rough scroll height. The mobile stylesheet compresses content
    vertically, so this is intentionally generous.
    """
    # Extract text from the body content (everything up to the references)
    ref_idx = rendered_html.find('class="mw-references-wrap"')
    if ref_idx < 0:
        ref_idx = rendered_html.find('id="References"')

    body_html = rendered_html[:ref_idx] if ref_idx > 0 else rendered_html

    # Strip tags to get visible text
    text = strip_html(body_html)
    # Estimate: 2.5 chars per px for mobile view
    height = max(1500, int(len(text) / 2.5))
    # Cap at a reasonable max (you can override with --max-height)
    return min(height, 30000)


# ── Reference Parser ─────────────────────────────────────────────────────


def parse_references(rendered_html: str) -> list[dict]:
    """Parse all unique references from the rendered Wikipedia HTML.

    Returns deduplicated list of dicts:
        {
            "index": int,          # 1-based citation number
            "ref_name": str,       # Base ref name (e.g. "umkc")
            "url": str | None,     # External URL found, or None
            "ref_type": str,       # One of: webpage, pdf, book, doi, pubmed, arxiv, text, dead
            "label": str,          # Short display label
            "text": str,           # Clean citation text (HTML stripped)
            "raw_html": str,       # Original reference-text HTML
        }
    """
    # Find all <li id="cite_note-..."> within reference blocks.
    # NOTE: Wikipedia action=parse HTML encodes underscores in IDs as &#95;
    # The ID format is: id="cite&#95;note-REFNAME" or id="cite&#95;note-REFNAME-INDEX"
    # Some pages may use literal underscores too.
    underscore = r"(?:&#95;|_)"
    ref_pattern = re.compile(
        r'<li[^>]*id="cite' + underscore + r'note-([^"]+)"[^>]*>'
        r'.*?'
        r'<span[^>]*class="(?:mw-)?reference-text"[^>]*>'
        r'(.*?)'
        r'</span>',
        re.DOTALL,
    )

    seen = {}  # base_ref_name → first occurrence data
    for m in ref_pattern.finditer(rendered_html):
        raw_id = m.group(1)
        ref_html = m.group(2).strip()

        # Derive base ref name (strip trailing -N index)
        base = re.sub(r'-\d+$', '', raw_id)

        # Skip if we already have this ref (keep first occurrence)
        if base in seen:
            continue

        # Extract URL from <a rel="nofollow" ... href="...">
        url_match = re.search(
            r'<a[^>]*rel="nofollow"[^>]*href="([^"]+)"',
            ref_html,
        )
        url = url_match.group(1) if url_match else None

        # Clean reference text for display
        clean_text = strip_html(ref_html)
        # Truncate long text
        label = clean_text[:80]
        if len(clean_text) > 80:
            label += "…"

        # Classify reference type
        ref_type = classify_reference(clean_text, url)

        # Re-extract URL for ISBN/DOI/internal — still capture what we found
        if not url:
            # Check for ISBN link patterns
            isbn_match = re.search(
                r'Special:BookSources[/?]([0-9X\-]+)',
                ref_html,
            )
            if isbn_match:
                url = "https://en.wikipedia.org/wiki/Special:BookSources/" + isbn_match.group(1)
            # Check for internal /wiki/ links that might be useful
            wiki_link = re.search(
                r'<a[^>]*href="(/wiki/[^"]+)"[^>]*>',
                ref_html,
            )

        # Extract ISBN number separately for book covers
        isbn = None
        if ref_type == "book":
            isbn_m = re.search(r'ISBN\s*([0-9X\-]{10,17})', clean_text, re.IGNORECASE)
            if isbn_m:
                isbn = isbn_m.group(1)

        # Extract DOI for DOI type
        doi = None
        if ref_type == "doi":
            doi_m = re.search(r'(10\.\d{4,}/[^\s,;<"\']+)', clean_text)
            if doi_m:
                doi = doi_m.group(1)

        seen[base] = {
            "ref_name": base,
            "url": url,
            "ref_type": ref_type,
            "label": label,
            "text": clean_text,
            "raw_html": ref_html,
            "isbn": isbn,
            "doi": doi,
        }

    # Convert to list with sequential indices
    result = []
    for idx, (base, data) in enumerate(seen.items(), 1):
        data["index"] = idx
        result.append(data)

    return result


def classify_reference(text: str, url: str | None) -> str:
    """Classify a reference into one of the known types."""
    if url:
        url_lower = url.lower()
        # Check for PDF
        if url_lower.endswith(".pdf") or "/pdf/" in url_lower or "pdf=" in url_lower:
            return "pdf"
        # Check for DOI
        if "doi.org" in url_lower:
            return "doi"
        # Check for arXiv
        if "arxiv.org" in url_lower:
            return "arxiv"
        # Check for PubMed
        if "ncbi.nlm.nih.gov" in url_lower or "pubmed" in url_lower:
            return "pubmed"
        # Default: webpage
        return "webpage"

    # No URL — check text patterns
    if re.search(r'\bISBN\b', text, re.IGNORECASE):
        return "book"
    if re.search(r'\bDOI\b', text, re.IGNORECASE) or re.search(r'10\.\d{4,}/', text):
        return "doi"
    if re.search(r'\b(PMID|PMCID)\b', text, re.IGNORECASE):
        return "pubmed"
    if re.search(r'\barxiv\b', text, re.IGNORECASE):
        return "arxiv"

    return "text"


# ── Layout Calculators ────────────────────────────────────────────────────


def layout_positioned_both_sides(
    article_x: int, article_y: int, article_w: int, article_h: int,
    refs: list[dict], ref_w: int, ref_h_map: dict[str, int],
    citation_ys: dict[str, int] | None = None,
) -> tuple[list[dict], list[float], list[str]]:
    """Position refs on both sides of the article at their citation Y positions.

    Refs are alternated between left and right sides, flanking the article.
    Clustered refs (same Y) are fanned outward horizontally and staggered
    vertically on their respective sides.

    Returns (positions, y_anchors, sides) where:
      - positions: list of {ref, x, y, w, h} dicts
      - y_anchors: [0..1] ratios for arrow Y origination
      - sides: ["left"|"right"] for each ref
    """
    positions = []
    y_anchors: list[float] = []
    sides: list[str] = []

    if not refs:
        return [], [], []

    # Build Y positions for each ref
    ref_ys: list[int] = []
    for ref_data in refs:
        ref_name = ref_data["ref_name"]
        if citation_ys and ref_name in citation_ys:
            y = citation_ys[ref_name]
        else:
            # Fallback: evenly spaced by index
            idx = ref_data["index"]
            y = article_y + int(article_h * idx / (len(refs) + 1))
        ref_ys.append(y)

    # Alternate sides by index order (first ref left, second right, etc.)
    # But also distribute: even indices → left, odd indices → right
    # This naturally balances refs across both sides

    # Detect clusters for staggering
    CLUSTER_GAP = 150
    sorted_pairs = sorted(enumerate(ref_ys), key=lambda p: p[1])

    clusters: list[list[int]] = []
    current_cluster: list[int] = []
    for idx, y in sorted_pairs:
        if not current_cluster:
            current_cluster = [idx]
        else:
            prev_idx = current_cluster[-1]
            prev_y = ref_ys[prev_idx]
            if abs(y - prev_y) <= CLUSTER_GAP:
                current_cluster.append(idx)
            else:
                clusters.append(current_cluster)
                current_cluster = [idx]
    if current_cluster:
        clusters.append(current_cluster)

    CLUSTER_FAN = 24
    for cluster in clusters:
        cluster_ys = [ref_ys[i] for i in cluster]
        n_in_cluster = len(cluster)
        # Restore original order within cluster for side assignment
        cluster_in_order = sorted(cluster, key=lambda i: refs[i]["index"])
        cluster_anchor_y = cluster_ys[0] if cluster_ys else (article_y + article_h // 2)

        for j, orig_idx in enumerate(cluster_in_order):
            ref_data = refs[orig_idx]
            ref_h = ref_h_map.get(ref_data["ref_type"], REF_HEIGHTS["webpage"])

            # Alternate sides: even j → left, odd j → right within cluster
            side = "left" if j % 2 == 0 else "right"
            # For single-item clusters, alternate globally by index
            if n_in_cluster == 1:
                side = "left" if ref_data["index"] % 2 == 1 else "right"

            fan_offset = (j - (n_in_cluster - 1) / 2) * CLUSTER_FAN
            ry = cluster_anchor_y + fan_offset - ref_h // 2

            if side == "left":
                # Place to the left of the article, with stagger going further left
                stagger_offset = j * (ref_w + REF_COL_GAP)
                rx = article_x - MARGIN - ref_w - stagger_offset
            else:
                # Place to the right of the article, with stagger going further right
                stagger_offset = j * (ref_w + REF_COL_GAP)
                rx = article_x + article_w + MARGIN + stagger_offset

            positions.append({
                "ref": ref_data,
                "x": int(rx),
                "y": max(article_y + 20, int(ry)),
                "w": ref_w,
                "h": ref_h,
            })

            anchor_y = max(0.0, min(1.0, (cluster_anchor_y - article_y) / max(article_h, 1)))
            y_anchors.append(anchor_y)
            sides.append(side)

    return positions, y_anchors, sides


def layout_ring(
    article_x: int, article_y: int, article_w: int, article_h: int,
    refs: list[dict], ref_w: int, ref_h_map: dict[str, int],
) -> list[dict]:
    """Full ring layout: references circle the article in an ellipse.

    Uses a double ring when >30 refs.
    """
    positions = []
    n = len(refs)
    cx = article_x + article_w // 2
    cy = article_y + article_h // 2

    # Determine ring parameters
    if n <= 30:
        # Single ring
        rings = [(RING_RADIUS_INNER, refs)]
    else:
        # Double ring: split refs between inner and outer
        mid = n // 2
        rings = [(RING_RADIUS_INNER, refs[:mid]), (RING_RADIUS_OUTER, refs[mid:])]

    for ring_radius, ring_refs in rings:
        count = len(ring_refs)
        for i, ref_data in enumerate(ring_refs):
            ref_h = ref_h_map.get(ref_data["ref_type"], REF_HEIGHTS["webpage"])
            # Full 360°, but skip the top section so refs don't sit above the article title
            angle_offset = -math.pi / 2  # Start at top
            span = 2 * math.pi * 0.85     # Leave 15% gap at top
            angle = angle_offset - span / 2 + (i / max(count - 1, 1)) * span
            rx = cx + ring_radius * math.cos(angle) - ref_w // 2
            ry = cy + ring_radius * math.sin(angle) - ref_h // 2
            positions.append({
                "ref": ref_data,
                "x": int(rx),
                "y": int(ry),
                "w": ref_w,
                "h": ref_h,
            })

    return positions


def layout_grid(
    article_x: int, article_y: int, article_w: int, article_h: int,
    refs: list[dict], ref_w: int, ref_h_map: dict[str, int],
) -> list[dict]:
    """Grid below layout: references as a centered grid below the article."""
    positions = []
    n = len(refs)
    cx = article_x + article_w // 2
    grid_top = article_y + article_h + MARGIN

    cols = max(1, min(int(math.ceil(math.sqrt(n))), GRID_MAX_COLS))
    total_row_w = cols * ref_w + (cols - 1) * REF_COL_GAP
    row_x_start = cx - total_row_w // 2

    for i, ref_data in enumerate(refs):
        col = i % cols
        row = i // cols
        ref_h = ref_h_map.get(ref_data["ref_type"], REF_HEIGHTS["webpage"])
        rx = row_x_start + col * (ref_w + REF_COL_GAP)
        ry = grid_top + row * (ref_h + REF_ROW_GAP)
        positions.append({
            "ref": ref_data,
            "x": int(rx),
            "y": int(ry),
            "w": ref_w,
            "h": ref_h,
        })

    return positions


# ── Tapestry Builder ──────────────────────────────────────────────────────


class CitationGraphBuilder:
    """Builds a v7 Tapestry zip for the Citation Graph."""

    def __init__(self, title: str, description: str = ""):
        self.root = {
            "version": 7,
            "id": make_id(),
            "title": title,
            "description": description or None,
            "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "items": [],
            "rels": [],
            "groups": [],
            "parentId": None,
            "presentation": [],
            "startView": None,
            "thumbnail": None,
            "theme": "light",
            "background": "#f8f9fa",
        }
        self._binary_files = {}

    def add_article_image(
        self, x: int, y: int, w: int, h: int,
        image_data: bytes, title: str = "",
    ) -> str:
        """Add the full-page article screenshot as an image item.

        The image is stored as a binary file in the zip and displayed
        at its natural size on the canvas.
        """
        item_id = make_id()
        fname = f"items/{item_id} (article).png"
        self._binary_files[fname] = image_data

        item = {
            "id": item_id,
            "type": "image",
            "position": {"x": x, "y": y},
            "size": {"width": w, "height": h},
            "title": title or "",
            "dropShadow": True,
            "groupId": None,
            "notes": None,
            "source": f"file:/{fname}",
        }
        self.root["items"].append(item)

        # Also use this screenshot as the root thumbnail
        thumb_fname = "thumbnail (article).webp"
        self._binary_files[thumb_fname] = image_data
        self.root["thumbnail"] = f"file:/{thumb_fname}"

        return item_id

    def add_reference_item(
        self, x: int, y: int, w: int, h: int,
        ref_data: dict,
        screenshot_data: bytes | None = None,
    ) -> str:
        """Add a reference item, rendered according to its type.

        If screenshot_data is provided (for webpage types), it's used
        as the item thumbnail.
        """
        ref_type = ref_data["ref_type"]
        url = ref_data.get("url")

        if ref_type == "pdf" and url:
            return self._add_pdf_ref(x, y, w, h, url, ref_data)
        elif ref_type in ("doi", "pubmed", "arxiv") and url:
            return self._add_webpage_ref(x, y, w, h, url, ref_data, screenshot_data)
        elif ref_type == "book":
            return self._add_book_ref(x, y, w, h, ref_data, screenshot_data)
        elif ref_type == "webpage" and url:
            return self._add_webpage_ref(x, y, w, h, url, ref_data, screenshot_data)
        elif ref_type == "dead":
            return self._add_placeholder_ref(x, y, w, h, ref_data)
        else:
            return self._add_text_ref(x, y, w, h, ref_data)

    def _add_webpage_ref(self, x, y, w, h, url, ref_data,
                          screenshot_data: bytes | None = None):
        """Add a webpage embed reference with optional screenshot thumbnail."""
        item_id = make_id()
        item = {
            "id": item_id,
            "type": "webpage",
            "position": {"x": x, "y": y},
            "size": {"width": w, "height": h},
            "title": "",
            "dropShadow": True,
            "groupId": None,
            "notes": None,
            "source": url,
        }
        # Attach screenshot as thumbnail if provided
        if screenshot_data:
            dims = self._image_dimensions(screenshot_data)
            if dims:
                tw, th = dims
                thumb_fname = f"items/{item_id} (thumbnail).png"
                scale = min(800 / tw, 600 / th, 1.0)
                pw, ph = int(tw * scale), int(th * scale)
                item["thumbnail"] = {
                    "renditions": [{
                        "source": f"file:/{thumb_fname}",
                        "format": "png",
                        "size": {"width": pw, "height": ph},
                        "isPrimary": True,
                        "isAutoGenerated": False,
                    }]
                }
                self._binary_files[thumb_fname] = screenshot_data
        self.root["items"].append(item)
        return item_id

    def _add_pdf_ref(self, x, y, w, h, url, ref_data):
        """Add a PDF embed reference."""
        item_id = make_id()
        self.root["items"].append({
            "id": item_id,
            "type": "pdf",
            "position": {"x": x, "y": y},
            "size": {"width": w, "height": h},
            "title": "",
            "dropShadow": True,
            "groupId": None,
            "notes": None,
            "source": url,
            "defaultPage": 1,
        })
        return item_id

    def _add_book_ref(self, x, y, w, h, ref_data,
                        screenshot_data: bytes | None = None):
        """Add a book reference — try Google Books, fall back to text card."""
        isbn = ref_data.get("isbn")
        if isbn:
            clean_isbn = isbn.replace("-", "").replace(" ", "")
            google_books_url = (
                f"https://books.google.com/books?vid=ISBN{clean_isbn}"
            )
            item_id = make_id()
            item = {
                "id": item_id,
                "type": "webpage",
                "position": {"x": x, "y": y},
                "size": {"width": w, "height": h},
                "title": "",
                "dropShadow": True,
                "groupId": None,
                "notes": None,
                "source": google_books_url,
            }
            if screenshot_data:
                dims = self._image_dimensions(screenshot_data)
                if dims:
                    tw, th = dims
                    thumb_fname = f"items/{item_id} (thumbnail).png"
                    scale = min(800 / tw, 600 / th, 1.0)
                    pw, ph = int(tw * scale), int(th * scale)
                    item["thumbnail"] = {
                        "renditions": [{
                            "source": f"file:/{thumb_fname}",
                            "format": "png",
                            "size": {"width": pw, "height": ph},
                            "isPrimary": True,
                            "isAutoGenerated": False,
                        }]
                    }
                    self._binary_files[thumb_fname] = screenshot_data
            self.root["items"].append(item)
            return item_id

        # No ISBN — show as text card
        return self._add_text_ref(x, y, w, h, ref_data)

    def _add_text_ref(self, x, y, w, h, ref_data):
        """Add a bare-text citation as a text card."""
        item_id = make_id()
        text = html_mod.escape(ref_data["text"])
        # Make it readable: short label + first sentence
        display_text = html_mod.escape(ref_data["label"])
        self.root["items"].append({
            "id": item_id,
            "type": "text",
            "position": {"x": x, "y": y},
            "size": {"width": w, "height": h},
            "title": "",
            "dropShadow": False,
            "groupId": None,
            "notes": None,
            "text": f"<p style=\"font-size:11px;line-height:1.4\">{display_text}</p>",
            "backgroundColor": "#f0f0f000",
        })
        return item_id

    def _add_placeholder_ref(self, x, y, w, h, ref_data):
        """Add a dimmed placeholder for unresolvable/dead references."""
        item_id = make_id()
        url = ref_data.get("url") or "unknown URL"
        safe_url = html_mod.escape(url[:60])
        self.root["items"].append({
            "id": item_id,
            "type": "text",
            "position": {"x": x, "y": y},
            "size": {"width": w, "height": h},
            "title": "",
            "dropShadow": False,
            "groupId": None,
            "notes": None,
            "text": (
                f'<p style="font-size:11px;color:#b32424">⚠️ Dead link</p>'
                f'<p style="font-size:9px;color:#72777d">{safe_url}…</p>'
            ),
            "backgroundColor": "#f8f8f800",
        })
        return item_id

    def add_type_label(self, x: int, y: int, ref_type: str, index: int):
        """Add a numbered badge + type label above a reference.

        Shows a colored circle badge with the citation number,
        followed by the reference type label text.
        """
        item_id = make_id()
        color = TYPE_COLORS.get(ref_type, "#72777d")
        label = TYPE_LABELS.get(ref_type, ref_type)
        self.root["items"].append({
            "id": item_id,
            "type": "text",
            "position": {"x": x, "y": y},
            "size": {"width": REF_WIDTH, "height": LABEL_HEIGHT},
            "title": "",
            "dropShadow": False,
            "groupId": None,
            "notes": None,
            "text": (
                f'<div style="display:flex;align-items:center;gap:6px">'
                f'<div style="background:{color};color:white;border-radius:10px;'
                f'width:18px;height:18px;display:flex;align-items:center;'
                f'justify-content:center;font-size:10px;font-weight:700">'
                f'{index}</div>'
                f'<span style="font-size:10px;color:{color};font-weight:600">'
                f'{label}</span></div>'
            ),
            "backgroundColor": "#ffffff00",
        })
        return item_id

    def add_action_button(
        self, x: int, y: int, w: int, h: int,
        url: str, label: str = "Open in new tab",
    ):
        """Add an action button to open a URL externally."""
        item_id = make_id()
        self.root["items"].append({
            "id": item_id,
            "type": "actionButton",
            "position": {"x": x, "y": y},
            "size": {"width": w, "height": h},
            "title": "",
            "dropShadow": False,
            "groupId": None,
            "notes": None,
            "actionType": "externalLink",
            "action": url,
            "text": label,
            "backgroundColor": "#dce8f5",
        })
        return item_id

    def add_rel(self, from_id: str, to_id: str,
                 y_anchor: float = 0.5,
                 side: str = "right"):
        """Add an arrow from article edge to reference.

        Args:
            y_anchor: Vertical position on the article (0=top, 1=bottom) where
                      the arrow originates.
            side: "right" for right-edge arrows, "left" for left-edge arrows.
                  Controls which side of the article the arrow exits from
                  and which side of the ref it enters.
        """
        rel_id = make_id()
        if side == "left":
            from_anchor = {"x": 0.0, "y": y_anchor}
            to_anchor = {"x": 1.0, "y": 0.5}  # enters ref from right side
        else:
            from_anchor = {"x": 1.0, "y": y_anchor}
            to_anchor = {"x": 0.0, "y": 0.5}  # enters ref from left side

        self.root["rels"].append({
            "id": rel_id,
            "from": {
                "itemId": from_id,
                "anchor": from_anchor,
                "arrowhead": "none",
            },
            "to": {
                "itemId": to_id,
                "anchor": to_anchor,
                "arrowhead": "arrow",
            },
            "color": "#36c",
            "weight": "light",
        })
        return rel_id

    def set_presentation(self, article_id: str, ref_item_ids: list[str]):
        """Build presentation tour: article first, then each reference in order."""
        pres_step_ids = []
        all_targets = [article_id] + ref_item_ids
        for target_id in all_targets:
            step_id = make_id()
            pres_step_ids.append(step_id)
            self.root["presentation"].append({
                "id": step_id,
                "prevStepId": pres_step_ids[-2] if len(pres_step_ids) >= 2 else None,
                "type": "item",
                "itemId": target_id,
            })

    def set_start_view(self):
        """Calculate dynamic startView from bounding box of all items."""
        if not self.root["items"]:
            return
        xs = [i["position"]["x"] for i in self.root["items"]]
        ys = [i["position"]["y"] for i in self.root["items"]]
        ws = [i["position"]["x"] + i["size"]["width"] for i in self.root["items"]]
        hs = [i["position"]["y"] + i["size"]["height"] for i in self.root["items"]]
        pad = 80
        self.root["startView"] = {
            "position": {
                "x": min(xs) - pad,
                "y": min(ys) - pad,
            },
            "size": {
                "width": max(ws) - min(xs) + pad * 2,
                "height": max(hs) - min(ys) + pad * 2,
            },
        }

    def save_zip(self, output_path: str):
        """Write the tapestry to a .zip file."""
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("root.json", json.dumps(self.root, indent=2))
            for filename, data in self._binary_files.items():
                zf.writestr(filename, data)
        print(f"\n✅ Tapestry saved to: {output_path}")
        print(f"   Items: {len(self.root['items'])}")
        print(f"   Rels:  {len(self.root['rels'])}")
        print(f"   Presentation steps: {len(self.root['presentation'])}")

    @staticmethod
    def _image_dimensions(data: bytes) -> tuple[int, int] | None:
        """Read image dimensions from JPEG or PNG bytes."""
        if data[:8] == b'\x89PNG\r\n\x1a\n' and len(data) > 24:
            w = (data[16] << 24) + (data[17] << 16) + (data[18] << 8) + data[19]
            h = (data[20] << 24) + (data[21] << 16) + (data[22] << 8) + data[23]
            return (w, h)
        if data[:2] == b'\xff\xd8' and len(data) > 9:
            i = 2
            while i < len(data) - 9:
                if data[i] == 0xff and data[i + 1] == 0xc0:
                    h = (data[i + 5] << 8) + data[i + 6]
                    w = (data[i + 7] << 8) + data[i + 8]
                    return (w, h)
                i += 1
        return None


# ── URL Probing ──────────────────────────────────────────────────────────


def probe_url(url: str, timeout: int = 10) -> bool:
    """Check if a URL is reachable with a HEAD request.

    Returns True if reachable (2xx), False otherwise.
    """
    try:
        resp = SESSION.head(url, timeout=timeout, allow_redirects=True)
        return 200 <= resp.status_code < 400
    except Exception:
        return False


# ── Main Conversion ──────────────────────────────────────────────────────


def convert_wikipedia_to_citation_graph(
    title: str,
    lang: str = "en",
    layout: str = "u",
    max_refs: int = 50,
    article_width: int = ARTICLE_WIDTH,
    max_height: int | None = None,
    height_ratio: float = 1.0,
    ref_width: int = REF_WIDTH,
    probe: bool = False,
    probe_timeout: int = 10,
    use_screenshots: bool = False,
    output: str | None = None,
):
    """Convert a Wikipedia article into a citation graph tapestry.

    If use_screenshots is True, captures real browser screenshots via Playwright CLI
    for the article and each source URL (with delays to avoid swamping).
    """

    print(f"📄 Fetching Wikipedia article: {title} ({lang})")
    print("─" * 60)

    # ── 1. Page summary ──
    summary = fetch_page_summary(lang, title)
    page_title = summary.get("title", title)
    description = summary.get("description", "")
    lead_image_url = (
        summary.get("thumbnail", {}).get("source")
        if summary.get("thumbnail")
        else None
    )
    article_url = (
        f"https://{lang}.wikipedia.org/wiki/{quote(title, safe='')}?useformat=mobile"
    )
    print(f"   Title:       {page_title}")
    print(f"   Description: {description or '(none)'}")
    print(f"   Lead image:  {'yes' if lead_image_url else 'no'}")

    # ── 2. Fetch rendered HTML for reference extraction ──
    print(f"\n📚 Fetching rendered HTML for reference parsing...")
    data = wiki_request(ACTION_API.format(lang=lang), {
        "action": "parse",
        "page": page_title,
        "prop": "text",
        "format": "json",
    })
    rendered_html = data.get("parse", {}).get("text", {}).get("*", "")
    if not rendered_html:
        print("⚠️  Could not fetch page HTML.", file=sys.stderr)
        return

    # ── 3. Parse references ──
    all_refs = parse_references(rendered_html)
    total_refs = len(all_refs)

    # Optional: cross-reference via mwparserfromhell (wikitext) for accuracy
    try:
        import mwparserfromhell
        api_url = ACTION_API.format(lang=lang)
        wt_data = wiki_request(api_url, {
            "action": "parse",
            "page": page_title,
            "prop": "wikitext",
            "format": "json",
        })
        raw_wt = wt_data.get("parse", {}).get("wikitext", {}).get("*", "")
        if raw_wt:
            parsed = mwparserfromhell.parse(raw_wt)
            wt_refs = parsed.filter_tags(matches=lambda t: t.tag.lower() == "ref")
            wt_names = set()
            for tag in wt_refs:
                for attr in tag.attributes:
                    m = re.match(r'\s*name\s*=\s*["\']?([^"\'>\s]+)', str(attr))
                    if m:
                        wt_names.add(m.group(1).strip())
            html_names = {r["ref_name"] for r in all_refs}
            missing = wt_names - html_names
            if missing:
                print(f"   ℹ️  mwparserfromhell: {len(missing)} additional ref names "
                      f"(not used by this article's body text)")
            else:
                print(f"   ✅ mwparserfromhell confirms all {total_refs} references")
    except ImportError:
        pass

    print(f"   References found: {total_refs}")
    if total_refs == 0:
        print("   ℹ️  This article has no citations. Generating minimal output.")

    # Apply max_refs cap
    if max_refs > 0 and total_refs > max_refs:
        print(f"   Including up to: {max_refs}")
        refs = all_refs[:max_refs]
        overflow = total_refs - max_refs
    else:
        refs = all_refs
        overflow = 0

    # ── 4. Classify and optionally probe ──
    print(f"\n🔍 Classifying references...")
    type_counts: dict[str, int] = {}
    for ref_data in refs:
        ref_type = ref_data["ref_type"]
        type_counts[ref_type] = type_counts.get(ref_type, 0) + 1

        if probe and ref_data["url"]:
            alive = probe_url(ref_data["url"], probe_timeout)
            if not alive:
                ref_data["ref_type"] = "dead"
                type_counts[ref_type] = max(0, type_counts.get(ref_type, 0) - 1)
                type_counts["dead"] = type_counts.get("dead", 0) + 1

    for rtype, count in sorted(type_counts.items()):
        print(f"   {TYPE_LABELS.get(rtype, rtype)}: {count}")

    # ── 5. Capture full-page article screenshot + measure citation positions ──
    print(f"\n📸 Capturing full-page article screenshot and measuring citation positions...")
    import tempfile
    ss_path = os.path.join(tempfile.gettempdir(), f"article_ss_{uuid.uuid4().hex}.png")
    article_screenshot, citation_ys = capture_article_with_positions(
        article_url, ss_path, viewport_w=800, viewport_h=600,
    )
    if not article_screenshot:
        print(f"   ⚠️  Article screenshot failed — cannot proceed")
        return

    print(f"   Article screenshot: {len(article_screenshot)} bytes")
    dims = CitationGraphBuilder._image_dimensions(article_screenshot)
    if dims:
        article_width = min(dims[0], 800)
        article_height = dims[1]
    print(f"   Image dimensions: {article_width}×{article_height}")
    print(f"   Citations positioned: {len(citation_ys)}/{len(refs)}")
    time.sleep(0.5)

    # Apply height caps AFTER screenshot dimensions are known
    if height_ratio != 1.0:
        article_height = int(article_height * height_ratio)
    if max_height:
        article_height = min(article_height, max_height)

    # ── 6. Build layout (using Playwright-measured positions) ──
    print(f"\n🎨 Building Citation Graph ({layout} layout)...")

    ref_h_map = {r["ref_type"]: REF_HEIGHTS.get(r["ref_type"], REF_HEIGHTS["webpage"]) for r in refs}

    if layout == "ring":
        positions = layout_ring(
            MARGIN, MARGIN, article_width, article_height,
            refs, ref_width, ref_h_map,
        )
        y_anchors = [0.5] * len(positions)
        sides = ["right"] * len(positions)
    elif layout == "grid":
        positions = layout_grid(
            MARGIN, MARGIN, article_width, article_height,
            refs, ref_width, ref_h_map,
        )
        y_anchors = [0.5] * len(positions)
        sides = ["right"] * len(positions)
    else:
        positions, y_anchors, sides = layout_positioned_both_sides(
            MARGIN, MARGIN, article_width, article_height,
            refs, ref_width, ref_h_map,
            citation_ys=citation_ys,
        )

    # ── 8. Build Tapestry ──
    builder = CitationGraphBuilder(page_title, description)

    # Add the article as an image item (full-page screenshot)
    article_id = builder.add_article_image(
        MARGIN, MARGIN, article_width, article_height,
        article_screenshot,
        title=page_title,
    )
    print(f"   Article: {article_width}×{article_height} at ({MARGIN}, {MARGIN})")

    # Collect refs that need screenshots
    ref_screenshots: dict[int, bytes | None] = {}
    if use_screenshots:
        print(f"\n📸 Capturing source page screenshots...")
        import tempfile
        for idx, pos in enumerate(positions):
            ref_data = pos["ref"]
            url = ref_data.get("url")
            if not url or ref_data["ref_type"] not in ("webpage", "doi", "pubmed", "arxiv", "book"):
                continue
            if ref_data["ref_type"] == "book" and not ref_data.get("isbn"):
                continue

            print(f"   [{idx+1}/{len(positions)}] {ref_data['label'][:50]}...", end=" ", flush=True)
            ss_path = os.path.join(tempfile.gettempdir(), f"ref_{uuid.uuid4().hex}.png")
            try:
                ss_data = capture_page_screenshot(url, ss_path, 450, 320)
                if ss_data:
                    ref_screenshots[idx] = ss_data
                    print(f"{len(ss_data)} bytes")
                else:
                    print("⚠️")
            except Exception as e:
                print(f"error: {e}")
            time.sleep(0.8)

    # ── 9. Add reference items with labels ──
    ref_item_ids = []
    for idx, pos in enumerate(positions):
        ref_data = pos["ref"]
        rx, ry, rw, rh = pos["x"], pos["y"], pos["w"], pos["h"]

        # Type label above the reference
        builder.add_type_label(rx, ry - LABEL_HEIGHT - LABEL_GAP, ref_data["ref_type"], ref_data["index"])

        # The reference item itself, with optional screenshot
        ss = ref_screenshots.get(idx)
        item_id = builder.add_reference_item(rx, ry, rw, rh, ref_data, ss)
        ref_item_ids.append(item_id)

        # Arrow from article to reference (positioned Y anchor, correct side)
        y_a = y_anchors[idx] if idx < len(y_anchors) else 0.5
        side = sides[idx] if idx < len(sides) else "right"
        builder.add_rel(article_id, item_id, y_anchor=y_a, side=side)

        # Action button for "Open in new tab" (only if URL exists)
        if ref_data.get("url"):
            btn_y = ry + rh + 4
            btn_h = 24
            # Left-side refs: button at left edge, right-side refs: button at right edge
            if side == "left":
                builder.add_action_button(
                    rx, btn_y, 110, btn_h,
                    ref_data["url"],
                    label="Open ↗",
                )
            else:
                builder.add_action_button(
                    rx + rw - 110, btn_y, 110, btn_h,
                    ref_data["url"],
                    label="Open ↗",
                )

    # Add overflow note if refs were capped
    if overflow > 0:
        note_x = MARGIN
        note_y = MARGIN + article_height + MARGIN + 40
        builder.root["items"].append({
            "id": make_id(),
            "type": "text",
            "position": {"x": note_x, "y": note_y},
            "size": {"width": 400, "height": 50},
            "title": "",
            "dropShadow": False,
            "groupId": None,
            "notes": None,
            "text": (
                f'<p style="font-size:12px;color:#72777d">'
                f'📄 +{overflow} more references not shown '
                f'(use --max-refs to increase)</p>'
            ),
            "backgroundColor": "#ffffff00",
        })

    # Presentation tour
    builder.set_presentation(article_id, ref_item_ids)

    # Dynamic start view
    builder.set_start_view()

    # ── 10. Output ──
    if output is None:
        safe = re.sub(r"[^\w\- ]", "_", page_title)
        safe = re.sub(r"\s+", "_", safe)
        output = f"{safe}_citation_graph.zip"

    builder.save_zip(output)
    return output


# ── CLI ───────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Convert a Wikipedia article into a citation graph tapestry.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python3 wikipedia-citation-graph.py "Seven dirty words"\n'
            '  python3 wikipedia-citation-graph.py "Alan Greenspan" --max-refs 40\n'
            '  python3 wikipedia-citation-graph.py "Supreme Court of the United States"'
            " --layout ring --max-refs 80\n"
            '  python3 wikipedia-citation-graph.py "Ada Lovelace" --layout grid --probe\n'
        ),
    )
    parser.add_argument("article", nargs="?",
                        help="Wikipedia article title or full URL")
    parser.add_argument(
        "--lang", default="en",
        help="Wikipedia language code (default: en)",
    )
    parser.add_argument(
        "--layout", choices=["u", "ring", "grid"], default="u",
        help="Reference layout: u (U-shape, default), ring (full ring), grid (grid below)",
    )
    parser.add_argument(
        "--max-refs", type=int, default=50,
        help="Maximum references to include (0 = all, default: 50)",
    )
    parser.add_argument(
        "--article-width", type=int, default=ARTICLE_WIDTH,
        help="Article embed width in pixels (default: 800)",
    )
    parser.add_argument(
        "--max-height", type=int, default=None,
        help="Cap article embed height in pixels (default: full article height)",
    )
    parser.add_argument(
        "--height-ratio", type=float, default=1.0,
        help="Scale auto-calculated article height by factor (default: 1.0)",
    )
    parser.add_argument(
        "--ref-width", type=int, default=REF_WIDTH,
        help="Reference embed width in pixels (default: 450)",
    )
    parser.add_argument(
        "--probe", action="store_true",
        help="Probe URLs with HEAD request to detect dead links (slower)",
    )
    parser.add_argument(
        "--probe-timeout", type=int, default=10,
        help="Timeout in seconds for URL probing (default: 10)",
    )
    parser.add_argument(
        "--screenshots", action="store_true",
        help="Capture real browser screenshots as thumbnails (requires playwright-cli)",
    )
    parser.add_argument(
        "--no-cache", action="store_true",
        help="Disable screenshot cache — recapture all screenshots fresh",
    )
    parser.add_argument(
        "--clear-cache", action="store_true",
        help="Clear screenshot cache and exit",
    )
    parser.add_argument(
        "--output", "-o", help="Output .zip file path",
    )

    args = parser.parse_args()

    if args.clear_cache:
        _clear_cache()
        return

    if args.no_cache:
        global SCREENSHOT_CACHE_ENABLED
        SCREENSHOT_CACHE_ENABLED = False

    if not args.article:
        parser.print_help()
        print("\n❌ Error: article title is required")
        sys.exit(1)

    article = args.article
    lang = args.lang

    # Parse URL or title
    url_match = re.match(
        r"https?://([a-z]{2,3})\.wikipedia\.org/wiki/(.+)$",
        article,
    )
    if url_match:
        lang = url_match.group(1)
        title = unquote(url_match.group(2))
        title = title.split("#")[0]
    else:
        title = article

    convert_wikipedia_to_citation_graph(
        title=title,
        lang=lang,
        layout=args.layout,
        max_refs=args.max_refs,
        article_width=args.article_width,
        max_height=args.max_height,
        height_ratio=args.height_ratio,
        ref_width=args.ref_width,
        probe=args.probe,
        probe_timeout=args.probe_timeout,
        use_screenshots=args.screenshots,
        output=args.output,
    )


if __name__ == "__main__":
    main()
