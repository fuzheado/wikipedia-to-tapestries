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
import asyncio
import html
import io
import json
import math
import os
import re
import sys
import tempfile
import time
import uuid
import zipfile
from urllib.parse import quote, unquote

import requests

try:
    import edge_tts
    HAS_TTS = True
except ImportError:
    HAS_TTS = False
    print("⚠️  edge_tts not installed. Run: pip install edge-tts", file=sys.stderr)

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
AUDIO_HEIGHT = 60   # height of the TTS audio player bar
AUDIO_GAP = 6       # gap between Commons button and audio player

# Text-to-speech defaults
TTS_VOICE = "en-US-JennyNeural"  # Microsoft neural voice

# Action button defaults
BUTTON_COLOR = "#dce8f5"  # pale blue — subtle, doesn't compete with images
BUTTON_LABEL = "🌐  View on Wikimedia Commons"

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
            print(f"  ⏳ Rate limited - waiting {retry_after}s...", file=sys.stderr)
            time.sleep(retry_after)
            continue
        if resp.status_code == 403:
            raise PermissionError(
                "403 Forbidden - check User-Agent header. "
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

def get_video_info_from_commons(filename: str) -> dict | None:
    """Get video thumbnail URL from Commons."""
    fname = filename if filename.startswith("File:") else f"File:{filename}"
    retrying_sleep(0.3)
    try:
        data = wiki_request(COMMONS_API, {
            "action": "query",
            "titles": fname,
            "prop": "videoinfo",
            "viprop": "thumburl|size",
            "format": "json",
        })
        for pdata in data.get("query", {}).get("pages", {}).values():
            info = pdata.get("videoinfo", [])
            if info:
                return {
                    "thumb_url": info[0].get("thumburl") or info[0].get("url"),
                    "orig_w": info[0].get("width", 640),
                    "orig_h": info[0].get("height", 480),
                }
    except Exception as e:
        print(f"  ⚠️  Could not fetch video info for {filename}: {e}", file=sys.stderr)
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

    Returns list of dicts: {title, narration, tts_text, images: [filename, ...],
                           citations: [{ref_id, text}]}
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

        # Extract images (including videos): [[File:...]]
        images = re.findall(r'\[\[File\s*:\s*([^\]|]+)', content, re.IGNORECASE)
        images = [f.strip() for f in images if f.strip()]

        # If no images, skip (VideoWiki requires at least one image per slide)
        if not images:
            continue

        # ── Extract and preserve citations ──
        citations = []
        def save_ref(m):
            ref_id = str(len(citations) + 1)
            raw = m.group(1)
            # Try to extract a readable title/URL from cite templates
            title_m = re.search(r'\btitle\s*=\s*([^|}]+)', raw, re.IGNORECASE)
            if title_m:
                ref_text = title_m.group(1).strip()[:120]
            else:
                url_m = re.search(r'\burl\s*=\s*([^|}]+)', raw, re.IGNORECASE)
                if url_m:
                    ref_text = url_m.group(1).strip()[:80]
                else:
                    ref_text = re.sub(r'<[^>]+>', '', raw).strip()[:80]
            citations.append({"ref_id": ref_id, "text": ref_text})
            # Use a placeholder that won't be caught by template stripping ({{...}})
            return f"§§CIT{ref_id}§§"

        narration = content
        narration = re.sub(r'<ref[^>]*>(.*?)</ref>', save_ref, narration, flags=re.DOTALL)
        narration = re.sub(r'<ref[^>]*/>', '', narration)

        # ── Remove [[File:...]] links ──
        narration = re.sub(r'\[\[\s*File\s*:[^\[\]]+\]\]', '', narration, flags=re.IGNORECASE)

        # ── Handle {{ReadShow|read=...|show=...}} ──
        # Extract show= for display text, remember read= for TTS
        tts_narration = narration
        readshow_pattern = re.compile(
            r'\{\{ReadShow\|\s*read\s*=\s*([^|}]+).*?\}\}',
            re.IGNORECASE | re.DOTALL
        )
        for rm in readshow_pattern.finditer(tts_narration):
            read_val = rm.group(1).strip()
            # Replace the whole template with the read= text for TTS
            tts_narration = tts_narration.replace(rm.group(0), read_val)

        # For display: keep show= text, strip the rest
        narration = re.sub(
            r'\{\{ReadShow\|[^}]*show\s*=\s*([^}|]+)[^}]*\}\}',
            r'\1', narration, flags=re.IGNORECASE
        )
        narration = re.sub(r'\{\{ReadShow\|[^}]*\}\}', '', narration, flags=re.IGNORECASE)

        # ── Strip other templates ──
        narration = re.sub(r'\{\{[^}]*\}\}', '', narration)
        tts_narration = re.sub(r'\{\{[^}]*\}\}', '', tts_narration)

        # ── Strip wiki markup ──
        narration = re.sub(r"'''?", '', narration)
        tts_narration = re.sub(r"'''?", '', tts_narration)
        narration = re.sub(r"\[\[([^\]|]+)\|([^\]|]+)\]\]", r'\2', narration)
        narration = re.sub(r"\[\[([^\]|]+)\]\]", r'\1', narration)
        tts_narration = re.sub(r"\[\[([^\]|]+)\|([^\]|]+)\]\]", r'\2', tts_narration)
        tts_narration = re.sub(r"\[\[([^\]|]+)\]\]", r'\1', tts_narration)

        # ── Replace citation placeholders ──
        for cit in citations:
            narration = narration.replace(
                f"§§CIT{cit['ref_id']}§§",
                f"<sup>[{cit['ref_id']}]</sup>"
            )
            tts_narration = tts_narration.replace(f"§§CIT{cit['ref_id']}§§", '')

        # ── Clean whitespace ──
        narration = re.sub(r'\n+', ' ', narration)
        narration = re.sub(r'\s+', ' ', narration).strip()
        tts_narration = re.sub(r'\n+', ' ', tts_narration)
        tts_narration = re.sub(r'\s+', ' ', tts_narration).strip()

        if not narration:
            narration = f"About {title}."
        if not tts_narration:
            tts_narration = narration

        slides.append({
            'title': title,
            'narration': narration,
            'tts_text': tts_narration,
            'images': images,
            'citations': citations,
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

    def add_video_item(self, x, y, w, h, source_url, title=""):
        """Add a video item, returning the item dict."""
        item = {
            "id": make_id(),
            "type": "video",
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

    def add_action_button(self, x, y, w, h, url, label="View on Commons",
                           background_color=None):
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
            "backgroundColor": background_color or BUTTON_COLOR,
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


# ── Text-to-Speech ────────────────────────────────────────────────────────

def generate_narration_audio(text: str, voice: str = TTS_VOICE) -> bytes | None:
    """Generate TTS audio bytes for the narration text using edge-tts.
    Returns MP3 bytes, or None if generation fails."""
    if not HAS_TTS or not text.strip():
        return None
    try:
        path = os.path.join(tempfile.gettempdir(), f"vw_tts_{uuid.uuid4().hex}.mp3")
        asyncio.run(edge_tts.Communicate(text[:1500], voice).save(path))
        with open(path, "rb") as f:
            data = f.read()
        os.remove(path)
        return data
    except Exception as e:
        print(f"  ⚠️  TTS failed: {e}", file=sys.stderr)
        return None


# ── Main conversion ───────────────────────────────────────────────────────

def convert_videowiki_to_tapestry(
    page_title: str,
    max_slides: int = 50,
    image_width: int = 600,
    output: str | None = None,
    generate_audio: bool = False,
    tts_voice: str = TTS_VOICE,
    text_scale: float = 1.0,
    button_color: str = BUTTON_COLOR,
    layout: str = "grid",
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

    # ── 3. Fetch image/video info from Commons per section ──
    print(f"\n🔍 Fetching media info from Commons...")
    total_images = sum(len(s['images']) for s in slides)
    image_idx = 0
    for slide in slides:
        for img_name in slide['images']:
            image_idx += 1
            is_video = bool(re.search(r'\.(webm|mp4|ogv|ogg)$', img_name, re.I))
            print(f"   [{image_idx}/{total_images}] {img_name[:60]}...", end="")
            sys.stdout.flush()

            if is_video:
                info = get_video_info_from_commons(img_name)
            else:
                info = get_image_info_from_commons(img_name, req_width=image_width)

            if info and info['thumb_url']:
                img_info = {
                    'name': img_name,
                    'thumb_url': info['thumb_url'],
                    'orig_w': info['orig_w'],
                    'orig_h': info['orig_h'],
                    'is_video': is_video,
                }
                if 'images_info' not in slide:
                    slide['images_info'] = []
                slide['images_info'].append(img_info)
                print(" ✓")
            else:
                print(" ⚠️  skipped")

    # Remove slides with no usable images
    slides = [s for s in slides if s.get('images_info')]

    if not slides:
        print("⚠️  No images could be processed.", file=sys.stderr)
        return

    # ── 4. Renumber citations globally (after filtering dropped slides) ──
    all_citations = []
    global_cit = 0
    for slide in slides:
        if not slide.get('citations'):
            continue
        old_to_new = {}
        for cit in slide['citations']:
            old_ph = f"<sup>[{cit['ref_id']}]</sup>"
            if old_ph not in slide['narration']:
                continue
            global_cit += 1
            new_id = str(global_cit)
            old_to_new[cit['ref_id']] = new_id
            all_citations.append({'ref_id': new_id, 'text': cit['text']})
        for old_id, new_id in old_to_new.items():
            slide['narration'] = slide['narration'].replace(
                f"<sup>[{old_id}]</sup>", f"<sup>[{new_id}]</sup>"
            )
        slide['citations'] = [{'ref_id': old_to_new[c['ref_id']], 'text': c['text']}
                               for c in slide['citations']
                               if c['ref_id'] in old_to_new]

    print(f"   Global citations: {len(all_citations)}")

    # ── 5. Build the Tapestry layout ──
    print(f"\n🎨 Building Tapestry slideshow layout ({len(slides)} groups)...")
    builder = TapestrySlideshowBuilder(page_title.replace("Wikipedia:VideoWiki/", ""))

    # Each section becomes one group with potentially multiple images in a sub-row
    slides_out = []
    for sdx, slide in enumerate(slides):
        images_info = slide['images_info']
        n = len(images_info)

        # Multi-image sections: each image gets an equal share of the cell width
        if n == 1:
            sub_width = image_width
        else:
            sub_width = max(200, int((image_width - (n - 1) * GAP_X) / n))

        group_id = builder.add_group()

        # Create image/video + Commons button for each media item
        imgs_data = []
        for img_info in images_info:
            disp_w, disp_h = get_display_dimensions(
                img_info['orig_w'], img_info['orig_h'], sub_width
            )
            commons_url = f"https://commons.wikimedia.org/wiki/File:{quote(img_info['name'])}"

            if img_info.get('is_video'):
                media_item = builder.add_video_item(
                    0, 0, disp_w, disp_h, source_url=img_info['thumb_url']
                )
            else:
                media_item = builder.add_image_item(
                    0, 0, disp_w, disp_h, source_url=img_info['thumb_url']
                )
            media_item['groupId'] = group_id

            btn_item = builder.add_action_button(
                0, 0, disp_w, BTN_HEIGHT,
                url=commons_url,
                label="🌐  View on Wikimedia Commons",
                background_color=button_color,
            )
            btn_item['groupId'] = group_id

            imgs_data.append({'item': media_item, 'btn': btn_item, 'w': disp_w, 'h': disp_h})

        # Build caption with citation footnotes (feature 5)
        caption_html = format_narration_html(slide['title'], slide['narration'])
        if slide.get('citations'):
            cit_parts = ['<br><br><span style="font-size:0.8em;color:#888;">']
            for cit in slide['citations']:
                safe_text = html.escape(cit['text'])
                safe_id = html.escape(cit['ref_id'])
                cit_parts.append(f"<sup>{safe_id}</sup> {safe_text}<br>")
            cit_parts.append('</span>')
            caption_html += ''.join(cit_parts)

        text_h = int(estimate_text_height(caption_html, image_width) * text_scale)
        txt_item = builder.add_text_item(0, 0, image_width, text_h, caption_html)
        txt_item['groupId'] = group_id

        # Generate TTS audio using tts_text (feature 2: uses ReadShow read= values)
        audio_item = None
        if generate_audio:
            tts_input = slide.get('tts_text') or slide['narration']
            print(f"   🎤 Generating TTS for group {sdx+1}...", end="")
            sys.stdout.flush()
            audio_data = generate_narration_audio(tts_input, voice=tts_voice)
            if audio_data:
                audio_uuid = make_id()
                safe_name = re.sub(r'[^\w\- ]', '_', slide['title'])[:30] or 'narration'
                audio_fname = f"items/{audio_uuid} ({safe_name}).mp3"
                builder._binary_files[audio_fname] = audio_data
                audio_item = {
                    'id': make_id(),
                    'type': 'audio',
                    'position': {'x': 0, 'y': 0},
                    'size': {'width': image_width, 'height': AUDIO_HEIGHT},
                    'title': '',
                    'dropShadow': False,
                    'groupId': group_id,
                    'notes': None,
                    'source': f"file:/{audio_fname}",
                }
                builder.root['items'].append(audio_item)
                print(" ✓")
            else:
                print(" ⚠️  failed")

        # Cell width = total image sub-row width or single image width
        total_img_w = sum(d['w'] + GAP_X for d in imgs_data) - GAP_X
        cell_w = max(total_img_w, image_width)
        max_img_h = max(d['h'] for d in imgs_data)

        slides_out.append({
            'imgs_data': imgs_data,
            'txt': txt_item,
            'audio': audio_item,
            'cell_w': cell_w,
            'img_h': max_img_h,
            'text_h': text_h,
            'group_id': group_id,
        })

    # Arrange into rows based on layout mode
    n_total = len(slides_out)
    if layout == "horizontal":
        target_cols = n_total  # one row, all items
    elif layout == "vertical":
        target_cols = 1        # one column, stacked
    else:
        target_cols = max(1, round(n_total ** 0.5))  # roughly square
    rows = [slides_out[i:i + target_cols] for i in range(0, n_total, target_cols)]

    cx = MARGIN + IMAGE_DISPLAY_WIDTH // 2
    y_cursor = MARGIN
    group_ids = []

    for row in rows:
        row_w = sum(s['cell_w'] + GAP_X for s in row) - GAP_X
        x_start = cx - row_w // 2

        # Cell height: images + button + text + audio
        row_cell_h = max(
            s['img_h'] + BTN_GAP + BTN_HEIGHT + GAP_TEXT + s['text_h']
            + (AUDIO_GAP + AUDIO_HEIGHT if s['audio'] else 0)
            for s in row
        )

        for slide in row:
            imgs_data = slide['imgs_data']
            n = len(imgs_data)

            # Center the image sub-row within the cell width
            sub_row_w = sum(d['w'] + GAP_X for d in imgs_data) - GAP_X
            img_x = x_start + (slide['cell_w'] - sub_row_w) // 2

            for img_data in imgs_data:
                img_data['item']['position'] = {'x': img_x, 'y': y_cursor}
                btn_y = y_cursor + img_data['h'] + BTN_GAP
                img_data['btn']['position'] = {'x': img_x, 'y': btn_y}
                img_x += img_data['w'] + GAP_X

            # Narration text below images/buttons
            txt_y = y_cursor + slide['img_h'] + BTN_GAP + BTN_HEIGHT + GAP_TEXT
            slide['txt']['position'] = {'x': x_start, 'y': txt_y}

            # Audio below text
            if slide['audio']:
                audio_y = txt_y + slide['text_h'] + AUDIO_GAP
                slide['audio']['position'] = {'x': x_start, 'y': audio_y}

            group_ids.append(slide['group_id'])
            x_start += slide['cell_w'] + GAP_X

        y_cursor += row_cell_h + GAP_ROW

    # ── 6. References section (free-floating, not in any group) ──
    y_cursor += GAP_ROW * 2
    if all_citations:
        ref_parts = ['<strong>References</strong><br><br>']
        for cit in all_citations:
            safe_text = html.escape(cit['text'])
            ref_parts.append(f'<sup>{cit["ref_id"]}</sup> {safe_text}<br><br>')
        ref_html = ''.join(ref_parts)
        ref_h = max(TEXT_MIN_HEIGHT, len(all_citations) * 30 + 40)
        builder.add_text_item(MARGIN, y_cursor, IMAGE_DISPLAY_WIDTH, ref_h, ref_html)
        y_cursor += ref_h + GAP_ROW

    # ── 7. Credit footer (free-floating, not in any group) ──
    script_url = f"https://en.wikipedia.org/wiki/{quote(page_title)}"
    credit_html = (
        f'<p style="text-align:center;font-size:0.85em;color:#888;">'
        f'Sourced from <a href="{script_url}">{html.escape(page_title)}</a>'
        f' &middot; Generated by'
        f' <a href="https://github.com/fuzheado/wikipedia-to-tapestries">wikipedia-to-tapestries</a>'
        f'</p>'
    )
    builder.add_text_item(MARGIN, y_cursor, IMAGE_DISPLAY_WIDTH, TEXT_MIN_HEIGHT, credit_html)

    # ── 8. Presentation — focus on each group ──
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

    # ── 9. Dynamic startView (include footer) ──
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

    # ── 10. Output path ──
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
            '  python3 videowiki-to-tapestry.py "Wikipedia:VideoWiki/Birthday_cake" --tts\n'
            '  python3 videowiki-to-tapestry.py "Wikipedia:VideoWiki/Birthday_cake" --text-scale 1.5\n'
            '  python3 videowiki-to-tapestry.py "Wikipedia:VideoWiki/Birthday_cake" --layout horizontal\n'
            '  python3 videowiki-to-tapestry.py "Wikipedia:VideoWiki/Birthday_cake" --button-color "#e8f0fe"\n'
        )
    )
    parser.add_argument("page", help="VideoWiki page title or full URL")
    parser.add_argument("--max-slides", type=int, default=50,
                        help="Maximum number of slides (default: 50)")
    parser.add_argument("--image-width", type=int, default=600,
                        help="Display width of each image in pixels (default: 600)")
    parser.add_argument("--tts", action="store_true",
                        help="Generate spoken narration audio for each slide (requires edge-tts)")
    parser.add_argument("--tts-voice", default=TTS_VOICE,
                        help=f"TTS voice (default: {TTS_VOICE})")
    parser.add_argument("--text-scale", type=float, default=1.0,
                        help="Scale caption text height by multiplier (e.g. 1.5 for more room)")
    parser.add_argument("--button-color", default=BUTTON_COLOR,
                        help=f"Action button background hex color (default: {BUTTON_COLOR})")
    parser.add_argument("--layout", choices=["grid", "horizontal", "vertical"], default="grid",
                        help="Layout: grid (square-ish), horizontal (single row), vertical (single column)")
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
        generate_audio=args.tts,
        tts_voice=args.tts_voice,
        text_scale=args.text_scale,
        button_color=args.button_color,
        layout=args.layout,
    )

if __name__ == "__main__":
    main()
