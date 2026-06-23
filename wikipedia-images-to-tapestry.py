#!/usr/bin/env python3
"""
Wikipedia Article Images → Tapestry Visual Slideshow

Converts all useful images from a Wikipedia article into a sequential
slideshow tapestry for import into Tapestries.media.

Each image is displayed large (default 700px wide), with its Commons
description and SDC caption underneath. Images are linked with arrows
(1→2→3→…) and the presentation tour walks through them in order —
like a visual narrative overview of the article.

Usage:
  python3 wikipedia-images-to-tapestry.py "Article Title" [options]
  python3 wikipedia-images-to-tapestry.py "https://en.wikipedia.org/wiki/Article_Title"

Examples:
  python3 wikipedia-images-to-tapestry.py "Chess"
  python3 wikipedia-images-to-tapestry.py "Great Barrier Reef" --image-width 900 --max-images 30
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

USER_AGENT = "WikipediaImagesToTapestryBot/1.0 (andrew.lih@gmail.com) WikiImageSlideshow"
REST_API = "https://{lang}.wikipedia.org/api/rest_v1"
ACTION_API = "https://{lang}.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})

# Layout defaults (pixels)
MARGIN = 40
IMAGE_DISPLAY_WIDTH = 600   # how wide each image is displayed on the canvas
TEXT_MIN_HEIGHT = 100       # minimum height for caption text
GAP_X = 20                  # horizontal gap between images in a row
GAP_TEXT = 8                # gap between image bottom and caption top
GAP_ROW = 30                # gap between caption bottom of one row and next row's images
BTN_HEIGHT = 36             # height of the "View on Commons" action button
BTN_GAP = 6                 # gap between caption text bottom and action button top
MAX_ROW_WIDTH = 1500        # max width of a row before wrapping (fits 2×600 + gap or 2×700)

# ── Image metadata cache (disk-backed, keyed by article) ──────────────────

CACHE_DIR = os.path.expanduser("~/.cache/tapestry-converter")

def _cache_key(page_title: str, lang: str) -> str:
    """Generate a safe cache filename for an article."""
    safe = re.sub(r"[^\w\- ]", "_", page_title).strip()[:80]
    return os.path.join(CACHE_DIR, f"{safe}_{lang}.json")

def load_image_cache(page_title: str, lang: str) -> dict:
    """Load previously-cached image metadata for an article."""
    path = _cache_key(page_title, lang)
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}

def save_image_cache(page_title: str, lang: str, cache: dict):
    """Persist image metadata cache to disk."""
    path = _cache_key(page_title, lang)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(cache, f, indent=2)

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
                "See: https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy\n"
                + resp.text
            )
        resp.raise_for_status()
    raise RuntimeError(f"Failed after {max_retries} retries")

def retrying_sleep(seconds=0.3):
    """Pause to respect Wikimedia rate limits."""
    time.sleep(seconds)

def fetch_page_summary(lang: str, title: str) -> dict:
    """Get page summary via REST API — includes title, description, extract, thumbnail."""
    url = REST_API.format(lang=lang) + f"/page/summary/{quote(title, safe='')}"
    return wiki_request(url)

def fetch_all_images(lang: str, title: str) -> list[str]:
    """Get all image filenames used on the page using parse+images for best coverage."""
    url = ACTION_API.format(lang=lang)
    data = wiki_request(url, {
        "action": "parse",
        "page": title,
        "prop": "images",
        "format": "json",
    })
    images = data.get("parse", {}).get("images", [])
    # Filter to raster image formats (skip SVGs, icons, etc.)
    return [f for f in images if re.search(r"\.(jpg|jpeg|png|gif|webp)$", f, re.I)]

def get_image_info_and_metadata(filename: str, req_width: int = 800):
    """Get thumbnail URL, original dimensions, AND Commons extmetadata for a file.
    
    Queries Commons API directly (not en.wikipedia) to get both image info
    and description metadata in a single call.
    
    Returns dict with keys: thumb_url, orig_w, orig_h, description, artist, credit, date
    or None on failure.
    """
    # Normalize: ensure File: prefix
    fname = filename if filename.startswith("File:") else f"File:{filename}"
    retrying_sleep(0.3)
    try:
        data = wiki_request(COMMONS_API, {
            "action": "query",
            "titles": fname,
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "iiurlwidth": req_width,
            "format": "json",
        })
        for pdata in data.get("query", {}).get("pages", {}).values():
            info = pdata.get("imageinfo", [])
            if not info:
                return None
            i = info[0]
            result = {
                "thumb_url": i.get("thumburl") or i.get("url"),
                "orig_w": i.get("width", req_width),
                "orig_h": i.get("height", req_width),
                "description": "",
                "artist": "",
                "credit": "",
                "date": "",
                "caption": "",
            }
            meta = i.get("extmetadata", {})
            # ImageDescription — the main description from the file's Information template
            if "ImageDescription" in meta:
                raw = meta["ImageDescription"].get("value", "")
                cleaned = re.sub(r'<[^>]+>', '', raw).strip()
                # Take only the first paragraph (up to first double newline)
                first_para = cleaned.split("\n\n")[0].strip()
                # Trim overly long descriptions
                if len(first_para) > 800:
                    first_para = first_para[:797] + "..."
                result["description"] = first_para
            # Artist (photographer, creator)
            if "Artist" in meta:
                raw = meta["Artist"].get("value", "")
                result["artist"] = re.sub(r'<[^>]+>', '', raw).strip()
            # Credit line
            if "Credit" in meta:
                raw = meta["Credit"].get("value", "")
                result["credit"] = re.sub(r'<[^>]+>', '', raw).strip()
            # Date
            if "DateTimeOriginal" in meta:
                result["date"] = meta["DateTimeOriginal"].get("value", "")
            # Object name (often a short title/caption)
            if "ObjectName" in meta:
                raw = meta["ObjectName"].get("value", "")
                cleaned = re.sub(r'<[^>]+>', '', raw).strip()
                if cleaned:
                    result["caption"] = cleaned
            return result
    except Exception as e:
        print(f"  ⚠️  Could not fetch metadata for {filename}: {e}", file=sys.stderr)
    return None

def fetch_comments_sdc_caption(filename: str, lang: str = "en") -> str:
    """Fetch SDC (Structured Data on Commons) caption for a file.
    
    Returns the caption string for the requested language, or empty string.
    These are the short, multilingual labels curated on the Commons file page.
    """
    fname = filename if filename.startswith("File:") else f"File:{filename}"
    retrying_sleep(0.3)
    try:
        data = wiki_request(COMMONS_API, {
            "action": "wbgetentities",
            "sites": "commonswiki",
            "titles": fname,
            "props": "labels",
            "languages": lang,
            "format": "json",
        })
        for entity_id, entity in data.get("entities", {}).items():
            if "labels" in entity and lang in entity["labels"]:
                return entity["labels"][lang]["value"]
    except Exception as e:
        print(f"  ⚠️  Could not fetch SDC caption for {filename}: {e}", file=sys.stderr)
    return ""

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
        "flag_of", "flag_",
        "cscr-", "wikitech", "wikimedia-logo", "wikibooks-logo",
        "wikinews-logo", "wikiquote-logo", "wikisource-logo",
        "wikiversity-logo", "wikivoyage-logo", "wiktionary-logo",
        "wikidata-logo", "wikispecies-logo", "mediawiki-logo",
        "metawiki-logo", "commons-logo", "wikimedia-button",
        "footer-banner", "wikipedia-logo",
    ]
    for pattern in skip_patterns:
        if pattern in name_lower:
            return False
    return True

def truncate_name(fname: str, max_len: int = 50) -> str:
    """Truncate a display name for use in filenames."""
    name = re.sub(r"^File:", "", fname)
    clean = re.sub(r"[^\w\- ]", "_", name)[:max_len].strip()
    return clean or "image"


# ── Tapestry Builder ──────────────────────────────────────────────────────

class TapestrySlideshowBuilder:
    """Builds a v7 Tapestry zip for the image slideshow."""

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

    def add_image_item(self, x: int, y: int, w: int, h: int,
                       source_url: str, title: str = ""):
        """Add an image item at given position and size, returning the item dict."""
        item = {
            "id": make_id(),
            "type": "image",
            "position": {"x": x, "y": y},
            "size": {"width": w, "height": h},
            "title": title or "",
            "dropShadow": True,
            "groupId": None,
            "notes": None,
            "source": source_url,
        }
        self.root["items"].append(item)
        return item

    def add_text_item(self, x: int, y: int, w: int, h: int,
                      html_text: str):
        """Add a text item with HTML content, returning the item dict."""
        item = {
            "id": make_id(),
            "type": "text",
            "position": {"x": x, "y": y},
            "size": {"width": w, "height": h},
            "title": "",
            "dropShadow": False,
            "groupId": None,
            "notes": None,
            "text": html_text,
            "backgroundColor": "#ffffff00",
        }
        self.root["items"].append(item)
        return item

    def add_action_button(self, x: int, y: int, w: int, h: int,
                           url: str, label: str = "View on Commons"):
        """Add a clickable action button that opens an external URL."""
        item = {
            "id": make_id(),
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
            "backgroundColor": "#3366cc",
        }
        self.root["items"].append(item)
        return item

    def add_group(self):
        """Create an empty group and return its ID."""
        gid = make_id()
        self.root["groups"].append({
            "id": gid,
            "color": None,
            "hasBorder": False,
            "hasBackground": False,
        })
        return gid

    def add_rel(self, from_id: str, to_id: str,
                color: str = "#72777d", weight: str = "light") -> str:
        """Add an arrow between two items. Returns the rel ID."""
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
        print(f"\n✅ Tapestry slideshow saved to: {output_path}")
        print(f"   Items: {len(self.root['items'])}")
        print(f"   Rels:  {len(self.root['rels'])}")
        print(f"   Presentation steps: {len(self.root['presentation'])}")


# ── Main conversion logic ────────────────────────────────────────────────

def get_display_dimensions(orig_w: int, orig_h: int, max_width: int) -> tuple[int, int]:
    """Calculate display dimensions fitting within max_width, preserving aspect ratio."""
    if orig_w <= 0 or orig_h <= 0:
        return (max_width, max_width)
    if orig_w <= max_width:
        # Smaller than max width — display at original size
        return (orig_w, orig_h)
    scale = max_width / orig_w
    return (max_width, max(60, int(orig_h * scale)))

def estimate_text_height(text_html: str, max_width: int) -> int:
    """
    Roughly estimate the height needed to display HTML text.
    Assumes ~60 chars per line at the given width, ~20px per line.
    Returns minimum TEXT_MIN_HEIGHT.
    """
    # Strip tags for character count
    plain = re.sub(r'<[^>]+>', '', text_html)
    plain = html.unescape(plain).strip()
    if not plain:
        return TEXT_MIN_HEIGHT
    
    # Rough: at 700px width, ~80 chars per line with ~18px line height
    chars_per_line = max(20, max_width // 9)
    num_lines = max(1, len(plain) // chars_per_line + (1 if len(plain) % chars_per_line > 0 else 0))
    # Account for <br> tags and headings
    br_count = text_html.count("<br>") + text_html.count("<br/>")
    num_lines += br_count
    h_count = text_html.count("<h")
    if h_count:
        num_lines += h_count * 2  # headings are taller
    
    height = max(TEXT_MIN_HEIGHT, num_lines * 18 + 20)  # 18px line height + padding
    return min(height, 400)  # cap at 400px max

def format_caption_html(image_info: dict) -> str:
    """
    Build an HTML string for the caption/description text item.
    
    Combines:
    - SDC caption (short label, shown as bold heading if present)
    - Commons description (from extmetadata)
    - Artist / credit metadata
    """
    parts = []
    
    # SDC caption or ObjectName as heading
    heading = image_info.get("caption", "").strip()
    if heading:
        # Sanitize: ensure it's safe for HTML and wrap in bold
        safe = html.escape(heading)
        parts.append(f"<strong>{safe}</strong>")
    
    # Commons description as body text
    desc = image_info.get("description", "").strip()
    if desc:
        safe = html.escape(desc)
        if parts:
            parts.append(f"<br><br>{safe}")
        else:
            parts.append(safe)
    
    # Artist credit
    artist = image_info.get("artist", "").strip()
    if artist and artist not in (desc or ""):
        safe_artist = html.escape(artist)
        date = image_info.get("date", "").strip()
        date_str = f", {html.escape(date)}" if date else ""
        parts.append(f'<br><br><span style="font-size:0.85em;color:#666;">— {safe_artist}{date_str}</span>')
    
    if not parts:
        return ""
    
    return "".join(parts)

def convert_wikipedia_images_to_tapestry(
    title: str,
    lang: str = "en",
    max_images: int = 50,
    image_width: int = 600,
    output: str | None = None,
):
    """Convert all useful images from a Wikipedia article into a slideshow tapestry."""

    print(f"📸 Fetching Wikipedia article: {title} ({lang})")
    print("─" * 60)

    # ── 1. Page summary ──
    summary = fetch_page_summary(lang, title)
    page_title = summary.get("title", title)
    description = summary.get("description", "")
    lead_image_url = summary.get("thumbnail", {}).get("source") if summary.get("thumbnail") else None
    print(f"   Title:       {page_title}")
    print(f"   Description: {description or '(none)'}")
    print(f"   Lead image:  {'yes' if lead_image_url else 'no'}")

    # ── 2. Fetch all images ──
    all_images = fetch_all_images(lang, page_title)
    print(f"   Raw images:  {len(all_images)} found on page")

    # Filter out icons, logos, UI elements
    useful = [i for i in all_images if is_useful_image(i)]
    print(f"   After filter: {len(useful)} useful images (skipped {len(all_images) - len(useful)} icons/UI)")

    # Limit to max
    selected = useful[:max_images]
    if len(useful) > max_images:
        print(f"   Limiting to: {max_images} images")

    if not selected:
        print("⚠️  No useful images found. Nothing to generate.", file=sys.stderr)
        return

    # ── 3. Fetch image info, dimensions, and Commons metadata (with disk cache) ──
    print(f"\n🔍 Fetching image info and Commons metadata ({len(selected)} images)...")
    cache = load_image_cache(page_title, lang)
    image_data = []
    for idx, fname in enumerate(selected):
        name_only = re.sub(r"^File:", "", fname)
        cache_key = f"File:{name_only}"
        print(f"   [{idx+1}/{len(selected)}] {name_only[:60]}...", end="")
        sys.stdout.flush()

        # Check cache first
        cached = cache.get(cache_key)
        if cached:
            image_data.append(cached)
            print(" 💾")
            continue

        # Get thumbnail URL, dimensions, and Commons description (single API call)
        info = get_image_info_and_metadata(fname, req_width=image_width)
        if not info or not info["thumb_url"]:
            print(" ⚠️  skipped (no URL)")
            continue

        # Also fetch SDC caption (separate call for structured label)
        sdc_caption = fetch_comments_sdc_caption(fname, lang=lang)
        if sdc_caption:
            info["caption"] = sdc_caption

        commons_url = f"https://commons.wikimedia.org/wiki/File:{quote(name_only)}"
        entry = {
            "display_name": name_only,
            "thumb_url": info["thumb_url"],
            "orig_w": info["orig_w"],
            "orig_h": info["orig_h"],
            "description": info["description"],
            "artist": info["artist"],
            "credit": info["credit"],
            "date": info["date"],
            "caption": info["caption"],
            "commons_url": commons_url,
        }
        image_data.append(entry)
        cache[cache_key] = entry
        print(" ✓")

    save_image_cache(page_title, lang, cache)

    if not image_data:
        print("⚠️  No images could be processed. Nothing to generate.", file=sys.stderr)
        return

    # ── 4. Build the Tapestry layout (center-aligned grid) ──
    print(f"\n🎨 Building Tapestry slideshow layout ({len(image_data)} slides)...")
    builder = TapestrySlideshowBuilder(page_title, description)

    # Create all image+text+button item triples (positions set to 0,0 — arranged below)
    # Each triple shares a group so the presentation zooms to show all three together
    slides = []  # list of dicts: {img_item, txt_item, btn_item, w, h, text_h, group_id}
    for img in image_data:
        disp_w, disp_h = get_display_dimensions(img["orig_w"], img["orig_h"], image_width)
        caption_html = format_caption_html(img)
        text_h = estimate_text_height(caption_html, disp_w) if caption_html else TEXT_MIN_HEIGHT

        group_id = builder.add_group()
        btn_label = "🌐  View on Wikimedia Commons"
        img_item = builder.add_image_item(
            0, 0, disp_w, disp_h,
            source_url=img["thumb_url"],
            title=truncate_name(img["display_name"], 40),
        )
        img_item["groupId"] = group_id
        txt_item = builder.add_text_item(
            0, 0, disp_w, text_h,
            caption_html if caption_html else "",
        )
        txt_item["groupId"] = group_id
        # Build Commons URL (fallback for cached entries that predate this field)
        commons_url = img.get("commons_url") or f"https://commons.wikimedia.org/wiki/File:{quote(img['display_name'])}"
        btn_item = builder.add_action_button(
            0, 0, disp_w, BTN_HEIGHT,
            url=commons_url,
            label=btn_label,
        )
        btn_item["groupId"] = group_id
        slides.append({
            "img": img_item,
            "txt": txt_item,
            "btn": btn_item,
            "w": disp_w,
            "h": disp_h,
            "text_h": text_h,
            "group_id": group_id,
        })

    # Arrange into rows to make a roughly square/round overall shape
    # Compute column count so rows ≈ columns (e.g., 49 images → 7×7)
    n = len(slides)
    target_cols = max(1, round(n ** 0.5))
    rows = [slides[i:i + target_cols] for i in range(0, n, target_cols)]

    # Position items in center-aligned rows (ragged left/right edges)
    # First pass: find the widest row to establish the centerline
    max_row_w = max(sum(s["w"] + GAP_X for s in row) - GAP_X for row in rows)
    cx = MARGIN + max_row_w // 2  # horizontal centerline
    y_cursor = MARGIN
    group_ids = []
    for row in rows:
        row_w = sum(s["w"] + GAP_X for s in row) - GAP_X
        x_start = cx - row_w // 2

        # Cell height: image + text gap + text + button gap + button
        row_cell_h = max(s["h"] + GAP_TEXT + s["text_h"] + BTN_GAP + BTN_HEIGHT for s in row)

        for slide in row:
            # Position image
            slide["img"]["position"] = {"x": x_start, "y": y_cursor}
            # Position text below image
            slide["txt"]["position"] = {"x": x_start, "y": y_cursor + slide["h"] + GAP_TEXT}
            # Position Commons link button below caption
            slide["btn"]["position"] = {"x": x_start, "y": y_cursor + slide["h"] + GAP_TEXT + slide["text_h"] + BTN_GAP}
            # Track group IDs for presentation focus
            group_ids.append(slide["group_id"])
            x_start += slide["w"] + GAP_X

        y_cursor += row_cell_h + GAP_ROW

    # ── 5. Presentation order (guided tour) — focus on each image+caption+button group ──
    # Using groups instead of individual items lets Tapestries zoom out enough
    # to show the image, its caption text, and the Commons link button together.
    pres_step_ids = []
    for gid in group_ids:
        step_id = make_id()
        pres_step_ids.append(step_id)
        builder.root["presentation"].append({
            "id": step_id,
            "prevStepId": pres_step_ids[-2] if len(pres_step_ids) >= 2 else None,
            "type": "group",
            "groupId": gid,
        })

    # ── 6. Dynamic start view (zoom out to fit all items) ──
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

    # ── 7. Output path ──
    if output is None:
        safe = re.sub(r"[^\w\- ]", "_", page_title)
        safe = re.sub(r"\s+", "_", safe)
        output = f"{safe}_images.zip"

    builder.save_zip(output)
    return output


# ── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Convert Wikipedia article images into a Tapestry slideshow.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python3 wikipedia-images-to-tapestry.py "Chess"\n'
            '  python3 wikipedia-images-to-tapestry.py "Great Barrier Reef" --image-width 600\n'
            '  python3 wikipedia-images-to-tapestry.py "https://en.wikipedia.org/wiki/Python_(programming_language)" -o python_slideshow.zip\n'
        )
    )
    parser.add_argument("article", help="Wikipedia article title or full URL")
    parser.add_argument("--lang", default="en", help="Wikipedia language code (default: en)")
    parser.add_argument("--max-images", type=int, default=50,
                        help="Maximum number of images to include (default: 50)")
    parser.add_argument("--image-width", type=int, default=600,
                        help="Display width of each image in pixels (default: 600)")
    parser.add_argument("--output", "-o", help="Output .zip file path")

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

    convert_wikipedia_images_to_tapestry(
        title=title,
        lang=lang,
        max_images=args.max_images,
        image_width=args.image_width,
        output=args.output,
    )

if __name__ == "__main__":
    main()
