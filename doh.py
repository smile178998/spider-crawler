#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DNS-over-HTTPS helpers — Cloudflare DoH to prevent DNS leaks with proxies.

Browser fetchers enable Chromium's ``--dns-over-https-templates`` flag.
HTTP fetchers set libcurl ``CURLOPT_DOH_URL`` (via curl_cffi) so hostname
resolution bypasses the system resolver.
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import urllib.error
import urllib.request
from contextlib import contextmanager
from typing import Any, Generator, Mapping, Optional
from urllib.parse import quote, urlparse

# Chromium / curl endpoint (same host Scrapling uses)
CLOUDFLARE_DOH_URL = "https://cloudflare-dns.com/dns-query"
CLOUDFLARE_DOH_TEMPLATE = "https://cloudflare-dns.com/dns-query"

_TRUTHY = frozenset({"1", "true", "yes", "on"})


class DohError(RuntimeError):
    """Raised when a DoH lookup fails."""


def is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in _TRUTHY


def env_dns_over_https_enabled() -> bool:
    """``SCRAPER_DOH`` or ``DNS_OVER_HTTPS`` enable DoH by default for the UI pipeline."""
    for key in ("SCRAPER_DOH", "DNS_OVER_HTTPS"):
        raw = os.getenv(key, "").strip()
        if raw:
            return is_truthy(raw)
    return False


def resolve_dns_over_https(
    flag: Any = None,
    *,
    default: Optional[bool] = None,
) -> bool:
    """Resolve effective DoH on/off.

    Explicit ``flag`` wins; otherwise ``default``; otherwise environment.
    """
    if flag is not None and flag is not ...:
        return is_truthy(flag)
    if default is not None:
        return bool(default)
    return env_dns_over_https_enabled()


def chromium_doh_args() -> list[str]:
    """Launch flags that route Chromium DNS through Cloudflare DoH."""
    return [f"--dns-over-https-templates={CLOUDFLARE_DOH_TEMPLATE}"]


def apply_chromium_doh(args: Optional[list[str]], enabled: bool) -> list[str]:
    """Return a copy of ``args`` with Cloudflare DoH flags when ``enabled``."""
    out = list(args or [])
    if not enabled:
        return out
    marker = "--dns-over-https-templates="
    if any(str(a).startswith(marker) for a in out):
        return out
    out.extend(chromium_doh_args())
    return out


def curl_doh_options() -> dict[Any, bytes]:
    """``curl_options`` dict for ``curl_cffi.Session(..., curl_options=...)``."""
    from curl_cffi import CurlOpt

    return {CurlOpt.DOH_URL: CLOUDFLARE_DOH_URL.encode("ascii")}


def is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def resolve_host(
    hostname: str,
    *,
    timeout: float = 5.0,
    doh_url: str = CLOUDFLARE_DOH_URL,
) -> str:
    """Resolve ``hostname`` to an IPv4 (preferred) or IPv6 address via Cloudflare DoH JSON."""
    host = (hostname or "").strip().rstrip(".").lower()
    if not host:
        raise DohError("hostname is required")
    if is_ip_literal(host):
        return host

    query = f"{doh_url}?name={quote(host)}&type=A"
    req = urllib.request.Request(
        query,
        headers={
            "Accept": "application/dns-json",
            "User-Agent": "spaider-crawler-doh/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise DohError(f"DoH lookup failed for {host}: {exc}") from exc

    answers = payload.get("Answer") or []
    for ans in answers:
        if int(ans.get("type", 0)) == 1:  # A
            data = str(ans.get("data") or "").strip()
            if data and is_ip_literal(data):
                return data

    # Fallback AAAA
    query6 = f"{doh_url}?name={quote(host)}&type=AAAA"
    req6 = urllib.request.Request(
        query6,
        headers={
            "Accept": "application/dns-json",
            "User-Agent": "spaider-crawler-doh/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req6, timeout=timeout) as resp:
            payload6 = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise DohError(f"DoH lookup failed for {host}: {exc}") from exc

    for ans in payload6.get("Answer") or []:
        if int(ans.get("type", 0)) == 28:  # AAAA
            data = str(ans.get("data") or "").strip()
            if data and is_ip_literal(data):
                return data

    raise DohError(f"DoH returned no A/AAAA for {host}")


@contextmanager
def pinned_hostname(hostname: str, ip: str) -> Generator[None, None, None]:
    """Temporarily pin ``hostname`` → ``ip`` for ``socket.getaddrinfo`` (urllib fallback)."""
    host = hostname.strip().rstrip(".").lower()
    real_getaddrinfo = socket.getaddrinfo

    def _patched(
        name: Any,
        port: Any,
        family: int = 0,
        type: int = 0,
        proto: int = 0,
        flags: int = 0,
    ):
        lookup = str(name or "").strip().rstrip(".").lower()
        if lookup == host:
            return real_getaddrinfo(ip, port, family, type, proto, flags)
        return real_getaddrinfo(name, port, family, type, proto, flags)

    socket.getaddrinfo = _patched  # type: ignore[assignment]
    try:
        yield
    finally:
        socket.getaddrinfo = real_getaddrinfo  # type: ignore[assignment]


def pin_url_host(url: str, *, timeout: float = 5.0) -> tuple[Optional[str], Optional[str]]:
    """Return ``(hostname, ip)`` for DoH pinning, or ``(None, None)`` if not applicable."""
    host = urlparse(url).hostname
    if not host or is_ip_literal(host):
        return None, None
    return host, resolve_host(host, timeout=timeout)
