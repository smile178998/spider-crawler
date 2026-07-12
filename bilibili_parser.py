#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bilibili-specific extraction via in-page state and APIs."""

from __future__ import annotations

import re
from typing import Callable
from urllib.parse import urlparse

from playwright.sync_api import Page

from image_utils import collect_images

LogFn = Callable[[str], None]

_BV_RE = re.compile(r"BV[\w]+", re.I)


def is_bilibili_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return "bilibili.com" in host or host.endswith("b23.tv")


def _prepare_bilibili_page(page: Page) -> None:
    """Scroll to load comments and related lazy content."""
    try:
        page.evaluate(
            "window.scrollTo(0, Math.max(document.body.scrollHeight, "
            "document.documentElement.scrollHeight) * 0.55)"
        )
        page.wait_for_timeout(1200)
        page.evaluate(
            "window.scrollTo(0, Math.max(document.body.scrollHeight, "
            "document.documentElement.scrollHeight))"
        )
        page.wait_for_timeout(2000)
    except Exception:
        pass


def extract_bilibili(page: Page, log: LogFn, max_comment_pages: int = 10) -> dict | None:
    """Extract metadata, streams, and comments from a Bilibili video page."""
    _prepare_bilibili_page(page)
    payload = page.evaluate(
        """async (maxPages) => {
            const state = window.__INITIAL_STATE__;
            if (!state || !state.videoData) return null;

            const v = state.videoData;
            const aid = v.aid;
            const cid = v.cid;

            const out = {
                bvid: v.bvid || '',
                aid,
                cid,
                title: v.title || '',
                description: v.desc || '',
                owner: v.owner ? {
                    mid: v.owner.mid,
                    name: v.owner.name,
                    face: v.owner.face || '',
                } : {},
                stat: v.stat || {},
                duration: v.duration,
                pubdate: v.pubdate,
                tname: v.tname || '',
                tags: (v.tag || []).map(t => t.tag_name).filter(Boolean),
                pages: (v.pages || []).map(p => ({
                    cid: p.cid,
                    page: p.page,
                    part: p.part,
                    duration: p.duration,
                    first_frame: p.first_frame || '',
                })),
                cover: v.pic || '',
                video_streams: [],
                audio_streams: [],
                comments: [],
                comment_total: (v.stat && v.stat.reply) || 0,
                danmaku_count: (v.stat && v.stat.danmaku) || 0,
            };

            try {
                const playinfo = window.__playinfo__;
                if (playinfo) {
                    const data = playinfo.data || playinfo;
                    const dash = data.dash || {};
                    (dash.video || []).forEach(track => {
                        const url = track.baseUrl || track.base_url;
                        if (url) {
                            out.video_streams.push({
                                id: track.id,
                                bandwidth: track.bandwidth,
                                width: track.width,
                                height: track.height,
                                codecs: track.codecs || '',
                                url,
                            });
                        }
                    });
                    (dash.audio || []).forEach(track => {
                        const url = track.baseUrl || track.base_url;
                        if (url) {
                            out.audio_streams.push({
                                id: track.id,
                                bandwidth: track.bandwidth,
                                codecs: track.codecs || '',
                                url,
                            });
                        }
                    });
                    (data.durl || []).forEach((part, idx) => {
                        if (part.url) {
                            out.video_streams.push({
                                id: 'durl-' + idx,
                                bandwidth: part.size || 0,
                                url: part.url,
                            });
                        }
                    });
                }
            } catch (_) {}

            const commentTexts = new Set();

            try {
                for (const sort of [2, 0]) {
                    for (let pn = 1; pn <= maxPages; pn++) {
                        const u = 'https://api.bilibili.com/x/v2/reply?type=1&oid=' + aid
                            + '&sort=' + sort + '&pn=' + pn + '&ps=20';
                        const res = await fetch(u, { credentials: 'include' });
                        const json = await res.json();
                        if (json.code !== 0) continue;
                        const replies = (json.data && json.data.replies) || [];
                        if (!replies.length) break;
                        replies.forEach(r => {
                            const user = (r.member && r.member.uname) || 'user';
                            const msg = (r.content && r.content.message) || '';
                            if (msg) commentTexts.add(user + ': ' + msg);
                            (r.replies || []).forEach(sub => {
                                const su = (sub.member && sub.member.uname) || 'user';
                                const sm = (sub.content && sub.content.message) || '';
                                if (sm) commentTexts.add('  ↳ ' + su + ': ' + sm);
                            });
                        });
                    }
                }
            } catch (_) {}

            const domSelectors = [
                '.reply-item .root-reply',
                '.bili-comment-item .bili-rich-text__content',
                '.list-item .text-con',
                '.reply-content',
            ];
            domSelectors.forEach(sel => {
                document.querySelectorAll(sel).forEach(el => {
                    const t = (el.innerText || '').trim();
                    if (t.length > 2 && t.length < 2000) commentTexts.add(t);
                });
            });

            out.comments = [...commentTexts];
            out.video_streams.sort((a, b) => (b.bandwidth || 0) - (a.bandwidth || 0));
            out.audio_streams.sort((a, b) => (b.bandwidth || 0) - (a.bandwidth || 0));
            return out;
        }""",
        max_comment_pages,
    )

    if not payload:
        log("[Bilibili] No __INITIAL_STATE__.videoData found on page.")
        return None

    log(
        f"[Bilibili] Extracted: title={payload.get('title', '')[:40]!r} ... "
        f"streams={len(payload.get('video_streams', []))} "
        f"comments={len(payload.get('comments', []))} "
        f"(API total ~{payload.get('comment_total', 0)})"
    )
    return payload


def merge_bilibili_result(result: dict, bili: dict) -> dict:
    """Merge Bilibili payload into the standard scrape result."""
    result["platform"] = "bilibili"
    result["title"] = bili.get("title") or result.get("title", "")

    desc = (bili.get("description") or "").strip()
    if desc:
        paragraphs = [p.strip() for p in re.split(r"\n+", desc) if p.strip()]
        result["text_paragraphs"] = paragraphs or [desc]

    owner = bili.get("owner") or {}
    if owner.get("name"):
        result["text_paragraphs"] = [
            f"UP主: {owner['name']}",
            *[p for p in result.get("text_paragraphs", []) if not p.startswith("UP主:")],
        ]

    stat = bili.get("stat") or {}
    if stat:
        stat_line = (
            f"播放 {stat.get('view', 0):,} · 点赞 {stat.get('like', 0):,} · "
            f"投币 {stat.get('coin', 0):,} · 收藏 {stat.get('favorite', 0):,} · "
            f"弹幕 {stat.get('danmaku', 0):,} · 评论 {stat.get('reply', 0):,}"
        )
        result["text_paragraphs"] = [stat_line] + result.get("text_paragraphs", [])

    if bili.get("comments"):
        result["comments"] = bili["comments"]

    stream_urls = []
    for stream in bili.get("video_streams") or []:
        url = stream.get("url")
        if url and url not in stream_urls:
            stream_urls.append(url)
    for stream in bili.get("audio_streams") or []:
        url = stream.get("url")
        if url and url not in stream_urls:
            stream_urls.append(url)

    existing = result.get("videos") or []
    result["videos"] = list(dict.fromkeys(stream_urls + existing))

    curated: list[str] = []
    cover = bili.get("cover")
    if cover:
        curated.append(cover)
    owner = bili.get("owner") or {}
    if owner.get("face"):
        curated.append(owner["face"])
    for pg in bili.get("pages") or []:
        frame = pg.get("first_frame")
        if frame:
            curated.append(frame)

  # Bilibili pages embed many recommendation thumbnails in HTML — keep only real assets.
    result["images"] = collect_images(curated, limit=20)

    meta = dict(result.get("meta") or {})
    meta.update({
        "bilibili_bvid": bili.get("bvid", ""),
        "bilibili_aid": str(bili.get("aid", "")),
        "bilibili_cid": str(bili.get("cid", "")),
        "bilibili_owner": owner.get("name", ""),
        "bilibili_tags": ", ".join(bili.get("tags") or []),
    })
    result["meta"] = meta
    result["bilibili"] = bili
    return result
