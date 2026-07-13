#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Video platform registry — URL detection and handler dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

from playwright.sync_api import Page

from video_platforms import bilibili, generic

LogFn = Callable[[str], None]
ExtractFn = Callable[[Page, str, LogFn], dict | None]


@dataclass(frozen=True)
class PlatformHandler:
    name: str
    match: Callable[[str], bool]
    extract: ExtractFn
    priority: int = 0


VIDEO_PLATFORMS: dict[str, PlatformHandler] = {
    "bilibili": PlatformHandler(
        name="bilibili",
        match=bilibili.match_url,
        extract=bilibili.extract,
        priority=100,
    ),
    "youtube": PlatformHandler(
        name="youtube",
        match=generic.match_youtube,
        extract=generic.extract,
        priority=50,
    ),
    "vimeo": PlatformHandler(
        name="vimeo",
        match=generic.match_vimeo,
        extract=generic.extract,
        priority=50,
    ),
    "tiktok": PlatformHandler(
        name="tiktok",
        match=generic.match_tiktok,
        extract=generic.extract,
        priority=50,
    ),
    "douyin": PlatformHandler(
        name="douyin",
        match=generic.match_douyin,
        extract=generic.extract,
        priority=50,
    ),
    "twitter": PlatformHandler(
        name="twitter",
        match=generic.match_twitter,
        extract=generic.extract,
        priority=50,
    ),
    "twitch": PlatformHandler(
        name="twitch",
        match=generic.match_twitch,
        extract=generic.extract,
        priority=50,
    ),
    "dailymotion": PlatformHandler(
        name="dailymotion",
        match=generic.match_dailymotion,
        extract=generic.extract,
        priority=50,
    ),
    "niconico": PlatformHandler(
        name="niconico",
        match=generic.match_niconico,
        extract=generic.extract,
        priority=50,
    ),
}


def detect_video_platform(url: str) -> str | None:
    """Return the highest-priority matching platform id, or None."""
    host = urlparse(url).netloc.lower()
    if not host:
        return None

    matches = [
        handler
        for handler in VIDEO_PLATFORMS.values()
        if handler.match(url)
    ]
    if not matches:
        return None

    matches.sort(key=lambda h: h.priority, reverse=True)
    return matches[0].name


def is_video_platform_url(url: str) -> bool:
    return detect_video_platform(url) is not None
