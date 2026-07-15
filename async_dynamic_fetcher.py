#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Async dynamic page loader via Playwright — Chromium or system Google Chrome.

Async twin of :class:`dynamic_fetcher.DynamicSession` /
:class:`dynamic_fetcher.DynamicFetcher`. Use when the page needs a real
browser under ``asyncio``.

Example::

    import asyncio
    from async_dynamic_fetcher import AsyncDynamicFetcher, AsyncDynamicSession

    async def main() -> None:
        r = await AsyncDynamicFetcher.fetch(
            "https://spa.example.com",
            real_chrome=True,
            network_idle=True,
            wait=1500,
        )
        print(r.title, r.status_code, len(r.text))

        async with AsyncDynamicSession(session_file=".sessions/dyn.json") as s:
            await s.fetch("https://example.com/login")
            s.state["step"] = "logged_in"
            await s.fetch("https://example.com/dashboard")
            await s.save()

    asyncio.run(main())
"""

from __future__ import annotations

import asyncio
import inspect
import time
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Union
from urllib.parse import urlparse

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Response as PWResponse,
    async_playwright,
)

from fetcher import FetchError
from scraper_core import (
    BROWSER_ARGS,
    _build_headers,
    _stealth_init_script,
)

from dynamic_fetcher import (
    CookieInput,
    DEFAULT_TIMEOUT_MS,
    DEFAULT_WAIT_MS,
    DynamicFetchResult,
    PageAction,
    ProxyInput,
    _SessionOptions,
    _as_bool_chrome,
    _inject_cookies,  # noqa: F401 — re-exported for parity / callers
    _normalize_proxy,
    _overrides_to_opts,
    _pick_profile,
    field_replace,
)

try:
    from playwright_stealth import Stealth

    _stealth = Stealth()
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _apply_request_blocking_async(
    page: Page,
    *,
    disable_resources: bool = False,
    blocked_domains: Optional[Sequence[str]] = None,
    block_ads: bool = False,
) -> bool:
    """Async port of :func:`request_blocking.apply_request_blocking`."""
    from request_blocking import (
        HEAVY_RESOURCES,
        is_domain_blocked,
        merge_blocked_domains,
    )

    heavy = HEAVY_RESOURCES if disable_resources else frozenset()
    domains = merge_blocked_domains(blocked_domains, block_ads=block_ads)
    if not heavy and not domains:
        return False

    async def handler(route: Any) -> None:
        try:
            req = route.request
            rtype = req.resource_type
            if rtype in heavy:
                await route.abort()
                return
            if domains:
                hostname = urlparse(req.url).hostname or ""
                if is_domain_blocked(hostname, domains):
                    await route.abort()
                    return
            await route.continue_()
        except Exception:
            try:
                await route.continue_()
            except Exception:
                pass

    await page.route("**/*", handler)
    return True


class AsyncDynamicSession:
    """Reusable async Playwright session with persistent cookies / storage.

    One browser context is shared for the lifetime of the session, so login
    cookies, ``localStorage`` (same origin), and custom ``state`` survive
    multiple ``fetch()`` calls.

    Example::

        async with AsyncDynamicSession(
            real_chrome=True, session_file=".sessions/dyn.json"
        ) as s:
            await s.fetch("https://example.com/login")
            s.state["step"] = "logged_in"
            await s.fetch("https://example.com/dashboard")
            await s.save()
    """

    def __init__(self, **kwargs: Any) -> None:
        session_file = kwargs.pop("session_file", None)
        state = kwargs.pop("state", None)
        proxy_rotator = kwargs.pop("proxy_rotator", None)
        real_chrome = _as_bool_chrome(kwargs)
        self.opts = _SessionOptions(
            headless=bool(kwargs.pop("headless", True)),
            real_chrome=real_chrome,
            disable_resources=bool(kwargs.pop("disable_resources", False)),
            blocked_domains=kwargs.pop("blocked_domains", None),
            block_ads=bool(kwargs.pop("block_ads", False)),
            network_idle=bool(kwargs.pop("network_idle", False)),
            load_dom=bool(kwargs.pop("load_dom", True)),
            timeout=int(kwargs.pop("timeout", DEFAULT_TIMEOUT_MS)),
            wait=int(kwargs.pop("wait", DEFAULT_WAIT_MS)),
            wait_selector=kwargs.pop("wait_selector", None),
            wait_selector_state=str(kwargs.pop("wait_selector_state", "attached")),
            useragent=kwargs.pop("useragent", None),
            cookies=kwargs.pop("cookies", None),
            locale=kwargs.pop("locale", None),
            proxy=kwargs.pop("proxy", None),
            google_search=bool(kwargs.pop("google_search", True)),
            extra_headers=kwargs.pop("extra_headers", None),
            extra_flags=kwargs.pop("extra_flags", None),
            init_script=kwargs.pop("init_script", None),
            page_action=kwargs.pop("page_action", None),
            page_setup=kwargs.pop("page_setup", None),
            cdp_url=kwargs.pop("cdp_url", None),
            additional_args=kwargs.pop("additional_args", None),
            simulate_stealth=bool(kwargs.pop("simulate_stealth", True)),
            viewport=kwargs.pop("viewport", None),
            dns_over_https=bool(kwargs.pop("dns_over_https", False)),
        )
        kwargs.pop("selector_config", None)
        kwargs.pop("custom_config", None)
        if kwargs:
            extra = dict(self.opts.additional_args or {})
            extra.update(kwargs)
            self.opts.additional_args = extra

        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._owns_browser = False
        self._browser_engine = ""
        self._entered = False
        self._cookies_seeded = False
        self.state: dict[str, Any] = dict(state or {})
        self._session_file = Path(session_file) if session_file else None
        self._proxy_rotator = proxy_rotator
        self.last_proxy: Optional[str] = None

        if self._proxy_rotator is not None and self.opts.proxy:
            raise ValueError(
                "Cannot use proxy_rotator together with a static proxy. "
                "Pass one or the other (per-request proxy= still overrides)."
            )

        if self._session_file and self._session_file.is_file():
            from session_store import load_session_file

            data = load_session_file(self._session_file)
            self.state.update(dict(data.get("state") or {}))
            if data.get("cookies") and not self.opts.cookies:
                self.opts.cookies = data["cookies"]

    async def __aenter__(self) -> "AsyncDynamicSession":
        if self._entered:
            raise RuntimeError("AsyncDynamicSession already entered")
        self._pw = await async_playwright().start()
        self._browser, self._browser_engine = await self._launch(self._pw)
        self._context = await self._new_context(self._browser, "https://example.com")
        self._owns_browser = True
        self._entered = True
        if self.opts.cookies:
            await self.set_cookies(self.opts.cookies)
            self._cookies_seeded = True
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._session_file:
            try:
                await self.save()
            except Exception:
                pass
        await self.close()

    async def close(self) -> None:
        if self._context is not None:
            try:
                await self._context.close()
            except Exception:
                pass
        self._context = None
        if self._browser is not None and self._owns_browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        self._browser = None
        if self._pw is not None:
            try:
                await self._pw.stop()
            except Exception:
                pass
        self._pw = None
        self._entered = False

    async def _launch(self, pw: Playwright) -> tuple[Browser, str]:
        opts = self.opts
        if opts.cdp_url:
            browser = await pw.chromium.connect_over_cdp(opts.cdp_url)
            return browser, "cdp"

        from doh import apply_chromium_doh

        args = apply_chromium_doh(list(BROWSER_ARGS), opts.dns_over_https)
        if opts.extra_flags:
            args.extend(str(f) for f in opts.extra_flags)

        launch_kwargs: dict[str, Any] = {
            "headless": opts.headless,
            "args": args,
        }
        # Static session proxy only — rotator / per-request handled at context level.
        if self._proxy_rotator is None:
            proxy = _normalize_proxy(opts.proxy)
            if proxy:
                launch_kwargs["proxy"] = proxy

        errors: list[str] = []

        async def try_chrome() -> Optional[Browser]:
            try:
                return await pw.chromium.launch(channel="chrome", **launch_kwargs)
            except Exception as exc:
                errors.append(f"chrome: {exc}")
                return None

        async def try_chromium() -> Optional[Browser]:
            try:
                return await pw.chromium.launch(**launch_kwargs)
            except Exception as exc:
                errors.append(f"chromium: {exc}")
                return None

        if opts.real_chrome:
            browser = await try_chrome()
            if browser is not None:
                return browser, "chrome"
            browser = await try_chromium()
            if browser is not None:
                return browser, "chromium"
        else:
            browser = await try_chromium()
            if browser is not None:
                return browser, "chromium"
            browser = await try_chrome()
            if browser is not None:
                return browser, "chrome"

        hint = (
            "Install system Google Chrome, or run: python -m playwright install chromium"
        )
        detail = " | ".join(errors) if errors else "unknown launch error"
        raise FetchError(f"Unable to launch browser ({detail}). {hint}")

    def _pick_fetch_proxy(self, overrides: dict[str, Any]) -> Optional[dict]:
        from proxy_rotator import normalize_proxy, proxy_to_url, resolve_request_proxy

        if "proxy" in overrides:
            chosen = overrides.pop("proxy")
        else:
            chosen = resolve_request_proxy(
                request_proxy=None,
                proxy_rotator=self._proxy_rotator,
                session_proxy=self.opts.proxy if self._proxy_rotator is None else None,
            )
        parsed = normalize_proxy(chosen) if chosen not in (None, "") else None
        self.last_proxy = proxy_to_url(parsed) if parsed else None
        return parsed

    async def _context_for_proxy(
        self, proxy: Optional[dict], url: str
    ) -> tuple[BrowserContext, bool]:
        """Return ``(context, ephemeral)``. Ephemeral = per-request proxied context."""
        assert self._browser is not None
        assert self._context is not None
        # Use shared context when no per-request proxy from rotator/override
        if proxy is None or self._proxy_rotator is None and "proxy" not in getattr(
            self, "_pending_proxy_override", {}
        ):
            if proxy is None:
                return self._context, False
            # Static proxy was already applied at browser launch
            if self._proxy_rotator is None and self.opts.proxy:
                return self._context, False

        if proxy is None:
            return self._context, False

        profile = _pick_profile(
            self.opts.useragent, self.opts.locale, self.opts.viewport
        )
        viewport = profile["viewport"]
        headers = _build_headers(
            profile["ua"], url, profile["languages"], profile["platform"]
        )
        if self.opts.google_search:
            headers["Referer"] = "https://www.google.com/"
        if self.opts.extra_headers:
            headers.update({str(k): str(v) for k, v in self.opts.extra_headers.items()})

        ctx_kwargs: dict[str, Any] = {
            "user_agent": profile["ua"],
            "viewport": {"width": viewport["width"], "height": viewport["height"]},
            "locale": profile["locale"],
            "timezone_id": profile["timezone"],
            "ignore_https_errors": True,
            "extra_http_headers": headers,
            "proxy": proxy,
        }
        if self.opts.additional_args:
            ctx_kwargs.update(dict(self.opts.additional_args))
        ctx = await self._browser.new_context(**ctx_kwargs)
        if self.opts.simulate_stealth:
            await ctx.add_init_script(
                _stealth_init_script(profile["languages"], profile["navigator_platform"])
            )
        existing = await self.get_cookies()
        if existing:
            try:
                await ctx.add_cookies(existing)
            except Exception:
                pass
        return ctx, True

    async def _new_context(self, browser: Browser, url: str) -> BrowserContext:
        opts = self.opts
        profile = _pick_profile(opts.useragent, opts.locale, opts.viewport)
        viewport = profile["viewport"]
        headers = _build_headers(
            profile["ua"], url, profile["languages"], profile["platform"]
        )
        if opts.google_search and "Referer" not in (opts.extra_headers or {}):
            headers["Referer"] = "https://www.google.com/"
        if opts.extra_headers:
            headers.update({str(k): str(v) for k, v in opts.extra_headers.items()})

        ctx_kwargs: dict[str, Any] = {
            "user_agent": profile["ua"],
            "viewport": {"width": viewport["width"], "height": viewport["height"]},
            "screen": {"width": viewport["width"], "height": viewport["height"]},
            "locale": profile["locale"],
            "timezone_id": profile["timezone"],
            "color_scheme": "light",
            "java_script_enabled": True,
            "ignore_https_errors": True,
            "extra_http_headers": headers,
        }
        if opts.additional_args:
            ctx_kwargs.update(dict(opts.additional_args))

        ctx = await browser.new_context(**ctx_kwargs)
        if opts.simulate_stealth:
            await ctx.add_init_script(
                _stealth_init_script(profile["languages"], profile["navigator_platform"])
            )
        if opts.init_script:
            path = Path(opts.init_script)
            if path.is_file():
                await ctx.add_init_script(path=str(path))
            else:
                await ctx.add_init_script(opts.init_script)
        return ctx

    async def fetch(self, url: str, **overrides: Any) -> DynamicFetchResult:
        """Navigate and return the rendered page; reuses one BrowserContext."""
        if not url or not str(url).strip():
            raise FetchError("URL is required")
        url = str(url).strip()

        # Extract per-request proxy before option merge (not a SessionOptions field)
        fetch_proxy = self._pick_fetch_proxy(overrides)

        saved = self.opts
        if overrides:
            merged = field_replace(saved, **_overrides_to_opts(overrides))
            self.opts = merged

        started = time.perf_counter()
        owns_runtime = False
        ephemeral = False
        ctx: Optional[BrowserContext] = None
        try:
            if not self._entered:
                await self.__aenter__()
                owns_runtime = True

            assert self._browser is not None
            assert self._context is not None
            engine = self._browser_engine or "chromium"

            # Rotator or explicit per-request proxy → ephemeral context; else shared
            if fetch_proxy is not None and (
                self._proxy_rotator is not None or self.opts.proxy is None
            ):
                ctx, ephemeral = await self._context_for_proxy(fetch_proxy, url)
            elif fetch_proxy is not None:
                # Override static session proxy for this request only
                ctx, ephemeral = await self._context_for_proxy(fetch_proxy, url)
            else:
                ctx, ephemeral = self._context, False

            page = await ctx.new_page()
            page.set_default_timeout(self.opts.timeout)

            try:
                if HAS_STEALTH and self.opts.simulate_stealth:
                    await _stealth.apply_stealth_async(page)

                if (
                    self.opts.disable_resources
                    or self.opts.block_ads
                    or self.opts.blocked_domains
                ):
                    await _apply_request_blocking_async(
                        page,
                        disable_resources=self.opts.disable_resources,
                        blocked_domains=self.opts.blocked_domains,
                        block_ads=self.opts.block_ads,
                    )

                if self.opts.page_setup:
                    await _maybe_await(self.opts.page_setup(page))

                wait_until = "load" if self.opts.load_dom else "domcontentloaded"
                response: Optional[PWResponse] = await page.goto(
                    url, wait_until=wait_until, timeout=self.opts.timeout
                )

                if self.opts.network_idle:
                    try:
                        await page.wait_for_load_state(
                            "networkidle", timeout=self.opts.timeout
                        )
                    except Exception:
                        pass

                if self.opts.wait_selector:
                    await page.wait_for_selector(
                        self.opts.wait_selector,
                        state=self.opts.wait_selector_state,  # type: ignore[arg-type]
                        timeout=self.opts.timeout,
                    )

                if self.opts.page_action:
                    await _maybe_await(self.opts.page_action(page))

                if self.opts.wait and self.opts.wait > 0:
                    await page.wait_for_timeout(int(self.opts.wait))

                html = await page.content()
                title = await page.title()
                final_url = page.url or url
                status = int(response.status) if response is not None else 200
                hdrs: dict[str, str] = {}
                if response is not None:
                    try:
                        hdrs = {k: v for k, v in response.headers.items()}
                    except Exception:
                        hdrs = {}

                # Merge cookies from ephemeral proxied context back into session store
                if ephemeral:
                    try:
                        await self.set_cookies(await ctx.cookies())
                    except Exception:
                        pass

                elapsed = time.perf_counter() - started
                cookie_count = len(await self.get_cookies())
                return DynamicFetchResult(
                    url=final_url,
                    status_code=status,
                    headers=hdrs,
                    content=html.encode("utf-8", errors="replace"),
                    text=html,
                    http_version="",
                    elapsed=elapsed,
                    ok=200 <= status < 400,
                    title=title,
                    browser_engine=engine,
                    final_url=final_url,
                    extras={
                        "title": title,
                        "browser": engine,
                        "engine": "playwright",
                        "headless": self.opts.headless,
                        "cookies": cookie_count,
                        "proxy": self.last_proxy,
                    },
                )
            finally:
                try:
                    await page.close()
                except Exception:
                    pass
                if ephemeral and ctx is not None and ctx is not self._context:
                    try:
                        await ctx.close()
                    except Exception:
                        pass
        except Exception as exc:
            from proxy_rotator import is_proxy_error

            if self._proxy_rotator is not None and fetch_proxy and is_proxy_error(exc):
                try:
                    self._proxy_rotator.mark_failed(fetch_proxy)
                except Exception:
                    pass
            raise FetchError(f"DynamicFetcher failed for {url}: {exc}") from exc
        finally:
            self.opts = saved
            if owns_runtime:
                await self.close()

    @property
    def proxy_rotator(self) -> Any:
        return self._proxy_rotator

    async def get_cookies(self) -> list[dict[str, Any]]:
        if self._context is None:
            return []
        try:
            return [dict(c) for c in await self._context.cookies()]
        except Exception:
            return []

    async def cookies_map(self) -> dict[str, str]:
        from session_store import cookies_to_dict

        return cookies_to_dict(await self.get_cookies())

    async def cookies_header(self) -> str:
        from session_store import cookies_to_header

        return cookies_to_header(await self.get_cookies())

    async def set_cookies(self, cookies: CookieInput, url: str = "") -> None:
        if self._context is None:
            self.opts.cookies = cookies
            return
        from session_store import normalize_cookies

        items = normalize_cookies(cookies, url=url or "https://example.com")
        if items:
            await self._context.add_cookies(items)

    async def clear_cookies(self) -> None:
        if self._context is not None:
            try:
                await self._context.clear_cookies()
            except Exception:
                pass

    async def save(
        self, path: Optional[Union[str, Path]] = None, **meta: Any
    ) -> Path:
        from session_store import save_session_file

        target = Path(path) if path else self._session_file
        if target is None:
            raise ValueError("No path given and no session_file configured")
        cookies = await self.get_cookies()
        state = self.state
        engine = self._browser_engine

        def _write() -> Path:
            return save_session_file(
                target,
                cookies=cookies,
                state=state,
                meta={"kind": "AsyncDynamicSession", "browser": engine, **meta},
            )

        return await asyncio.to_thread(_write)

    async def load(
        self, path: Optional[Union[str, Path]] = None, *, url: str = ""
    ) -> None:
        from session_store import load_session_file

        target = Path(path) if path else self._session_file
        if target is None or not Path(target).is_file():
            raise FileNotFoundError(f"Session file not found: {target}")

        data = await asyncio.to_thread(load_session_file, target)
        self.state.update(dict(data.get("state") or {}))
        if data.get("cookies"):
            await self.set_cookies(data["cookies"], url=url)

    async def snapshot(self) -> dict[str, Any]:
        """Return cookies + state (mirrors sync ``snapshot``, async for cookies)."""
        return {
            "cookies": await self.get_cookies(),
            "state": dict(self.state),
            "kind": "AsyncDynamicSession",
        }

    async def restore(
        self, snapshot: Mapping[str, Any], *, url: str = ""
    ) -> None:
        if snapshot.get("state"):
            self.state.update(dict(snapshot["state"]))
        if snapshot.get("cookies"):
            await self.set_cookies(snapshot["cookies"], url=url)  # type: ignore[arg-type]


class AsyncDynamicFetcher:
    """Fetch JS-rendered pages with async Playwright Chromium or Google Chrome.

    Example::

        import asyncio
        from async_dynamic_fetcher import AsyncDynamicFetcher

        async def main() -> None:
            r = await AsyncDynamicFetcher.fetch(
                "https://spa.example.com",
                real_chrome=True,
                headless=True,
                network_idle=True,
                wait=1500,
                wait_selector="main",
            )
            print(r.title, r.status_code, len(r.text))

        asyncio.run(main())
    """

    _defaults: dict[str, Any] = {
        "real_chrome": True,
        "headless": True,
        "timeout": DEFAULT_TIMEOUT_MS,
        "wait": DEFAULT_WAIT_MS,
        "load_dom": True,
        "google_search": True,
        "simulate_stealth": True,
    }

    @classmethod
    def configure(cls, **kwargs: Any) -> None:
        cls._defaults.update(kwargs)

    @classmethod
    async def fetch(cls, url: str, **kwargs: Any) -> DynamicFetchResult:
        opts = {**cls._defaults, **kwargs}
        async with AsyncDynamicSession(**opts) as session:
            return await session.fetch(url)

    # Scrapling alias
    get = fetch


# Backward-compatible alias
AsyncPlayWrightFetcher = AsyncDynamicFetcher
