"""Serve saved magazine page images, with on-the-fly cached thumbnails (Pillow)."""
from pathlib import Path

from PIL import Image

import settings


def page_path(slug: str, page: int) -> Path:
    return settings.RAW / slug / f"page_{int(page):03d}.jpg"


def _thumb_path(slug: str, page: int, w: int) -> Path:
    d = settings.THUMBS / slug
    d.mkdir(parents=True, exist_ok=True)
    return d / f"page_{int(page):03d}_w{w}.jpg"


def get_image(slug: str, page: int, w: int | None = None, full: bool = False):
    src = page_path(slug, page)
    if not src.exists():
        return None
    if full or not w:
        return src
    tp = _thumb_path(slug, page, w)
    if not tp.exists():
        try:
            im = Image.open(src).convert("RGB")
            im.thumbnail((w, w * 2))
            im.save(tp, "JPEG", quality=82)
        except Exception:  # noqa: BLE001
            return src
    return tp
