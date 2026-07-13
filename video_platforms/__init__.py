#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multi-platform video extraction — Bilibili, YouTube, Vimeo, TikTok, and more."""

from __future__ import annotations

from typing import Callable

from playwright.sync_api import Page

from video_platforms.merge import merge_platform_result
from video_platforms.registry import (
    VIDEO_PLATFORMS,
    detect_video_platform,
    is_video_platform_url,
)

LogFn = Callable[[str], None]

__all__ = [
    "VIDEO_PLATFORMS",
    "detect_video_platform",
    "extract_platform_data",
    "is_video_platform_url",
    "merge_platform_result",
]


def extract_platform_data(page: Page, url: str, log: LogFn) -> dict | None:
    """Run the best-matching platform extractor for *url*."""
    platform = detect_video_platform(url)
    if not platform:
        return None

    handler = VIDEO_PLATFORMS[platform]
    log(f"[Video:{platform}] Detected — extracting metadata and streams ...")
    payload = handler.extract(page, url, log)
    if not payload:
        return None

    payload["platform"] = platform
    return payload
