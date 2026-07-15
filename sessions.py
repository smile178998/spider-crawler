#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified session exports — persistent cookies & state across requests.

Three sync tiers + matching async sessions share the cookie/state API:

* :class:`~fetcher.FetcherSession` / :class:`~fetcher.AsyncFetcherSession`
* :class:`~dynamic_fetcher.DynamicSession` / :class:`~async_dynamic_fetcher.AsyncDynamicSession`
* :class:`~stealthy_fetcher.StealthySession` / :class:`~async_stealthy_fetcher.AsyncStealthySession`

Common methods on every session (async variants are ``await``-able where I/O)::

    get_cookies() / set_cookies() / clear_cookies()
    cookies_map() / cookies_header()
    save(path) / load(path)          # JSON on disk
    snapshot() / restore(snap)       # in-memory hand-off
    state: dict                      # arbitrary cross-request bag
"""

from __future__ import annotations

from fetcher import AsyncFetcherSession, FetcherSession
from dynamic_fetcher import DynamicSession
from stealthy_fetcher import StealthySession
from async_dynamic_fetcher import AsyncDynamicSession
from async_stealthy_fetcher import AsyncStealthySession
from session_store import (
    CookieInput,
    cookies_to_dict,
    cookies_to_header,
    load_session_file,
    normalize_cookies,
    parse_cookie_header,
    save_session_file,
)
from proxy_rotator import (
    ProxyRotator,
    ProxyType,
    cyclic_rotation,
    random_rotation,
    resolve_request_proxy,
    normalize_proxy,
    proxy_to_url,
    is_proxy_error,
)
from request_blocking import (
    apply_request_blocking,
    is_domain_blocked,
    merge_blocked_domains,
)
from ad_domains import ad_domain_count, load_ad_domains
from doh import (
    CLOUDFLARE_DOH_URL,
    apply_chromium_doh,
    chromium_doh_args,
    env_dns_over_https_enabled,
    resolve_dns_over_https,
    resolve_host,
)

__all__ = [
    "FetcherSession",
    "AsyncFetcherSession",
    "DynamicSession",
    "AsyncDynamicSession",
    "StealthySession",
    "AsyncStealthySession",
    "CookieInput",
    "cookies_to_dict",
    "cookies_to_header",
    "load_session_file",
    "normalize_cookies",
    "parse_cookie_header",
    "save_session_file",
    "ProxyRotator",
    "ProxyType",
    "cyclic_rotation",
    "random_rotation",
    "resolve_request_proxy",
    "normalize_proxy",
    "proxy_to_url",
    "is_proxy_error",
    "apply_request_blocking",
    "is_domain_blocked",
    "merge_blocked_domains",
    "ad_domain_count",
    "load_ad_domains",
    "CLOUDFLARE_DOH_URL",
    "apply_chromium_doh",
    "chromium_doh_args",
    "env_dns_over_https_enabled",
    "resolve_dns_over_https",
    "resolve_host",
]
