#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generic video metadata extraction via meta tags, JSON-LD, and in-page state."""

from __future__ import annotations

from typing import Callable
from urllib.parse import urlparse

from playwright.sync_api import Page

LogFn = Callable[[str], None]

_GENERIC_EXTRACT_JS = r"""
(platform) => {
    const out = {
        platform,
        title: document.title || "",
        description: "",
        author: { name: "", face: "" },
        cover: "",
        video_id: "",
        video_streams: [],
        audio_streams: [],
        comments: [],
        stat: {},
        tags: [],
        embed_url: "",
    };

    const addStream = (url, quality, bandwidth, mime) => {
        if (!url || url.startsWith("blob:")) return;
        const item = { url, bandwidth: bandwidth || 0, quality: quality || "", mime: mime || "" };
        if ((mime || "").includes("audio")) out.audio_streams.push(item);
        else out.video_streams.push(item);
    };

    document.querySelectorAll("meta").forEach((m) => {
        const n = m.getAttribute("property") || m.getAttribute("name") || "";
        const c = m.getAttribute("content") || "";
        if (!c) return;
        if (n === "og:title" || n === "twitter:title") out.title = c;
        if (n === "og:description" || n === "description" || n === "twitter:description") {
            out.description = out.description || c;
        }
        if (n === "og:image" || n === "twitter:image") out.cover = out.cover || c;
        if (n.startsWith("og:video") || n === "twitter:player:stream") {
            addStream(c, "og", 0, "");
        }
        if (n === "twitter:player") out.embed_url = c;
    });

    const walkLd = (node) => {
        if (!node || typeof node !== "object") return;
        const types = Array.isArray(node["@type"]) ? node["@type"] : [node["@type"]];
        if (types.includes("VideoObject")) {
            out.title = node.name || out.title;
            out.description = node.description || out.description;
            const thumb = node.thumbnailUrl;
            out.cover = out.cover || (Array.isArray(thumb) ? thumb[0] : thumb) || "";
            if (node.contentUrl) addStream(node.contentUrl, "json-ld", 0, "");
            if (node.embedUrl) out.embed_url = node.embedUrl;
            if (node.uploadDate) out.stat.upload_date = node.uploadDate;
            if (node.author && typeof node.author === "object") {
                out.author.name = node.author.name || out.author.name;
            }
            if (node.interactionStatistic) {
                const stats = Array.isArray(node.interactionStatistic)
                    ? node.interactionStatistic
                    : [node.interactionStatistic];
                stats.forEach((s) => {
                    if (s.interactionType && s.userInteractionCount != null) {
                        const key = String(s.interactionType).toLowerCase();
                        if (key.includes("view")) out.stat.views = s.userInteractionCount;
                        if (key.includes("like")) out.stat.likes = s.userInteractionCount;
                    }
                });
            }
        }
        if (Array.isArray(node)) node.forEach(walkLd);
        else Object.values(node).forEach(walkLd);
    };

    document.querySelectorAll('script[type="application/ld+json"]').forEach((s) => {
        try {
            walkLd(JSON.parse(s.textContent || "{}"));
        } catch (_) {}
    });

    if (platform === "youtube" && window.ytInitialPlayerResponse) {
        const pr = window.ytInitialPlayerResponse;
        const vd = pr.videoDetails || {};
        out.title = vd.title || out.title;
        out.description = vd.shortDescription || out.description;
        const thumbs = vd.thumbnail?.thumbnails || [];
        out.cover = out.cover || (thumbs.length ? thumbs[thumbs.length - 1].url : "");
        out.author.name = vd.author || out.author.name;
        out.video_id = vd.videoId || out.video_id;
        out.stat.views = vd.viewCount || out.stat.views;
        const streams = [
            ...(pr.streamingData?.formats || []),
            ...(pr.streamingData?.adaptiveFormats || []),
        ];
        streams.forEach((f) => {
            if (f.url) addStream(f.url, f.qualityLabel || f.quality || "", f.bitrate || 0, f.mimeType || "");
        });
    }

    if (platform === "vimeo" && window.vimeo) {
        try {
            const clip = window.vimeo.clip_page_config?.clip || {};
            out.title = clip.title || out.title;
            out.description = clip.description || out.description;
            out.cover = out.cover || clip.thumbnail_url || "";
            out.author.name = clip.owner?.name || out.author.name;
            out.video_id = String(clip.id || out.video_id || "");
        } catch (_) {}
    }

    document.querySelectorAll("video, video source").forEach((el) => {
        const u = el.src || el.currentSrc;
        if (u) addStream(u, "dom", 0, el.type || "");
    });

    document.querySelectorAll("iframe").forEach((el) => {
        const s = el.src || "";
        if (s && /video|player|embed|youtube|vimeo|bilibili|tiktok|twitch/i.test(s)) {
            out.embed_url = out.embed_url || s;
        }
    });

    const seen = new Set();
    out.video_streams = out.video_streams.filter((s) => {
        if (!s.url || seen.has(s.url)) return false;
        seen.add(s.url);
        return true;
    });
    out.audio_streams = out.audio_streams.filter((s) => {
        if (!s.url || seen.has(s.url)) return false;
        seen.add(s.url);
        return true;
    });
    out.video_streams.sort((a, b) => (b.bandwidth || 0) - (a.bandwidth || 0));
    out.audio_streams.sort((a, b) => (b.bandwidth || 0) - (a.bandwidth || 0));
    return out;
}
"""


def _host(url: str) -> str:
    return urlparse(url).netloc.lower()


def match_youtube(url: str) -> bool:
    h = _host(url)
    return "youtube.com" in h or h.endswith("youtu.be")


def match_vimeo(url: str) -> bool:
    return "vimeo.com" in _host(url)


def match_tiktok(url: str) -> bool:
    h = _host(url)
    return "tiktok.com" in h or h.endswith("tiktokv.com")


def match_douyin(url: str) -> bool:
    h = _host(url)
    return "douyin.com" in h or h.endswith("iesdouyin.com")


def match_twitter(url: str) -> bool:
    h = _host(url)
    return h.endswith("twitter.com") or h.endswith("x.com")


def match_twitch(url: str) -> bool:
    return "twitch.tv" in _host(url)


def match_dailymotion(url: str) -> bool:
    return "dailymotion.com" in _host(url)


def match_niconico(url: str) -> bool:
    h = _host(url)
    return "nicovideo.jp" in h or "nico.ms" in h


def _detect_from_url(url: str) -> str:
    checks = [
        ("youtube", match_youtube),
        ("vimeo", match_vimeo),
        ("tiktok", match_tiktok),
        ("douyin", match_douyin),
        ("twitter", match_twitter),
        ("twitch", match_twitch),
        ("dailymotion", match_dailymotion),
        ("niconico", match_niconico),
    ]
    for name, fn in checks:
        if fn(url):
            return name
    return "video"


def extract(page: Page, url: str, log: LogFn) -> dict | None:
    platform = _detect_from_url(url)
    payload = page.evaluate(_GENERIC_EXTRACT_JS, platform)
    if not payload:
        log(f"[Video:{platform}] Generic extractor returned nothing.")
        return None

    streams = len(payload.get("video_streams") or []) + len(payload.get("audio_streams") or [])
    log(
        f"[Video:{platform}] Extracted: title={payload.get('title', '')[:40]!r} "
        f"streams={streams} embed={bool(payload.get('embed_url'))}"
    )
    if streams == 0 and not payload.get("title"):
        return None
    return payload
