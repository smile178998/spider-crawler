#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Core scraping pipeline — shared by GUI and web app."""

import random
import queue
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

try:
    from playwright_stealth import Stealth
    _stealth = Stealth()
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

COMMENT_HINTS = [
    "comment", "comments", "reply", "replies", "discuss",
    "review", "feedback", "danmu",
]
VIDEO_EXTS = (".mp4", ".m3u8", ".flv", ".webm", ".mov", ".avi")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg")

COMMON_CONTENT_SELECTORS = [
    "#cnblogs_post_body",
    ".postBody", ".post_body",
    "#article_content", ".article-content", ".article__content",
    ".entry-content", ".post-content", ".post-body",
    "#js_content",
    ".markdown-body",
    "#content_views",
    ".content-detail", ".detail-content",
    "article", "main",
]

SIDEBAR_HINTS = [
    "sidebar", "side-bar", "aside", "nav", "menu", "footer", "header",
    "recommend", "related", "hot", "rank", "paihang", "tuijian",
    "widget", "banner", "advert", "ad-", "breadcrumb", "toc",
    "share", "social", "tag-list", "catalog",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

VIEWPORTS = [
    {"width": 1280, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
]

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
window.chrome = window.chrome || { runtime: {} };
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters)
);
"""


def _is_sidebar(tag) -> bool:
    cls = " ".join(tag.get("class") or []) + " " + (tag.get("id") or "")
    cls = cls.lower()
    return any(h in cls for h in SIDEBAR_HINTS)


def browser_fetch(url: str, wait_ms: int, cookie: str,
                  scroll: bool, log_q: queue.Queue) -> dict:
    def log(msg: str):
        log_q.put(("log", msg))

    log("[Browser] Launching Chromium …")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )

        ua = random.choice(USER_AGENTS)
        viewport = random.choice(VIEWPORTS)

        ctx = browser.new_context(
            user_agent=ua,
            viewport=viewport,
            locale="en-US",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )

        if HAS_STEALTH:
            log("[Browser] Applying playwright-stealth patches …")
        else:
            log("[Browser] playwright-stealth not installed — using built-in "
                "fallback patches (pip install playwright-stealth for more).")
        ctx.add_init_script(STEALTH_JS)

        if cookie.strip():
            parsed = urlparse(url)
            domain = parsed.netloc
            cookies = []
            for part in cookie.split(";"):
                part = part.strip()
                if "=" in part:
                    name, _, val = part.partition("=")
                    cookies.append({
                        "name": name.strip(),
                        "value": val.strip(),
                        "domain": domain,
                        "path": "/",
                    })
            if cookies:
                ctx.add_cookies(cookies)
                log(f"[Browser] Injected {len(cookies)} cookie(s).")

        page = ctx.new_page()
        if HAS_STEALTH:
            _stealth.apply_stealth_sync(page)

        log(f"[Browser] Navigating to {url} …")
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)

        if scroll:
            log("[Browser] Scrolling page to trigger lazy-loaded content …")
            for _ in range(4):
                page.evaluate("window.scrollBy(0, document.body.scrollHeight / 4)")
                page.wait_for_timeout(random.randint(350, 750))
            page.evaluate("window.scrollTo(0, 0)")

        jittered_wait = max(200, int(wait_ms * random.uniform(0.85, 1.15)))
        log(f"[Browser] Waiting ~{jittered_wait} ms for JavaScript to settle …")
        page.wait_for_timeout(jittered_wait)

        html = page.content()
        title = page.title()
        inner = page.evaluate("document.body.innerText")

        video_urls = list(page.evaluate("""
            () => {
                const vids = [];
                document.querySelectorAll('video, video source').forEach(el => {
                    if (el.src) vids.push(el.src);
                    if (el.currentSrc) vids.push(el.currentSrc);
                });
                document.querySelectorAll('iframe').forEach(el => {
                    const s = el.src || '';
                    if (s && (s.includes('video') || s.includes('player') ||
                              s.includes('embed') || s.includes('youtube') ||
                              s.includes('bilibili') || s.includes('vimeo'))) {
                        vids.push(s);
                    }
                });
                return [...new Set(vids.filter(Boolean))];
            }
        """))

        browser.close()
        log(f"[Browser] Done. Title: {title!r}")

    return {
        "html": html,
        "inner_text": inner,
        "title": title,
        "url": url,
        "video_urls_from_dom": video_urls,
    }


def parse_content(data: dict, text_sel: str, comment_sel: str) -> dict:
    soup = BeautifulSoup(data["html"], "lxml")
    base = data["url"]
    title = data["title"] or _bs_title(soup)

    paragraphs = _extract_text(soup, text_sel)
    comments = _extract_comments(soup, comment_sel)

    videos = list(data["video_urls_from_dom"])
    for a in soup.find_all("a", href=True):
        if a["href"].lower().endswith(VIDEO_EXTS):
            videos.append(urljoin(base, a["href"]))
    videos = _dedup(videos)

    images = []
    for img in soup.find_all("img", src=True):
        src = urljoin(base, img["src"])
        if src not in images:
            images.append(src)
    images = images[:50]

    meta = {}
    for tag in soup.find_all("meta"):
        name = tag.get("name") or tag.get("property") or ""
        content = tag.get("content", "")
        if name and content:
            meta[name] = content

    return {
        "url": base,
        "title": title,
        "text_paragraphs": paragraphs,
        "comments": comments,
        "videos": videos,
        "images": images,
        "meta": meta,
    }


def _bs_title(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    return h1.get_text(strip=True) if h1 else "(no title)"


def _extract_text(soup: BeautifulSoup, sel: str) -> list:
    if sel:
        nodes = soup.select(sel)
        result = [n.get_text(strip=True, separator=" ") for n in nodes if n.get_text(strip=True)]
        if result:
            return result

    container = None
    for css in COMMON_CONTENT_SELECTORS:
        node = soup.select_one(css)
        if node and len(node.get_text(strip=True)) > 200:
            container = node
            break
    if container is None:
        container = soup.find("article") or soup

    paras = [p.get_text(strip=True, separator=" ")
             for p in container.find_all(["p", "h2", "h3", "h4", "h5",
                                           "li", "pre", "code", "blockquote"])
             if len(p.get_text(strip=True)) > 1 and not _is_sidebar(p)]

    if len(paras) < 3:
        seen, paras = set(), []
        for div in container.find_all("div"):
            if _is_sidebar(div):
                continue
            t = div.get_text(strip=True, separator=" ")
            if len(t) > 50 and t not in seen:
                seen.add(t)
                paras.append(t)
        paras = paras[:60]

    return paras


def _extract_comments(soup: BeautifulSoup, sel: str) -> list:
    if sel:
        return [n.get_text(strip=True, separator=" ")
                for n in soup.select(sel) if n.get_text(strip=True)]

    seen, results = set(), []
    for tag in soup.find_all(["div", "li", "section"]):
        if _is_sidebar(tag):
            continue
        cls = " ".join(tag.get("class") or []) + " " + (tag.get("id") or "")
        if any(h in cls.lower() for h in COMMENT_HINTS):
            txt = tag.get_text(strip=True, separator=" ")
            if txt and 5 < len(txt) < 2000 and txt not in seen:
                seen.add(txt)
                results.append(txt)
    return results[:200]


def _dedup(lst: list) -> list:
    seen, out = set(), []
    for x in lst:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def run_pipeline(url: str, text_sel: str, comment_sel: str,
                 cookie: str, wait_ms: int, scroll: bool,
                 log_q: queue.Queue):
    try:
        raw = browser_fetch(url, wait_ms, cookie, scroll, log_q)
        result = parse_content(raw, text_sel, comment_sel)
        log_q.put(("done", result))
    except Exception as exc:
        log_q.put(("error", str(exc)))
