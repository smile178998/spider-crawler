#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Image URL normalization and junk filtering."""

from __future__ import annotations

import re
from urllib.parse import urlparse

IMAGE_SKIP_HINTS = [
    "/bfs/static/",
    "jinkela",
    "/icon",
    "/icons/",
    "favicon",
    ".svg",
    "emoji",
    "placeholder",
    "loading.gif",
    "blank.gif",
    "avatar/icon",
    "/assets/",
    "sprite",
    "data:image",
]

BILIBILI_JUNK_HINTS = [
    "rcmd-cover",
    "ad-cover",
    "web-video-rcmd",
    "web-video-ad",
    "web-video-right-bottom-ad",
    "web-video-share-cover",
    "/bfs/banner/",
    "/bfs/garb/",
    "/bfs/sycp/",
    "/bfs/legacy/",
    "mgk/collage",
    "!web-avatar",
]

BILIBILI_GOOD_HINTS = [
    "/bfs/archive/",
    "/bfs/face/",
    "firsti.jpg",
    "first_frame",
    "/bfs/new_dyn/",
]

IMAGE_SIZE_THUMB_RE = re.compile(r"@(\d+)w_", re.I)
BILIBILI_SIZE_SUFFIX_RE = re.compile(r"@[^/]*$", re.I)


def normalize_image_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    if url.startswith("http://"):
        url = "https://" + url[7:]
    return url


def strip_bilibili_resize(url: str) -> str:
    """Remove Bilibili @resize suffix for a stable, loadable URL."""
    url = normalize_image_url(url)
    if "hdslb.com" not in url:
        return url
    return BILIBILI_SIZE_SUFFIX_RE.sub("", url)


def is_page_url_not_image(url: str) -> bool:
    lower = url.lower()
    if lower.startswith("blob:"):
        return True
    parsed = urlparse(lower)
    path = parsed.path or ""
    if "bilibili.com/video" in lower or path.endswith("/video/") or "/video/bv" in lower:
        return True
    if path in ("", "/") and "bilibili.com" in parsed.netloc:
        return True
    image_exts = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".bmp")
    if "hdslb.com" in lower or "bilibili.com" in lower:
        if "/bfs/" in path or any(path.endswith(ext) for ext in image_exts):
            return False
        return True
    if any(path.endswith(ext) for ext in image_exts):
        return False
    if "/image" in path or "img" in parsed.netloc:
        return False
    return not bool(re.search(r"\.(jpe?g|png|webp|gif|avif)(?:\?|$|@)", lower))


def is_bilibili_good(url: str) -> bool:
    lower = (url or "").lower()
    return any(g in lower for g in BILIBILI_GOOD_HINTS)


def is_bilibili_junk(url: str) -> bool:
    lower = (url or "").lower()
    if is_bilibili_good(lower):
        return False
    if any(h in lower for h in BILIBILI_JUNK_HINTS):
        return True
    match = IMAGE_SIZE_THUMB_RE.search(lower)
    if match and int(match.group(1)) <= 190:
        return True
    if "hdslb.com" in lower:
        return True
    return False


def is_content_image(url: str, *, platform: str = "") -> bool:
    """Filter out icons, UI sprites, and invalid thumbnails."""
    url = normalize_image_url(url)
    if not url or is_page_url_not_image(url):
        return False
    lower = url.lower()
    if lower.startswith("data:"):
        return False
    if any(hint in lower for hint in IMAGE_SKIP_HINTS):
        return False
    if platform == "bilibili" or "hdslb.com" in lower or "bilibili.com" in lower:
        return not is_bilibili_junk(url)
    match = IMAGE_SIZE_THUMB_RE.search(lower)
    if match and int(match.group(1)) <= 100:
        return False
    return True


def collect_images(
    urls: list[str],
    limit: int = 50,
    *,
    platform: str = "",
) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    plat = platform
    if not plat:
        for raw in urls:
            if "hdslb.com" in (raw or "").lower():
                plat = "bilibili"
                break

    for raw in urls:
        src = strip_bilibili_resize(raw) if plat == "bilibili" else normalize_image_url(raw)
        if not is_content_image(src, platform=plat) or src in seen:
            continue
        seen.add(src)
        out.append(src)
        if len(out) >= limit:
            break
    return out


def filter_images_for_url(page_url: str, images: list[str], limit: int = 50) -> list[str]:
    """Re-filter images using the source page URL (e.g. after generic HTML parse)."""
    plat = "bilibili" if "bilibili.com" in (page_url or "") or "b23.tv" in (page_url or "") else ""
    return collect_images(images, limit=limit, platform=plat)


def pick_og_image(meta: dict, *, platform: str = "") -> str | None:
    for key in ("og:image", "twitter:image", "image"):
        val = (meta or {}).get(key, "")
        if not val:
            continue
        plat = platform
        if not plat and ("hdslb.com" in val or "bilibili" in val.lower()):
            plat = "bilibili"
        candidate = (
            strip_bilibili_resize(val) if plat == "bilibili" else normalize_image_url(val)
        )
        if is_content_image(candidate, platform=plat):
            return candidate
    return None
