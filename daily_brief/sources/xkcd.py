"""Latest xkcd comic from the official JSON API.

Fetches the current comic's metadata and image, scales it to fit the
printer width, and renders it as a bitmap. The API is free, requires no
authentication, and updates every Monday, Wednesday, and Friday.
"""

from __future__ import annotations

import logging
from io import BytesIO

import requests
from PIL import Image

from ..brief import Picture, Section, Text
from ._http import get_json

log = logging.getLogger(__name__)

API_URL = "https://xkcd.com/info.0.json"


def _fetch_image(url: str) -> Image.Image | None:
    """Download an image URL and return a PIL Image, or None on failure."""
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return Image.open(BytesIO(resp.content)).convert("L")  # grayscale
    except Exception as exc:
        log.warning("xkcd image fetch failed: %s", exc)
        return None


def build(section_cfg, ctx) -> Section | None:
    title = section_cfg.title or "XKCD"
    show_alt = section_cfg.get("show_alt", True)

    # Cache 12h — xkcd updates Mon/Wed/Fri so we'll pick up new ones same day.
    data = get_json(API_URL, ttl=43_200)
    if not data:
        return Section(title, [Text("(unavailable)")])

    comic_title = data.get("title", "")
    comic_num = data.get("num", "")
    img_url = data.get("img", "")
    alt_text = data.get("alt", "")

    items = []
    items.append(Text(f"#{comic_num} — {comic_title}"))

    # Fetch and render the comic image
    if img_url:
        image = _fetch_image(img_url)
        if image:
            items.append(Picture(image))
        else:
            items.append(Text("(image unavailable)"))

    # The alt/hover text is often the best part
    if show_alt and alt_text:
        items.append(Text(alt_text))

    return Section(title, items)
