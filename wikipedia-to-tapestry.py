#!/usr/bin/env python3
"""
Wikipedia Article → Tapestry Visual Map Converter

Produces a v7 .zip file that breaks down a Wikipedia article as a visual map:
  • Center: the article itself as an embedded webpage item
  • Below: linked articles from the lead section, each as a webpage item with arrows
  • Right: a gallery of images from the article as image items

Usage:  python3 wikipedia-to-tapestry.py "Chess" [options]
"""

import argparse
import html
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

USER_AGENT = "WikipediaToTapestryBot/2.0 (andrew.lih@gmail.com) WikiTapestryVisualMap"
REST_API = "https://{lang}.wikipedia.org/api/rest_v1"
ACTION_API = "https://{lang}.wikipedia.org/w/api.php"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})

# Layout constants (pixels)
MARGIN = 40
COL_GAP = 40
MAIN_WIDTH = 700
MAIN_HEIGHT = 500
LINK_WIDTH = 500
LINK_HEIGHT = 400
TILE_HEIGHT = 160  # fixed height for gallery images (width varies by aspect ratio)


# ── Helpers ────────────────────────────────────────────────────────────────

def make_id() -> str:
    return str(uuid.uuid4())


def wiki_request(url, params=None, max_retries=3):
    """Generic Wikimedia API request with retry and UA handling."""
    for attempt in range(max_retries):
        resp = SESSION.get(url, params=params, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 10))
            time.sleep(retry_after)
            continue
        if resp.status_code == 403:
            raise PermissionError(
                "403 Forbidden — check User-Agent header. "
                "See: https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy\n"
                + resp.text
            )
        resp.raise_for_status()
    raise RuntimeError(f"Failed after {max_retries} retries")


def fetch_page_summary(lang: str, title: str) -> dict:
    """Get page summary via REST API — includes title, description, extract, thumbnail."""
    url = REST_API.format(lang=lang) + f"/page/summary/{quote(title, safe='')}"
    return wiki_request(url)


def fetch_lead_links(lang: str, title: str) -> list[dict]:
    """Get wikilinks from the lead section (section 0) only."""
    url = ACTION_API.format(lang=lang)
    data = wiki_request(url, {
        "action": "parse",
        "page": title,
        "section": "0",
        "prop": "links",
        "format": "json",
    })
    links = data.get("parse", {}).get("links", [])
    # Filter to namespace 0 (main articles), exclude missing pages
    return [l for l in links if l.get("ns") == 0 and "*" in l]


def fetch_all_images(lang: str, title: str, limit=50) -> list[str]:
    """Get image filenames used on the page."""
    url = ACTION_API.format(lang=lang)
    data = wiki_request(url, {
        "action": "query",
        "prop": "images",
        "titles": title,
        "imlimit": limit,
        "format": "json",
    })
    images = []
    for pdata in data.get("query", {}).get("pages", {}).values():
        for img in pdata.get("images", []):
            filename = img["title"]
            # Only raster images for gallery
            if re.search(r"\.(jpg|jpeg|png|gif|webp)$", filename, re.I):
                images.append(filename)
    return images


def get_image_thumb_url(filename: str, width=400) -> str | None:
    """Get a thumbnail URL for a Commons filename."""
    data = wiki_request("https://en.wikipedia.org/w/api.php", {
        "action": "query",
        "titles": filename,
        "prop": "imageinfo",
        "iiprop": "url",
        "iiurlwidth": width,
        "format": "json",
    })
    for pdata in data.get("query", {}).get("pages", {}).values():
        info = pdata.get("imageinfo", [])
        if info:
            return info[0].get("thumburl") or info[0].get("url")
    return None


def get_image_info(filename: str, req_width: int = 800):
    """Get thumbnail URL + original dimensions from the API (no file download).
    Returns (thumb_url, orig_width, orig_height) or (None, None, None) on failure."""
    data = wiki_request("https://en.wikipedia.org/w/api.php", {
        "action": "query",
        "titles": filename,
        "prop": "imageinfo",
        "iiprop": "url|size",
        "iiurlwidth": req_width,
        "format": "json",
    })
    for pdata in data.get("query", {}).get("pages", {}).values():
        info = pdata.get("imageinfo", [])
        if info:
            thumb_url = info[0].get("thumburl") or info[0].get("url")
            ow = info[0].get("width", req_width)
            oh = info[0].get("height", req_width)
            return (thumb_url, ow, oh)
    return (None, None, None)


def download_image(url: str, filepath: str) -> bytes | None:
    """Download image bytes, return None on failure. Includes delay for rate limiting."""
    time.sleep(0.3)
    try:
        resp = SESSION.get(url, timeout=30)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        print(f"  ⚠️  Could not download {filepath}: {e}", file=sys.stderr)
        return None


def capture_page_screenshot(url: str, output_path: str, viewport_size: int = 500) -> bytes | None:
    """Capture a webpage screenshot using Playwright CLI with a square viewport."""
    import subprocess
    try:
        subprocess.run(["playwright-cli", "goto", url],
                       capture_output=True, timeout=30, check=False)
        subprocess.run(["playwright-cli", "resize", str(viewport_size), str(viewport_size)],
                       capture_output=True, timeout=10, check=False)
        result = subprocess.run(
            ["playwright-cli", "screenshot", "--filename", output_path],
            capture_output=True, timeout=15, check=False
        )
        if os.path.exists(output_path):
            with open(output_path, "rb") as f:
                data = f.read()
            os.remove(output_path)
            if len(data) > 1000:
                return data
        return None
    except Exception as e:
        print(f"  ⚠️  Screenshot failed for {url}: {e}", file=sys.stderr)
        return None


def clean_title(title: str) -> str:
    """Clean a page title for use as a display name."""
    return re.sub(r"[^\w \-]", "_", title)[:40].strip() or "page"


def image_dimensions(data: bytes) -> tuple[int, int] | None:
    """Read image dimensions from JPEG or PNG bytes without external libraries."""
    # PNG: starts with 8-byte signature, then IHDR chunk with width/height
    if data[:8] == b'\x89PNG\r\n\x1a\n' and len(data) > 24:
        w = (data[16] << 24) + (data[17] << 16) + (data[18] << 8) + data[19]
        h = (data[20] << 24) + (data[21] << 16) + (data[22] << 8) + data[23]
        return (w, h)
    # JPEG: find SOF0 marker (0xFF 0xC0), read height then width
    if data[:2] == b'\xff\xd8':
        i = 2
        while i < len(data) - 9:
            if data[i] == 0xff and data[i+1] == 0xc0:
                h = (data[i+5] << 8) + data[i+6]
                w = (data[i+7] << 8) + data[i+8]
                return (w, h)
            i += 1
    return None


def is_useful_image(filename: str) -> bool:
    """Filter out icons, logos, buttons, and small UI elements from Wikipedia."""
    name_lower = filename.lower()
    # Skip known icon/symbol patterns
    skip_patterns = [
        "icon", "logo", "button", "bullet", "crystal ", "crystal_",
        "gnome-", "tango-", "nuvola", "circle-arrow", "symbol-",
        "question-book", "edit-clear", "commons-logo", "wikimedia-",
        "wikinews", "wikiquote", "wikisource", "wikiversity",
        "wikivoyage", "wiktionary", "wikibooks", "wikidata",
        "amp-", "amp_", "portal-", "redirect-arrow", "padlock",
        "audio-input", "video-input", "acap-", "imbox ", "imbox_",
        "semi-protection", "semi-protect", "lock-", "lock_",
        "flag_of", "flag_"
    ]
    for pattern in skip_patterns:
        if pattern in name_lower:
            return False
    return True


# ── Tapestry Builder ──────────────────────────────────────────────────────

class TapestryBuilder:
    def __init__(self, title: str, description: str = "", thumbnail_url: str = ""):
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

        # Download and set the root thumbnail if provided
        if thumbnail_url:
            img_data = download_image(thumbnail_url, "thumbnail")
            if img_data:
                self._binary_files["thumbnail (thumbnail).webp"] = img_data
                self.root["thumbnail"] = "file:/thumbnail (thumbnail).webp"

    def add_webpage_item(self, x: int, y: int, w: int, h: int,
                         source_url: str, title: str = "",
                         thumb_url: str = "", use_screenshot: bool = False) -> str:
        """Add a webpage item. Thumbnail can be lead image or browser screenshot."""
        item_id = make_id()
        item = {
            "id": item_id,
            "type": "webpage",
            "position": {"x": x, "y": y},
            "size": {"width": w, "height": h},
            "title": title or "",
            "dropShadow": True,
            "groupId": None,
            "notes": None,
            "source": source_url,
        }
        # Thumbnail: browser screenshot or lead image
        thumb_data = None
        if use_screenshot:
            import tempfile
            tmp = os.path.join(tempfile.gettempdir(), f"ss_{item_id}.png")
            thumb_data = capture_page_screenshot(source_url, tmp)
            ext = ".png"
        elif thumb_url:
            thumb_data = download_image(thumb_url, f"thumb_{item_id}")
            ext = os.path.splitext(thumb_url.split("?")[0])[1] or ".jpg"

        if thumb_data:
            dims = image_dimensions(thumb_data)
            if dims:
                tw, th = dims
                thumb_fname = f"items/{item_id} (thumbnail){ext}"
                scale = min(800 / tw, 600 / th, 1.0)
                pw, ph = int(tw * scale), int(th * scale)
                item["thumbnail"] = {
                    "renditions": [{
                        "source": f"file:/{thumb_fname}",
                        "format": ext.lstrip("."),
                        "size": {"width": pw, "height": ph},
                        "isPrimary": True,
                        "isAutoGenerated": False,
                    }]
                }
                self._binary_files[thumb_fname] = thumb_data
        self.root["items"].append(item)
        return item_id

    def add_image_item(self, x: int, y: int, source_url: str,
                       title: str = "", fixed_height: int = TILE_HEIGHT,
                       orig_w: int = 0, orig_h: int = 0) -> str:
        """Add an image item. Uses API-provided dimensions, no download needed."""
        item_id = make_id()
        disp_w = disp_h = fixed_height
        if orig_w > 0 and orig_h > 0:
            # Calculate what the thumbnail dimensions will be at the requested width
            req_w = max(fixed_height * 4, 800)
            thumb_w = min(req_w, orig_w)
            thumb_h = int(orig_h * (thumb_w / orig_w))
            # Scale to target display height
            scale = fixed_height / thumb_h
            disp_w = max(int(thumb_w * scale), 60)
            disp_h = fixed_height
        self.root["items"].append({
            "id": item_id,
            "type": "image",
            "position": {"x": x, "y": y},
            "size": {"width": disp_w, "height": disp_h},
            "title": title or "",
            "dropShadow": True,
            "groupId": None,
            "notes": None,
            "source": source_url,
        })
        return item_id

    def add_rel(self, from_id: str, to_id: str,
                color: str = "#72777d", weight: str = "light") -> str:
        """Add an arrow between two items."""
        rel_id = make_id()
        self.root["rels"].append({
            "id": rel_id,
            "from": {
                "itemId": from_id,
                "anchor": {"x": 0.5, "y": 1.0},
                "arrowhead": "none",
            },
            "to": {
                "itemId": to_id,
                "anchor": {"x": 0.5, "y": 0.0},
                "arrowhead": "arrow",
            },
            "color": color,
            "weight": weight,
        })
        return rel_id

    def save_zip(self, output_path: str):
        """Write the tapestry to a .zip file."""
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("root.json", json.dumps(self.root, indent=2))
            for filename, data in self._binary_files.items():
                zf.writestr(filename, data)
        print(f"\n✅ Tapestry saved to: {output_path}")
        print(f"   Items: {len(self.root['items'])}")
        print(f"   Rels:  {len(self.root['rels'])}")
        print(f"   Images embedded: {len(self._binary_files)}")


# ── Main conversion logic ────────────────────────────────────────────────

def convert_wikipedia_to_tapestry(
    title: str,
    lang: str = "en",
    max_links: int = 15,
    max_gallery: int = 20,
    gallery_height: int = 160,
    output: str | None = None,
    use_screenshots: bool = False,
    layout: str = "grid",
):
    """Convert a Wikipedia article into a visual-map tapestry."""

    print(f"📄 Fetching Wikipedia article: {title} ({lang})")
    print("─" * 50)

    # ── 1. Page summary ──
    summary = fetch_page_summary(lang, title)
    page_title = summary.get("title", title)
    description = summary.get("description", "")
    lead_image_url = summary.get("thumbnail", {}).get("source") if summary.get("thumbnail") else None
    article_url = f"https://{lang}.wikipedia.org/wiki/{quote(title, safe='')}?useformat=mobile"
    print(f"   Title:       {page_title}")
    print(f"   Description: {description or '(none)'}")
    print(f"   Lead image:  {'yes' if lead_image_url else 'no'}")

    # ── 2. Lead section links ──
    all_lead_links = fetch_lead_links(lang, page_title)
    link_titles = [l["*"] for l in all_lead_links if "*" in l][:max_links]
    print(f"   Lead links:  {len(link_titles)} (showing up to {max_links})")

    # ── 3. Fetch linked article summaries ──
    linked_info = []
    if link_titles:
        print(f"   Fetching linked article info...")
        for lt in link_titles:
            try:
                ls = fetch_page_summary(lang, lt)
                # Skip disambiguation pages
                if ls.get("type") == "disambiguation":
                    continue
                linked_info.append({
                    "title": ls.get("title", lt),
                    "url": f"https://{lang}.wikipedia.org/wiki/{quote(lt, safe='')}?useformat=mobile",
                    "description": ls.get("description", ""),
                    "thumbnail": ls.get("thumbnail", {}).get("source") if ls.get("thumbnail") else None,
                })
            except Exception as e:
                print(f"     ⚠️  Skipping '{lt}': {e}", file=sys.stderr)
                continue

    # ── 4. Article images ──
    all_images = fetch_all_images(lang, page_title, limit=50)
    # Don't include the lead image in the gallery (already used as root thumbnail)
    if lead_image_url:
        # Extract the filename from the lead image URL to filter it out
        lead_fname_match = re.search(r"/([^/]+?)(?:/thumb|$)", lead_image_url)
        if lead_fname_match:
            lead_fname = lead_fname_match.group(1)
            all_images = [i for i in all_images if lead_fname not in i]
    # Filter out icons, logos, UI elements
    all_images = [i for i in all_images if is_useful_image(i)]
    image_filenames = all_images[:max_gallery]
    print(f"   Images:      {len(image_filenames)} (showing up to {max_gallery})")

    # Get thumbnail URLs + dimensions for each image (single API call per image, no download)
    image_urls = []  # (display_name, thumb_url, orig_width, orig_height)
    for fname in image_filenames:
        req_w = max(gallery_height * 4, 800)
        url, ow, oh = get_image_info(fname, req_width=req_w)
        if url and ow and oh:
            display = re.sub(r"^File:", "", fname)
            image_urls.append((display, url, ow, oh))

    if lead_image_url:
        # Skip — lead image is already used as the root thumbnail
        pass

    image_urls = image_urls[:max_gallery]

    if lead_image_url:
        pass  # lead image is already the root thumbnail, skip gallery

    image_urls = image_urls[:max_gallery]

    # ── Build the Tapestry ──
    print(f"\n🎨 Building Tapestry layout...")
    builder = TapestryBuilder(page_title, description, lead_image_url)

    x_main = MARGIN
    y_cursor = MARGIN

    # ── Image gallery (top, compact grid) ──
    # Arrange images in rows at TILE_HEIGHT height, wrapping at max_row_width
    img_ids = []
    if image_urls:
        max_row_width = max(MAIN_WIDTH + MARGIN, 1200)
        row_x = MARGIN
        row_y = y_cursor
        for img_name, img_url, ow, oh in image_urls:
            display_name = img_name[:40] if img_name != "Thumbnail" else ""
            iid = builder.add_image_item(
                row_x, row_y, img_url, title=display_name,
                fixed_height=TILE_HEIGHT, orig_w=ow, orig_h=oh
            )
            img_ids.append(iid)
            img_w = builder.root["items"][-1]["size"]["width"]
            if row_x > MARGIN and row_x + img_w > MARGIN + max_row_width:
                row_y += TILE_HEIGHT + 6
                row_x = MARGIN
            builder.root["items"][-1]["position"]["x"] = row_x
            builder.root["items"][-1]["position"]["y"] = row_y
            row_x += img_w + 6

        y_cursor = row_y + TILE_HEIGHT + MARGIN * 2

    # ── Main article (webpage embed) ──
    title_item_id = builder.add_webpage_item(
        x_main, y_cursor, MAIN_WIDTH, MAIN_HEIGHT,
        article_url, title=page_title,
        thumb_url=lead_image_url or "",
        use_screenshot=use_screenshots
    )
    y_cursor += MAIN_HEIGHT + MARGIN

    # ── Linked articles (below the main article) ──
    link_ids = []
    if linked_info:
        cx = x_main + MAIN_WIDTH // 2

        if layout == "semicircle":
            n = len(linked_info)
            radius = max(LINK_WIDTH * 1.5, min(n * (LINK_WIDTH + COL_GAP) / math.pi, LINK_WIDTH * 2.5))
            for i, info in enumerate(linked_info):
                angle = i * math.pi / (n - 1) if n > 1 else math.pi / 2
                lx = cx + radius * math.cos(angle) - LINK_WIDTH // 2
                ly = y_cursor + radius * math.sin(angle)
                lid = builder.add_webpage_item(
                    lx, ly, LINK_WIDTH, LINK_HEIGHT,
                    info["url"], title=info["title"],
                    thumb_url=info.get("thumbnail") or "",
                    use_screenshot=use_screenshots
                )
                link_ids.append(lid)
                builder.add_rel(title_item_id, lid, color="#36c", weight="light")
        else:
            link_cols = 2
            total_row_w = link_cols * LINK_WIDTH + (link_cols - 1) * COL_GAP
            x_start = max(MARGIN, cx - total_row_w // 2)
            for i, info in enumerate(linked_info):
                col = i % link_cols
                row = i // link_cols
                lx = x_start + col * (LINK_WIDTH + COL_GAP)
                ly = y_cursor + row * (LINK_HEIGHT + MARGIN)
                lid = builder.add_webpage_item(
                    lx, ly, LINK_WIDTH, LINK_HEIGHT,
                    info["url"], title=info["title"],
                    thumb_url=info.get("thumbnail") or "",
                    use_screenshot=use_screenshots
                )
                link_ids.append(lid)
                builder.add_rel(title_item_id, lid, color="#36c", weight="light")

    # ── Presentation order (guided tour) ──
    # Main article → Link 1 → Link 2 → ... → First gallery image
    pres_step_ids = []
    all_tour_items = [title_item_id] + img_ids + link_ids
    for item_id in all_tour_items:
        step_id = make_id()
        pres_step_ids.append(step_id)
        builder.root["presentation"].append({
            "id": step_id,
            "prevStepId": pres_step_ids[-2] if len(pres_step_ids) >= 2 else None,
            "type": "item",
            "itemId": item_id,
        })

    # ── Dynamic start view (zoom out to fit all items) ──
    if builder.root["items"]:
        xs = [i["position"]["x"] for i in builder.root["items"]]
        ys = [i["position"]["y"] for i in builder.root["items"]]
        ws = [i["position"]["x"] + i["size"]["width"] for i in builder.root["items"]]
        hs = [i["position"]["y"] + i["size"]["height"] for i in builder.root["items"]]
        min_x, max_x = min(xs), max(ws)
        min_y, max_y = min(ys), max(hs)
        pad = 60
        builder.root["startView"] = {
            "position": {"x": min_x - pad, "y": min_y - pad},
            "size": {"width": max_x - min_x + pad * 2, "height": max_y - min_y + pad * 2},
        }

    # ── Output path ──
    if output is None:
        safe = re.sub(r"[^\w\- ]", "_", page_title)
        safe = re.sub(r"\s+", "_", safe)
        output = f"{safe}.zip"

    builder.save_zip(output)
    return output


# ── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Convert a Wikipedia article into a Tapestry visual map.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python3 wikipedia-to-tapestry.py "Chess"\n'
            '  python3 wikipedia-to-tapestry.py "Ada Lovelace" --max-links 10 --gallery-height 120\n'
            '  python3 wikipedia-to-tapestry.py "https://en.wikipedia.org/wiki/Python_(programming_language)"\n'
        )
    )
    parser.add_argument("article", help="Wikipedia article title or full URL")
    parser.add_argument("--lang", default="en", help="Wikipedia language code (default: en)")
    parser.add_argument("--max-links", type=int, default=10,
                        help="Maximum linked articles from lead section (default: 12)")
    parser.add_argument("--max-gallery", type=int, default=50,
                        help="Maximum gallery images (default: 20)")
    parser.add_argument("--gallery-height", type=int, default=160,
                        help="Gallery image height in pixels (default: 160)")
    parser.add_argument("--output", "-o", help="Output .zip file path")
    parser.add_argument("--screenshots", action="store_true",
                        help="Use Playwright browser screenshots as webpage thumbnails (slower)")
    parser.add_argument("--layout", choices=["grid", "semicircle"], default="grid",
                        help="Layout of linked articles: grid (default) or semicircle")

    args = parser.parse_args()

    article = args.article
    lang = args.lang

    # Parse URL or title
    url_match = re.match(
        r"https?://([a-z]{2,3})\.wikipedia\.org/wiki/(.+)$",
        article
    )
    if url_match:
        lang = url_match.group(1)
        title = unquote(url_match.group(2))
        title = title.split("#")[0]
        title = unquote(title)
    else:
        title = article

    convert_wikipedia_to_tapestry(
        title=title,
        lang=lang,
        max_links=args.max_links,
        max_gallery=args.max_gallery,
        gallery_height=args.gallery_height,
        output=args.output,
        use_screenshots=args.screenshots,
        layout=args.layout,
    )


if __name__ == "__main__":
    main()
