#!/usr/bin/env python3
"""
VideoWiki → Tapestry Slideshow Converter

Converts a VideoWiki script page into a Tapestry slideshow where each
section becomes a slide with its hand-picked images and narration text.

VideoWiki scripts are Wikipedia subpages that pair images with narrated
text to create a video-like experience. This converter preserves that
narrative flow as an interactive Tapestry slideshow.

Usage:
  python3 videowiki-to-tapestry.py "Wikipedia:VideoWiki/Birthday_cake" [options]
  python3 videowiki-to-tapestry.py "https://en.wikipedia.org/wiki/Wikipedia:VideoWiki/Birthday_cake"

Examples:
  python3 videowiki-to-tapestry.py "Wikipedia:VideoWiki/Birthday_cake"
  python3 videowiki-to-tapestry.py "Wikipedia:VideoWiki/A._P._J._Abdul_Kalam" --image-width 500
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

USER_AGENT = "VideoWikiToTapestryBot/1.0 (andrew.lih@gmail.com) VWSlideshow"
ACTION_API = "https://en.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})

# Layout defaults (pixels)
MARGIN = 40
IMAGE_DISPLAY_WIDTH = 600
TEXT_MIN_HEIGHT = 100
GAP_X = 20
GAP_TEXT = 8
GAP_ROW = 30
BTN_HEIGHT = 36
BTN_GAP = 6

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

def retrying_sleep(seconds=0.3):
    time.sleep(seconds)

def fetch_page_wikitext(page_title: str) -> str:
    """Fetch the raw wikitext of a Wikipedia page."""
    data = wiki_request(ACTION_API, {
        "action": "parse",
        "page": page_title,
        "prop": "wikitext",
        "format": "json",
    })
    return data.get("parse", {}).get("wikitext", {}).get("*", "")

def get_image_info_from_commons(filename: str, req_width: int = 800):
    """Get thumbnail URL and original dimensions from Commons."""
    fname = filename if filename.startswith("File:") else f"File:{filename}"
    retrying_sleep(0.3)
    try:
        data = wiki_request(COMMONS_API, {
            "action": "query",
            "titles": fname,
            "prop": "imageinfo",
            "iiprop": "url|size",
            "iiurlwidth": req_width,
            "format": "json",
        })
        for pdata in data.get("query", {}).get("pages", {}).values():
            info = pdata.get("imageinfo", [])
            if info:
                return {
                    "thumb_url": info[0].get("thumburl") or info[0].get("url"),
                    "orig_w": info[0].get("width", req_width),
                    "orig_h": info[0].get("height", req_width),
                }
    except Exception as e:
        print(f"  ⚠️  Could not fetch info for {filename}: {e}", file=sys.stderr)
    return None

def get_display_dimensions(orig_w: int, orig_h: int, max_width: int):
    """Calculate display dimensions preserving aspect ratio."""
    if orig_w <= 0 or orig_h <= 0:
        return (max_width, max_width)
    if orig_w <= max_width:
        return (orig_w, orig_h)
    scale = max_width / orig_w
    return (max_width, max(60, int(orig_h * scale)))

def estimate_text_height(text_html: str, max_width: int) -> int:
    """Roughly estimate the height needed to display HTML text."""
    plain = re.sub(r'<[^>]+>', '', text_html)
    plain = html.unescape(plain).strip()
    if not plain:
        return TEXT_MIN_HEIGHT
    chars_per_line = max(20, max_width // 9)
    num_lines = max(1, len(plain) // chars_per_line + 1)
    br_count = text_html.count("<br>") + text_html.count("<br/>")
    num_lines += br_count
    height = max(TEXT_MIN_HEIGHT, num_lines * 18 + 20)
    return min(height, 400)


# ── VideoWiki Parser ──────────────────────────────────────────────────────

def parse_videowiki(wikitext: str) -> list[dict]:
    """Parse VideoWiki wikitext into slides.
    
    Returns list of dicts: {title, narration, images: [filename, ...]}
    """
    # Find the ==References== boundary if present
    ref_match = re.search(r'^==\s*References\s*==', wikitext, re.MULTILINE)
    if ref_match:
        wikitext = wikitext[:ref_match.start()]

    # Find all section headings (level 2, 3, 4)
    heading_re = re.compile(r'^(={2,4})\s*(.+?)\s*\1\s*$', re.MULTILINE)
    headings = []
    for m in heading_re.finditer(wikitext):
        level = len(m.group(1))
        title = m.group(2).strip()
        headings.append((level, title, m.start(), m.end()))

    if not headings:
        return []

    slides = []
    for i, (level, title, h_start, h_end) in enumerate(headings):
        # Determine content range for this section
        if i + 1 < len(headings):
            content = wikitext[h_end:headings[i + 1][2]]
        else:
            content = wikitext[h_end:]

        # Extract images: [[File:...]]
        images = re.findall(r'\[\[File\s*:\s*([^\]|]+)', content, re.IGNORECASE)
        images = [f.strip() for f in images if f.strip()]

        # If no images, skip (VideoWiki requires at least one image per slide)
        if not images:
            continue

        # Extract narration: strip markup, keep readable text
        narration = content

        # Remove [[File:...]] links entirely
        narration = re.sub(r'\[\[\s*File\s*:[^\[\]]+\]\]', '', narration, flags=re.IGNORECASE)

        # Remove <ref>...</ref> footnotes
        narration = re.sub(r'<ref[^>]*>.*?</ref>', '', narration, flags=re.DOTALL)
        narration = re.sub(r'<ref[^>]*/?>', '', narration)

        # Strip {{ReadShow|read=...|show=...}} — keep only the visible text
        narration = re.sub(r'\{\{ReadShow\|[^}]*show\s*=\s*([^}|]+)[^}]*\}\}',
                           r'\1', narration, flags=re.IGNORECASE)
        narration = re.sub(r'\{\{ReadShow\|[^}]*\}\}', '', narration, flags=re.IGNORECASE)

        # Strip other templates: {{cite ...}}, {{webarchive}}, {{videowiki}}, etc.
        narration = re.sub(r'\{\{[^}]*\}\}', '', narration)

        # Strip wiki markup: bold, italic, links
        narration = re.sub(r"'''?", '', narration)
        narration = re.sub(r"\[\[([^\]|]+)\|([^\]|]+)\]\]", r'\2', narration)
        narration = re.sub(r"\[\[([^\]|]+)\]\]", r'\1', narration)

        # Clean whitespace
        narration = re.sub(r'\n+', ' ', narration)
        narration = re.sub(r'\s+', ' ', narration).strip()

        if not narration:
            # Fallback: use the section title as narration
            narration = f"About {title}."

        slides.append({
            'title': title,
            'narration': narration,
            'images': images,
        })

    return slides


# ── Tapestry Builder ──────────────────────────────────────────────────────

class TapestrySlideshowBuilder:
    """Builds a v7 Tapestry zip for the VideoWiki slideshow."""

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

    def add_image_item(self, x, y, w, h, source_url, title=""):
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

    def add_text_item(self, x, y, w, h, html_text):
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

    def add_action_button(self, x, y, w, h, url, label="View on Commons"):
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
        gid = make_id()
        self.root["groups"].append({
            "id": gid,
            "color": None,
            "hasBorder": False,
            "hasBackground": False,
        })
        return gid

    def save_zip(self, output_path):
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("root.json", json.dumps(self.root, indent=2))
            for filename, data in self._binary_files.items():
                zf.writestr(filename, data)
        print(f"\n✅ Tapestry slideshow saved to: {output_path}")
        print(f"   Items: {len(self.root['items'])}")
        print(f"   Groups: {len(self.root['groups'])}")
        print(f"   Presentation steps: {len(self.root['presentation'])}")


# ── Narration formatting ──────────────────────────────────────────────────

def format_narration_html(title: str, narration: str) -> str:
    """Build HTML for the caption text item. Uses VideoWiki narration text."""
    safe_title = html.escape(title)
    safe_narration = html.escape(narration)
    return f"<strong>{safe_title}</strong><br><br>{safe_narration}"


# ── Main conversion ───────────────────────────────────────────────────────

def convert_videowiki_to_tapestry(
    page_title: str,
    max_slides: int = 50,
    image_width: int = 600,
    output: str | None = None,
):
    """Convert a VideoWiki page into a Tapestry slideshow."""

    print(f"🎬 Fetching VideoWiki page: {page_title}")
    print("─" * 60)

    # ── 1. Fetch wikitext ──
    wikitext = fetch_page_wikitext(page_title)
    if not wikitext:
        print("⚠️  Could not fetch page. Check the title.", file=sys.stderr)
        return

    print(f"   Fetched {len(wikitext)} characters of wikitext")

    # ── 2. Parse into slides ──
    raw_slides = parse_videowiki(wikitext)
    print(f"   Parsed {len(raw_slides)} slides from VideoWiki script")

    if not raw_slides:
        print("⚠️  No slides found. Is this a valid VideoWiki page?", file=sys.stderr)
        return

    slides = raw_slides[:max_slides]
    if len(raw_slides) > max_slides:
        print(f"   Limiting to {max_slides} slides")

    # ── 3. Flatten: one tapestry slide per image, carry the narration ──
    # A VideoWiki section can have multiple images; we create one tapestry
    # group per image so the user sees all of them.
    image_slides = []  # {title, narration, image_name, section_index}
    for slide in slides:
        for img_name in slide['images']:
            image_slides.append({
                'title': slide['title'],
                'narration': slide['narration'],
                'image_name': img_name,
            })

    print(f"   Expanded to {len(image_slides)} image slides ({len(slides)} sections)")

    # ── 4. Fetch image info from Commons ──
    print(f"\n🔍 Fetching image info from Commons ({len(image_slides)} images)...")
    for idx, islide in enumerate(image_slides):
        print(f"   [{idx+1}/{len(image_slides)}] {islide['image_name'][:60]}...", end="")
        sys.stdout.flush()

        info = get_image_info_from_commons(islide['image_name'], req_width=image_width)
        if info and info['thumb_url']:
            islide['thumb_url'] = info['thumb_url']
            islide['orig_w'] = info['orig_w']
            islide['orig_h'] = info['orig_h']
            print(" ✓")
        else:
            print(" ⚠️  skipped (no URL)")
            islide['skip'] = True

    image_slides = [s for s in image_slides if not s.get('skip')]

    if not image_slides:
        print("⚠️  No images could be processed.", file=sys.stderr)
        return

    # ── 5. Build the Tapestry layout ──
    print(f"\n🎨 Building Tapestry slideshow layout ({len(image_slides)} slides)...")
    builder = TapestrySlideshowBuilder(page_title.replace("Wikipedia:VideoWiki/", ""))

    # Create groups: one per image, each with image + narration + Commons button
    slides_out = []
    for islide in image_slides:
        disp_w, disp_h = get_display_dimensions(
            islide['orig_w'], islide['orig_h'], image_width
        )
        caption_html = format_narration_html(islide['title'], islide['narration'])
        text_h = estimate_text_height(caption_html, disp_w)

        group_id = builder.add_group()
        commons_url = f"https://commons.wikimedia.org/wiki/File:{quote(islide['image_name'])}"

        img_item = builder.add_image_item(0, 0, disp_w, disp_h,
                                          source_url=islide['thumb_url'])
        img_item['groupId'] = group_id

        txt_item = builder.add_text_item(0, 0, disp_w, text_h, caption_html)
        txt_item['groupId'] = group_id

        btn_item = builder.add_action_button(0, 0, disp_w, BTN_HEIGHT,
                                             url=commons_url,
                                             label="🌐  View on Wikimedia Commons")
        btn_item['groupId'] = group_id

        slides_out.append({
            'img': img_item,
            'txt': txt_item,
            'btn': btn_item,
            'w': disp_w,
            'h': disp_h,
            'text_h': text_h,
            'group_id': group_id,
        })

    # Arrange into roughly square rows (same sqrt(N) approach)
    n = len(slides_out)
    target_cols = max(1, round(n ** 0.5))
    rows = [slides_out[i:i + target_cols] for i in range(0, n, target_cols)]

    max_row_w = max(sum(s['w'] + GAP_X for s in row) - GAP_X for row in rows)
    cx = MARGIN + max_row_w // 2
    y_cursor = MARGIN
    group_ids = []

    for row in rows:
        row_w = sum(s['w'] + GAP_X for s in row) - GAP_X
        x_start = cx - row_w // 2
        row_cell_h = max(s['h'] + GAP_TEXT + s['text_h'] + BTN_GAP + BTN_HEIGHT for s in row)

        for slide in row:
            slide['img']['position'] = {'x': x_start, 'y': y_cursor}
            slide['txt']['position'] = {'x': x_start, 'y': y_cursor + slide['h'] + GAP_TEXT}
            slide['btn']['position'] = {
                'x': x_start,
                'y': y_cursor + slide['h'] + GAP_TEXT + slide['text_h'] + BTN_GAP,
            }
            group_ids.append(slide['group_id'])
            x_start += slide['w'] + GAP_X

        y_cursor += row_cell_h + GAP_ROW

    # ── 6. Presentation — focus on each image+caption+button group ──
    pres_step_ids = []
    for gid in group_ids:
        step_id = make_id()
        pres_step_ids.append(step_id)
        builder.root['presentation'].append({
            'id': step_id,
            'prevStepId': pres_step_ids[-2] if len(pres_step_ids) >= 2 else None,
            'type': 'group',
            'groupId': gid,
        })

    # ── 7. Dynamic startView ──
    if builder.root['items']:
        xs = [i['position']['x'] for i in builder.root['items']]
        ys = [i['position']['y'] for i in builder.root['items']]
        ws = [i['position']['x'] + i['size']['width'] for i in builder.root['items']]
        hs = [i['position']['y'] + i['size']['height'] for i in builder.root['items']]
        pad = 60
        builder.root['startView'] = {
            'position': {'x': min(xs) - pad, 'y': min(ys) - pad},
            'size': {'width': max(ws) - min(xs) + pad * 2, 'height': max(hs) - min(ys) + pad * 2},
        }

    # ── 8. Output path ──
    if output is None:
        safe = re.sub(r'[^\w\- ]', '_', page_title.replace("Wikipedia:VideoWiki/", ""))
        safe = re.sub(r'\s+', '_', safe)
        output = f'{safe}_videowiki.zip'

    builder.save_zip(output)
    return output


# ── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Convert a VideoWiki page into a Tapestry slideshow.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python3 videowiki-to-tapestry.py "Wikipedia:VideoWiki/Birthday_cake"\n'
            '  python3 videowiki-to-tapestry.py "https://en.wikipedia.org/wiki/Wikipedia:VideoWiki/Birthday_cake"\n'
            '  python3 videowiki-to-tapestry.py "Wikipedia:VideoWiki/A._P._J._Abdul_Kalam" --image-width 500\n'
        )
    )
    parser.add_argument("page", help="VideoWiki page title or full URL")
    parser.add_argument("--max-slides", type=int, default=50,
                        help="Maximum number of slides (default: 50)")
    parser.add_argument("--image-width", type=int, default=600,
                        help="Display width of each image in pixels (default: 600)")
    parser.add_argument("--output", "-o", help="Output .zip file path")

    args = parser.parse_args()

    page = args.page
    page_title = page

    # Parse URL or title
    url_match = re.match(
        r"https?://([a-z]{2,3})\.wikipedia\.org/wiki/(.+)$",
        page
    )
    if url_match:
        page_title = unquote(url_match.group(2))
        page_title = page_title.split("#")[0]

    # Ensure the page is in the VideoWiki namespace
    if not page_title.startswith("Wikipedia:VideoWiki/"):
        page_title = f"Wikipedia:VideoWiki/{page_title}"

    convert_videowiki_to_tapestry(
        page_title=page_title,
        max_slides=args.max_slides,
        image_width=args.image_width,
        output=args.output,
    )

if __name__ == "__main__":
    main()
