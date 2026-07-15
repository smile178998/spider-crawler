#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared cookie / state persistence helpers for Fetcher sessions."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Optional, Sequence, Union
from urllib.parse import urlparse

CookieDict = dict[str, Any]
CookieList = list[CookieDict]
CookieInput = Union[str, Mapping[str, str], Sequence[Mapping[str, Any]], None]


def parse_cookie_header(header: str, url: str = "") -> CookieList:
    """Parse ``a=1; b=2`` into Playwright/curl-style cookie dicts."""
    out: CookieList = []
    if not header or not str(header).strip():
        return out
    page_url = url or "https://example.com"
    parsed = urlparse(page_url)
    domain = parsed.hostname or "example.com"
    for part in str(header).split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        name, value = name.strip(), value.strip()
        if not name:
            continue
        item: CookieDict = {"name": name, "value": value}
        if url:
            item["url"] = page_url
        else:
            item["domain"] = domain
            item["path"] = "/"
        out.append(item)
    return out


def normalize_cookies(cookies: CookieInput, url: str = "") -> CookieList:
    """Normalize str / dict / list cookies into a list of cookie dicts."""
    if not cookies:
        return []
    if isinstance(cookies, str):
        return parse_cookie_header(cookies, url)
    if isinstance(cookies, Mapping):
        # Simple name→value mapping
        page_url = url or "https://example.com"
        parsed = urlparse(page_url)
        domain = parsed.hostname or "example.com"
        items: CookieList = []
        for name, value in cookies.items():
            item: CookieDict = {"name": str(name), "value": str(value)}
            if url:
                item["url"] = page_url
            else:
                item["domain"] = domain
                item["path"] = "/"
            items.append(item)
        return items
    items = []
    for raw in cookies:
        c = dict(raw)
        if "name" not in c:
            continue
        if "value" not in c:
            c["value"] = ""
        if "url" not in c and "domain" not in c:
            if url:
                c["url"] = url
            else:
                c["domain"] = urlparse(url or "https://example.com").hostname or "example.com"
                c["path"] = c.get("path") or "/"
        items.append(c)
    return items


def cookies_to_header(cookies: Sequence[Mapping[str, Any]]) -> str:
    """Flatten cookies to a ``Cookie`` request header value."""
    parts = []
    for c in cookies:
        name = c.get("name")
        if not name:
            continue
        parts.append(f"{name}={c.get('value', '')}")
    return "; ".join(parts)


def cookies_to_dict(cookies: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Collapse cookie list to ``{name: value}`` (last wins on duplicates)."""
    return {str(c["name"]): str(c.get("value", "")) for c in cookies if c.get("name")}


def save_session_file(
    path: Union[str, Path],
    *,
    cookies: Sequence[Mapping[str, Any]] | None = None,
    state: Mapping[str, Any] | None = None,
    meta: Mapping[str, Any] | None = None,
) -> Path:
    """Persist cookies + arbitrary state to a JSON file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "saved_at": time.time(),
        "cookies": [dict(c) for c in (cookies or [])],
        "state": dict(state or {}),
        "meta": dict(meta or {}),
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_session_file(path: Union[str, Path]) -> dict[str, Any]:
    """Load a session JSON produced by :func:`save_session_file`."""
    target = Path(path)
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid session file: {target}")
    data.setdefault("cookies", [])
    data.setdefault("state", {})
    data.setdefault("meta", {})
    return data


class SessionMixin:
    """Mixin: cross-request ``state`` bag + cookie save/load helpers.

    Concrete sessions implement :meth:`get_cookies` / :meth:`set_cookies`.
    """

    state: MutableMapping[str, Any]

    def _init_session_state(
        self,
        *,
        state: Optional[Mapping[str, Any]] = None,
        session_file: Optional[Union[str, Path]] = None,
    ) -> None:
        self.state = dict(state or {})
        self._session_file: Optional[Path] = Path(session_file) if session_file else None
        if self._session_file and self._session_file.is_file():
            self.load(self._session_file)

    def get_cookies(self) -> CookieList:
        raise NotImplementedError

    def set_cookies(self, cookies: CookieInput, url: str = "") -> None:
        raise NotImplementedError

    def clear_cookies(self) -> None:
        raise NotImplementedError

    def cookies_header(self) -> str:
        return cookies_to_header(self.get_cookies())

    def cookies_map(self) -> dict[str, str]:
        return cookies_to_dict(self.get_cookies())

    def save(self, path: Optional[Union[str, Path]] = None, **meta: Any) -> Path:
        """Save cookies + ``state`` to disk. Defaults to constructor ``session_file``."""
        target = Path(path) if path else self._session_file
        if target is None:
            raise ValueError("No path given and no session_file configured")
        return save_session_file(
            target,
            cookies=self.get_cookies(),
            state=self.state,
            meta={"kind": type(self).__name__, **meta},
        )

    def load(self, path: Optional[Union[str, Path]] = None, *, url: str = "") -> None:
        """Load cookies + ``state`` from disk into this live session."""
        target = Path(path) if path else self._session_file
        if target is None or not target.is_file():
            raise FileNotFoundError(f"Session file not found: {target}")
        data = load_session_file(target)
        if data.get("state"):
            self.state.update(dict(data["state"]))
        cookies = data.get("cookies") or []
        if cookies:
            self.set_cookies(cookies, url=url)

    def snapshot(self) -> dict[str, Any]:
        """In-memory snapshot of cookies + state (for cloning/hand-off)."""
        return {
            "cookies": self.get_cookies(),
            "state": dict(self.state),
            "kind": type(self).__name__,
        }

    def restore(self, snapshot: Mapping[str, Any], *, url: str = "") -> None:
        """Restore from :meth:`snapshot` or a loaded session file dict."""
        if snapshot.get("state"):
            self.state.update(dict(snapshot["state"]))
        cookies = snapshot.get("cookies") or []
        if cookies:
            self.set_cookies(cookies, url=url)  # type: ignore[arg-type]
