#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bilibili handler — one platform inside the generic video_platforms package."""

from __future__ import annotations

import hashlib
import json
import re
import time
from functools import reduce
from typing import Callable
from urllib.parse import quote, urlparse

from playwright.sync_api import Page

LogFn = Callable[[str], None]

_BV_RE = re.compile(r"BV[\w]+", re.I)
_MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]


def _get_mixin_key(orig: str) -> str:
    return reduce(lambda s, i: s + orig[i], _MIXIN_KEY_ENC_TAB, "")[:32]


def _strip_wbi_value(value: str) -> str:
    return "".join(c for c in str(value) if c not in "!'()*")


def _sign_wbi(params: dict, img_key: str, sub_key: str) -> dict:
    mixin_key = _get_mixin_key(img_key + sub_key)
    signed = dict(params)
    signed["wts"] = int(time.time())
    query = "&".join(
        f"{quote(k, safe='')}={quote(_strip_wbi_value(v), safe='')}"
        for k, v in sorted(signed.items())
    )
    signed["w_rid"] = hashlib.md5((query + mixin_key).encode()).hexdigest()
    return signed


def _wbi_keys_from_nav(page: Page) -> tuple[str, str]:
    resp = page.context.request.get("https://api.bilibili.com/x/web-interface/nav")
    data = resp.json()
    img_url = data.get("data", {}).get("wbi_img", {}).get("img_url", "")
    sub_url = data.get("data", {}).get("wbi_img", {}).get("sub_url", "")
    img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
    sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
    return img_key, sub_key


def _fetch_comments_wbi(
    page: Page, aid: int, log: LogFn, max_pages: int = 100
) -> list[str]:
    """Fetch paginated comments via WBI-signed reply API."""
    comments: list[str] = []
    seen: set[str] = set()
    try:
        img_key, sub_key = _wbi_keys_from_nav(page)
    except Exception as exc:
        log(f"[Bilibili] WBI nav failed: {exc}")
        return comments

    offset = ""
    referer = page.url or f"https://www.bilibili.com/video/av{aid}"
    headers = {"Referer": referer}

    for page_idx in range(max_pages):
        base = {
            "oid": str(aid),
            "type": "1",
            "mode": "3",
            "pagination_str": json.dumps({"offset": offset}, separators=(",", ":")),
            "plat": "1",
            "web_location": "1315875",
        }
        if page_idx == 0:
            base["seek_rpid"] = ""

        signed = _sign_wbi(base, img_key, sub_key)
        query = "&".join(
            f"{quote(k, safe='')}={quote(_strip_wbi_value(v), safe='')}"
            for k, v in signed.items()
        )
        url = f"https://api.bilibili.com/x/v2/reply/wbi/main?{query}"
        try:
            resp = page.context.request.get(url, headers=headers)
            payload = resp.json()
        except Exception as exc:
            log(f"[Bilibili] Comment page {page_idx + 1} failed: {exc}")
            break

        if payload.get("code") != 0:
            log(f"[Bilibili] Comment API code={payload.get('code')} msg={payload.get('message', '')}")
            break

        data = payload.get("data") or {}
        replies = data.get("replies") or []
        for reply in replies:
            user = (reply.get("member") or {}).get("uname") or "user"
            msg = (reply.get("content") or {}).get("message") or ""
            if msg:
                line = f"{user}: {msg}"
                if line not in seen:
                    seen.add(line)
                    comments.append(line)
            for sub in reply.get("replies") or []:
                su = (sub.get("member") or {}).get("uname") or "user"
                sm = (sub.get("content") or {}).get("message") or ""
                if sm:
                    line = f"  ↳ {su}: {sm}"
                    if line not in seen:
                        seen.add(line)
                        comments.append(line)

        cursor = data.get("cursor") or {}
        if cursor.get("is_end") or not replies:
            break
        next_offset = (cursor.get("pagination_reply") or {}).get("next_offset")
        if not next_offset:
            break
        offset = next_offset

    log(f"[Bilibili] Fetched {len(comments)} comment lines via WBI API.")
    return comments

_EXTRACT_JS = r"""
async (maxPages) => {
    const mixinKeyEncTab = [
        46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
        33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
        61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
        36, 20, 34, 44, 52
    ];

    const getMixinKey = (orig) =>
        mixinKeyEncTab.map((n) => orig[n]).join("").slice(0, 32);

    const stripValue = (v) =>
        String(v).replace(/[!'()*]/g, "");

    const signWbi = async (params) => {
        const navRes = await fetch("https://api.bilibili.com/x/web-interface/nav", {
            credentials: "include",
        });
        const navJson = await navRes.json();
        const imgUrl = navJson.data?.wbi_img?.img_url || "";
        const subUrl = navJson.data?.wbi_img?.sub_url || "";
        const imgKey = imgUrl.slice(imgUrl.lastIndexOf("/") + 1, imgUrl.lastIndexOf("."));
        const subKey = subUrl.slice(subUrl.lastIndexOf("/") + 1, subUrl.lastIndexOf("."));
        const mixinKey = getMixinKey(imgKey + subKey);
        const signed = { ...params, wts: Math.round(Date.now() / 1000) };
        const query = Object.keys(signed)
            .sort()
            .map((k) => `${k}=${stripValue(signed[k])}`)
            .join("&");
        signed.w_rid = await crypto.subtle
            .digest("MD5", new TextEncoder().encode(query + mixinKey))
            .then((buf) =>
                Array.from(new Uint8Array(buf))
                    .map((b) => b.toString(16).padStart(2, "0"))
                    .join("")
            )
            .catch(() => "");
        if (!signed.w_rid) {
            // Fallback for environments without subtle MD5 (use simple hash via fetch proxy)
            const enc = new TextEncoder();
            const data = enc.encode(query + mixinKey);
            let h = 0;
            for (const b of data) h = (h * 31 + b) >>> 0;
            signed.w_rid = h.toString(16).padStart(32, "0");
        }
        return signed;
    };

    const md5 = (text) => {
        // Lightweight MD5 for WBI (browser may lack crypto.subtle MD5)
        function cmn(q, a, b, x, s, t) {
            a = (a + q + x + t) | 0;
            return (((a << s) | (a >>> (32 - s))) + b) | 0;
        }
        function ff(a, b, c, d, x, s, t) {
            return cmn((b & c) | (~b & d), a, b, x, s, t);
        }
        function gg(a, b, c, d, x, s, t) {
            return cmn((b & d) | (c & ~d), a, b, x, s, t);
        }
        function hh(a, b, c, d, x, s, t) {
            return cmn(b ^ c ^ d, a, b, x, s, t);
        }
        function ii(a, b, c, d, x, s, t) {
            return cmn(c ^ (b | ~d), a, b, x, s, t);
        }
        function md5cycle(x, k) {
            let [a, b, c, d] = x;
            a = ff(a, b, c, d, k[0], 7, -680876936);
            d = ff(d, a, b, c, k[1], 12, -389564586);
            c = ff(c, d, a, b, k[2], 17, 606105819);
            b = ff(b, c, d, a, k[3], 22, -1044525330);
            a = ff(a, b, c, d, k[4], 7, -176418897);
            d = ff(d, a, b, c, k[5], 12, 1200080426);
            c = ff(c, d, a, b, k[6], 17, -1473231341);
            b = ff(b, c, d, a, k[7], 22, -45705983);
            a = ff(a, b, c, d, k[8], 7, 1770035416);
            d = ff(d, a, b, c, k[9], 12, -1958414417);
            c = ff(c, d, a, b, k[10], 17, -42063);
            b = ff(b, c, d, a, k[11], 22, -1990404162);
            a = ff(a, b, c, d, k[12], 7, 1804603682);
            d = ff(d, a, b, c, k[13], 12, -40341101);
            c = ff(c, d, a, b, k[14], 17, -1502002290);
            b = ff(b, c, d, a, k[15], 22, 1236535329);
            a = gg(a, b, c, d, k[1], 5, -165796510);
            d = gg(d, a, b, c, k[6], 9, -1069501632);
            c = gg(c, d, a, b, k[11], 14, 643717713);
            b = gg(b, c, d, a, k[0], 20, -373897302);
            a = gg(a, b, c, d, k[5], 5, -701558691);
            d = gg(d, a, b, c, k[10], 9, 38016083);
            c = gg(c, d, a, b, k[15], 14, -660478335);
            b = gg(b, c, d, a, k[4], 20, -405537848);
            a = gg(a, b, c, d, k[9], 5, 568446438);
            d = gg(d, a, b, c, k[14], 9, -1019803690);
            c = gg(c, d, a, b, k[3], 14, -187363961);
            b = gg(b, c, d, a, k[8], 20, 1163531501);
            a = gg(a, b, c, d, k[13], 5, -1444681467);
            d = gg(d, a, b, c, k[2], 9, -51403784);
            c = gg(c, d, a, b, k[7], 14, 1735328473);
            b = gg(b, c, d, a, k[12], 20, -1926607734);
            a = hh(a, b, c, d, k[5], 4, -378558);
            d = hh(d, a, b, c, k[8], 11, -2022574463);
            c = hh(c, d, a, b, k[11], 16, 1839030562);
            b = hh(b, c, d, a, k[14], 23, -35309556);
            a = hh(a, b, c, d, k[1], 4, -1530992060);
            d = hh(d, a, b, c, k[4], 11, 1272893353);
            c = hh(c, d, a, b, k[7], 16, -155497632);
            b = hh(b, c, d, a, k[10], 23, -1094730640);
            a = hh(a, b, c, d, k[13], 4, 681279174);
            d = hh(d, a, b, c, k[0], 11, -358537222);
            c = hh(c, d, a, b, k[3], 16, -722521979);
            b = hh(b, c, d, a, k[6], 23, 76029189);
            a = hh(a, b, c, d, k[9], 4, -640364487);
            d = hh(d, a, b, c, k[12], 11, -421815835);
            c = hh(c, d, a, b, k[15], 16, 530742520);
            b = hh(b, c, d, a, k[2], 23, -995338651);
            a = ii(a, b, c, d, k[0], 6, -198630844);
            d = ii(d, a, b, c, k[7], 10, 1126891415);
            c = ii(c, d, a, b, k[14], 15, -1416354905);
            b = ii(b, c, d, a, k[5], 21, -57434055);
            a = ii(a, b, c, d, k[12], 6, 1700485571);
            d = ii(d, a, b, c, k[3], 10, -1894986606);
            c = ii(c, d, a, b, k[10], 15, -1051523);
            b = ii(b, c, d, a, k[1], 21, -2054922799);
            a = ii(a, b, c, d, k[8], 6, 1873313359);
            d = ii(d, a, b, c, k[15], 10, -30611744);
            c = ii(c, d, a, b, k[6], 15, -1560198380);
            b = ii(b, c, d, a, k[13], 21, 1309151649);
            a = ii(a, b, c, d, k[4], 6, -145523070);
            d = ii(d, a, b, c, k[11], 10, -1120210379);
            c = ii(c, d, a, b, k[2], 15, 718787259);
            b = ii(b, c, d, a, k[9], 21, -343485551);
            x[0] = (a + x[0]) | 0;
            x[1] = (b + x[1]) | 0;
            x[2] = (c + x[2]) | 0;
            x[3] = (d + x[3]) | 0;
        }
        function md51(s) {
            const n = s.length;
            const state = [1732584193, -271733879, -1732584194, 271733878];
            let i;
            for (i = 64; i <= n; i += 64) {
                md5cycle(state, md5blk(s.substring(i - 64, i)));
            }
            s = s.substring(i - 64);
            const tail = new Array(16).fill(0);
            for (i = 0; i < s.length; i++) tail[i >> 2] |= s.charCodeAt(i) << ((i % 4) << 3);
            tail[i >> 2] |= 0x80 << ((i % 4) << 3);
            if (i > 55) {
                md5cycle(state, tail);
                tail.fill(0);
            }
            tail[14] = n * 8;
            md5cycle(state, tail);
            return state;
        }
        function md5blk(s) {
            const md5blks = [];
            for (let i = 0; i < 64; i += 4) {
                md5blks[i >> 2] =
                    s.charCodeAt(i) +
                    (s.charCodeAt(i + 1) << 8) +
                    (s.charCodeAt(i + 2) << 16) +
                    (s.charCodeAt(i + 3) << 24);
            }
            return md5blks;
        }
        function rhex(n) {
            const hex = "0123456789abcdef";
            let s = "";
            for (let j = 0; j < 4; j++) {
                s += hex.charAt((n >> (j * 8 + 4)) & 0x0f) + hex.charAt((n >> (j * 8)) & 0x0f);
            }
            return s;
        }
        return md51(text).map(rhex).join("");
    };

    const signWbiParams = async (params) => {
        const navRes = await fetch("https://api.bilibili.com/x/web-interface/nav", {
            credentials: "include",
        });
        const navJson = await navRes.json();
        const imgUrl = navJson.data?.wbi_img?.img_url || "";
        const subUrl = navJson.data?.wbi_img?.sub_url || "";
        const imgKey = imgUrl.slice(imgUrl.lastIndexOf("/") + 1, imgUrl.lastIndexOf("."));
        const subKey = subUrl.slice(subUrl.lastIndexOf("/") + 1, subUrl.lastIndexOf("."));
        const mixinKey = getMixinKey(imgKey + subKey);
        const signed = { ...params, wts: Math.round(Date.now() / 1000) };
        const query = Object.keys(signed)
            .sort()
            .map((k) => `${k}=${stripValue(signed[k])}`)
            .join("&");
        signed.w_rid = md5(query + mixinKey);
        return signed;
    };

    const state = window.__INITIAL_STATE__;
    if (!state) return null;

    const resolveVideoData = (s) => {
        if (s.videoData) return s.videoData;
        if (s.video && s.video.videoData) return s.video.videoData;
        if (s.videoInfo) return s.videoInfo;
        return null;
    };

    let v = resolveVideoData(state);
    if (!v) {
        const bvid =
            state.bvid || (location.pathname.match(/BV[\w]+/i) || [])[0] || "";
        if (bvid) {
            try {
                const signed = await signWbiParams({ bvid });
                const qs = new URLSearchParams(signed).toString();
                const res = await fetch(
                    "https://api.bilibili.com/x/web-interface/view?" + qs,
                    { credentials: "include" }
                );
                const json = await res.json();
                if (json.code === 0 && json.data) {
                    const d = json.data;
                    v = {
                        bvid: d.bvid || bvid,
                        aid: d.aid,
                        cid: d.cid,
                        title: d.title || "",
                        desc: d.desc || "",
                        owner: d.owner || {},
                        stat: d.stat || {},
                        duration: d.duration,
                        pubdate: d.pubdate,
                        tname: d.tname || "",
                        tag: (d.tag || []).map((t) => ({
                            tag_name: t.tag_name || t,
                        })),
                        pages: d.pages || [],
                        pic: d.pic || "",
                    };
                }
            } catch (_) {}
        }
    }
    if (!v) return null;

    const aid = v.aid || state.aid;
    const cid = v.cid || (v.pages && v.pages[0] && v.pages[0].cid) || state.cid;

    const out = {
        bvid: v.bvid || "",
        aid,
        cid,
        title: v.title || "",
        description: v.desc || v.description || "",
        owner: v.owner
            ? {
                  mid: v.owner.mid,
                  name: v.owner.name,
                  face: v.owner.face || "",
              }
            : {},
        stat: v.stat || {},
        duration: v.duration,
        pubdate: v.pubdate,
        tname: v.tname || "",
        tags: (v.tag || []).map((t) => t.tag_name || t).filter(Boolean),
        pages: (v.pages || []).map((p) => ({
            cid: p.cid,
            page: p.page,
            part: p.part,
            duration: p.duration,
            first_frame: p.first_frame || "",
        })),
        cover: v.pic || "",
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
            (dash.video || []).forEach((track) => {
                const url = track.baseUrl || track.base_url;
                if (url) {
                    out.video_streams.push({
                        id: track.id,
                        bandwidth: track.bandwidth,
                        width: track.width,
                        height: track.height,
                        codecs: track.codecs || "",
                        url,
                    });
                }
            });
            (dash.audio || []).forEach((track) => {
                const url = track.baseUrl || track.base_url;
                if (url) {
                    out.audio_streams.push({
                        id: track.id,
                        bandwidth: track.bandwidth,
                        codecs: track.codecs || "",
                        url,
                    });
                }
            });
            (data.durl || []).forEach((part, idx) => {
                if (part.url) {
                    out.video_streams.push({
                        id: "durl-" + idx,
                        bandwidth: part.size || 0,
                        url: part.url,
                    });
                }
            });
        }
    } catch (_) {}

    const commentTexts = new Set();

    const addReplies = (replies) => {
        (replies || []).forEach((r) => {
            const user = (r.member && r.member.uname) || "user";
            const msg = (r.content && r.content.message) || "";
            if (msg) commentTexts.add(user + ": " + msg);
            (r.replies || []).forEach((sub) => {
                const su = (sub.member && sub.member.uname) || "user";
                const sm = (sub.content && sub.content.message) || "";
                if (sm) commentTexts.add("  ↳ " + su + ": " + sm);
            });
        });
    };

    const fetchComments = async () => {
        if (!aid) return;
        let offset = "";
        for (let page = 0; page < maxPages; page++) {
            try {
                const base = {
                    oid: aid,
                    type: 1,
                    mode: 3,
                    pagination_str: JSON.stringify({ offset }),
                    plat: 1,
                    web_location: "1315875",
                };
                if (page === 0) base.seek_rpid = "";
                const signed = await signWbiParams(base);
                const qs = Object.keys(signed)
                    .sort()
                    .map((k) => encodeURIComponent(k) + "=" + encodeURIComponent(String(signed[k])))
                    .join("&");
                const res = await fetch(
                    "https://api.bilibili.com/x/v2/reply/wbi/main?" + qs,
                    { credentials: "include" }
                );
                const json = await res.json();
                if (json.code !== 0 || !json.data) break;
                const replies = json.data.replies || [];
                addReplies(replies);
                const cursor = json.data.cursor || {};
                if (cursor.is_end || !replies.length) break;
                const next = cursor.pagination_reply && cursor.pagination_reply.next_offset;
                if (!next) break;
                offset = next;
            } catch (_) {
                break;
            }
        }
    };

    await fetchComments();

    const domSelectors = [
        ".reply-item .root-reply",
        ".bili-comment-item .bili-rich-text__content",
        ".list-item .text-con",
        ".reply-content",
    ];
    domSelectors.forEach((sel) => {
        document.querySelectorAll(sel).forEach((el) => {
            const t = (el.innerText || "").trim();
            if (t.length > 2 && t.length < 2000) commentTexts.add(t);
        });
    });

    out.comments = [...commentTexts];
    out.video_streams.sort((a, b) => (b.bandwidth || 0) - (a.bandwidth || 0));
    out.audio_streams.sort((a, b) => (b.bandwidth || 0) - (a.bandwidth || 0));
    return out;
}
"""


def match_url(url: str) -> bool:
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


def extract(page: Page, url: str, log: LogFn, max_comment_pages: int = 100) -> dict | None:
    """Extract metadata, streams, and comments from a Bilibili video page."""
    title = page.title() or ""
    html_lower = (page.content() or "").lower()
    if "验证码" in title or "geetest" in html_lower or "verifycenter" in html_lower:
        log("[Bilibili] Captcha/verification page detected — add Cookie and use Visible browser.")
        return None

    _prepare_bilibili_page(page)
    payload = page.evaluate(_EXTRACT_JS, max_comment_pages)

    if not payload:
        log("[Bilibili] No video metadata found (__INITIAL_STATE__ or view API).")
        return None

    aid = payload.get("aid")
    if aid:
        api_comments = _fetch_comments_wbi(page, int(aid), log, max_comment_pages)
        if api_comments:
            payload["comments"] = api_comments

    log(
        f"[Video:bilibili] Extracted: title={payload.get('title', '')[:40]!r} ... "
        f"streams={len(payload.get('video_streams', []))} "
        f"comments={len(payload.get('comments', []))} "
        f"(API total ~{payload.get('comment_total', 0)})"
    )
    payload["platform"] = "bilibili"
    return payload
