#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Image URL normalization and junk filtering."""

from __future__ import annotations

import re

IMAGE_SKIP_HINTS = [
    "/bfs/static/", "jinkela", "/icon", "/icons/", "favicon", ".svg",
    "emoji", "placeholder", "loading.gif", "blank.gif", "avatar/icon",
    "/assets/", "sprite", "data:image",
]

IMAGE_SIZE_THUMB_RE = re.compile(r"@(\d+)w_", re.I)


def normalize_image_url(url: str) -> str:
    url = url.strip()
    if url.startswith("//"):
        return "https:" + url
    return url


def is_content_image(url: str) -> bool:
    """Filter out icons, UI sprites, and tiny thumbnail assets."""
    if not url:
        return False
    lower = url.lower()
    if lower.startswith("data:"):
        return False
    if any(hint in lower for hint in IMAGE_SKIP_HINTS):
        return False
    match = IMAGE_SIZE_THUMB_RE.search(lower)
    if match and int(match.group(1)) <= 100:
        return False
    return True


def collect_images(urls: list[str], limit: int = 50) -> list[str]:
    seen, out = set(), []
    for raw in urls:
        src = normalize_image_url(raw)
        if not is_content_image(src) or src in seen:
            continue
        seen.add(src)
        out.append(src)
        if len(out) >= limit:
            break
    return out
