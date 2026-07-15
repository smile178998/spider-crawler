#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Proxy rotation — round-robin / random / custom strategies for all Sessions."""

from __future__ import annotations

import random
from threading import Lock
from typing import Any, Callable, Mapping, Optional, Sequence, Union
from urllib.parse import urlparse

ProxyDict = dict[str, str]
ProxyType = Union[str, ProxyDict]
RotationStrategy = Callable[[list[ProxyType], int], tuple[ProxyType, int]]

_PROXY_ERROR_INDICATORS = (
    "net::err_proxy",
    "net::err_tunnel",
    "proxyerror",
    "proxy error",
    "connection refused",
    "connection reset",
    "connection timed out",
    "failed to connect",
    "could not resolve proxy",
    "tunnel connection failed",
    "407 proxy",
    "proxy authentication",
)


def proxy_key(proxy: ProxyType) -> str:
    """Stable identity for a proxy (server + username)."""
    if isinstance(proxy, str):
        return proxy.strip()
    server = str(proxy.get("server") or "").strip()
    username = str(proxy.get("username") or "").strip()
    return f"{server}|{username}"


def normalize_proxy(proxy: Optional[ProxyType]) -> Optional[ProxyDict]:
    """Normalize string / dict proxy to Playwright-style ``{server, ...}``."""
    if not proxy:
        return None
    if isinstance(proxy, Mapping):
        server = str(proxy.get("server") or "").strip()
        if not server:
            return None
        if "://" not in server:
            server = "http://" + server
        out: ProxyDict = {"server": server}
        if proxy.get("username"):
            out["username"] = str(proxy["username"])
        if proxy.get("password"):
            out["password"] = str(proxy["password"])
        return out

    raw = str(proxy).strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = "http://" + raw
    parsed = urlparse(raw)
    if not parsed.hostname:
        raise ValueError(f"Invalid proxy address: {proxy}")
    server = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        server = f"{server}:{parsed.port}"
    out = {"server": server}
    if parsed.username:
        out["username"] = parsed.username
    if parsed.password:
        out["password"] = parsed.password
    return out


def proxy_to_url(proxy: Optional[ProxyType]) -> Optional[str]:
    """Convert proxy to a single URL string (for curl_cffi / urllib)."""
    parsed = normalize_proxy(proxy)
    if not parsed:
        return None
    server = parsed["server"]
    user = parsed.get("username")
    password = parsed.get("password")
    if user:
        # Insert credentials into URL
        scheme, rest = server.split("://", 1)
        auth = user if not password else f"{user}:{password}"
        return f"{scheme}://{auth}@{rest}"
    return server


def proxy_to_curl_map(proxy: Optional[ProxyType]) -> Optional[dict[str, str]]:
    """``{"http": url, "https": url}`` for curl_cffi / requests-style clients."""
    url = proxy_to_url(proxy)
    if not url:
        return None
    return {"http": url, "https": url}


def is_proxy_error(error: BaseException) -> bool:
    msg = str(error).lower()
    return any(ind in msg for ind in _PROXY_ERROR_INDICATORS)


def cyclic_rotation(proxies: list[ProxyType], current_index: int) -> tuple[ProxyType, int]:
    """Round-robin through the proxy list."""
    if not proxies:
        raise ValueError("Empty proxy list")
    idx = current_index % len(proxies)
    return proxies[idx], (idx + 1) % len(proxies)


def random_rotation(proxies: list[ProxyType], current_index: int) -> tuple[ProxyType, int]:
    """Pick a random proxy each time (``current_index`` ignored for selection)."""
    if not proxies:
        raise ValueError("Empty proxy list")
    idx = random.randrange(len(proxies))
    return proxies[idx], (current_index + 1) % len(proxies)


class ProxyRotator:
    """Thread-safe proxy rotator with pluggable strategies.

    Example::

        from proxy_rotator import ProxyRotator, random_rotation

        rotator = ProxyRotator([
            "http://1.2.3.4:8080",
            {"server": "http://5.6.7.8:8080", "username": "u", "password": "p"},
        ])
        print(rotator.get())  # next in cycle

        rotator = ProxyRotator(proxies, strategy=random_rotation)

        # Custom: always prefer first unless marked dead
        def sticky(proxies, idx):
            return proxies[0], idx
        rotator = ProxyRotator(proxies, strategy=sticky)
    """

    __slots__ = ("_proxies", "_proxy_to_index", "_strategy", "_current_index", "_lock", "_failed")

    def __init__(
        self,
        proxies: Sequence[ProxyType],
        strategy: RotationStrategy = cyclic_rotation,
    ) -> None:
        if not proxies:
            raise ValueError("At least one proxy must be provided")
        if not callable(strategy):
            raise TypeError(f"strategy must be callable, got {type(strategy).__name__}")

        self._strategy = strategy
        self._lock = Lock()
        self._proxies: list[ProxyType] = []
        self._proxy_to_index: dict[str, int] = {}
        self._failed: set[str] = set()

        for i, proxy in enumerate(proxies):
            if isinstance(proxy, str):
                if not proxy.strip():
                    raise ValueError("Empty proxy string")
            elif isinstance(proxy, Mapping):
                if "server" not in proxy:
                    raise ValueError("Proxy dict must have a 'server' key")
            else:
                raise TypeError(f"Invalid proxy type: {type(proxy)}. Expected str or dict.")
            key = proxy_key(proxy)
            self._proxy_to_index[key] = i
            self._proxies.append(proxy)

        self._current_index = 0

    def get(self) -> ProxyType:
        """Alias for :meth:`get_proxy`."""
        return self.get_proxy()

    def get_proxy(self) -> ProxyType:
        """Return the next proxy according to the rotation strategy."""
        with self._lock:
            alive = [p for p in self._proxies if proxy_key(p) not in self._failed]
            pool = alive or list(self._proxies)
            # Map strategy index into the working pool size
            proxy, next_idx = self._strategy(pool, self._current_index % max(len(pool), 1))
            self._current_index = next_idx
            return proxy

    def get_normalized(self) -> ProxyDict:
        """Next proxy as a Playwright-style dict."""
        parsed = normalize_proxy(self.get_proxy())
        if not parsed:
            raise ValueError("Rotator returned an empty/invalid proxy")
        return parsed

    def get_url(self) -> str:
        """Next proxy as a URL string."""
        url = proxy_to_url(self.get_proxy())
        if not url:
            raise ValueError("Rotator returned an empty/invalid proxy")
        return url

    def mark_failed(self, proxy: ProxyType) -> None:
        """Temporarily skip this proxy in rotation (until :meth:`reset_failures`)."""
        with self._lock:
            self._failed.add(proxy_key(proxy))

    def mark_ok(self, proxy: ProxyType) -> None:
        with self._lock:
            self._failed.discard(proxy_key(proxy))

    def reset_failures(self) -> None:
        with self._lock:
            self._failed.clear()

    @property
    def proxies(self) -> list[ProxyType]:
        return list(self._proxies)

    @property
    def failed(self) -> list[str]:
        with self._lock:
            return sorted(self._failed)

    def __len__(self) -> int:
        return len(self._proxies)

    def __repr__(self) -> str:
        return f"ProxyRotator(proxies={len(self._proxies)}, strategy={getattr(self._strategy, '__name__', self._strategy)})"


def resolve_request_proxy(
    *,
    request_proxy: Optional[ProxyType] = None,
    proxy_rotator: Optional[ProxyRotator] = None,
    session_proxy: Optional[ProxyType] = None,
) -> Optional[ProxyType]:
    """Pick proxy for one request.

    Priority: explicit per-request ``proxy`` → rotator → session static proxy.
    """
    if request_proxy is not None and request_proxy != "":
        return request_proxy
    if proxy_rotator is not None:
        return proxy_rotator.get_proxy()
    return session_proxy
