"""Refuse browser requests that change something when they come from another site.

Defence in depth on top of SameSite=Strict cookies and the session-bound CSRF token. Only
requests that use the browser session cookie are checked; the Link app and other clients use
a bearer token, which a foreign page cannot send.

The check accepts whatever address the person opened Vault at: the request's own Host, or
the X-Forwarded-Host a local proxy (the Link bridge, Tailscale Serve, a reverse proxy) sets.
A cross-site page can't set that header without a CORS preflight, which Vault never grants.
Anything else can be allowed with RESONO_VAULT_TRUSTED_ORIGINS (comma-separated origins).
"""
from __future__ import annotations

import os
from typing import Mapping
from urllib.parse import urlsplit

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_DEFAULT_PORTS = {"http": 80, "https": 443}


def _header(headers: Mapping[str, str], name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None


def _authority(host: str, scheme: str | None = None) -> str | None:
    """host[:port] in lower case, without the default port for the scheme."""
    host = host.strip().lower().rstrip(".")
    if not host:
        return None
    parts = urlsplit(f"//{host}")
    try:
        port = parts.port
    except ValueError:
        return None
    name = parts.hostname or ""
    if ":" in name:
        name = f"[{name}]"
    if port is None or (scheme is not None and _DEFAULT_PORTS.get(scheme) == port):
        return name
    return f"{name}:{port}"


def trusted_origins() -> frozenset[str]:
    raw = os.environ.get("RESONO_VAULT_TRUSTED_ORIGINS", "")
    return frozenset(item.strip().rstrip("/").lower() for item in raw.split(",") if item.strip())


def cross_site_refusal(*, method: str, headers: Mapping[str, str]) -> str | None:
    """A reason to refuse, or None. Only cookie-session requests that change state are checked."""
    if method.upper() in _SAFE_METHODS:
        return None
    authorization = _header(headers, "authorization") or ""
    cookies = _header(headers, "cookie") or ""
    if authorization.lower().startswith("bearer ") or "resono_refresh=" not in cookies:
        return None
    origin = (_header(headers, "origin") or "").strip()
    if not origin:
        # Older browsers omit Origin; the Fetch metadata header still says where it came from.
        site = (_header(headers, "sec-fetch-site") or "").strip().lower()
        return "cross-site" if site == "cross-site" else None
    if origin.lower() == "null":
        return "an opaque origin"
    if origin.rstrip("/").lower() in trusted_origins():
        return None
    parts = urlsplit(origin)
    claimed = _authority(parts.netloc, parts.scheme) if parts.scheme in _DEFAULT_PORTS else None
    if claimed is None:
        return "an invalid origin"
    for value in (_header(headers, "host"), _header(headers, "x-forwarded-host")):
        for candidate in (value or "").split(","):
            if candidate.strip() and _authority(candidate, parts.scheme) == claimed:
                return None
    return f"{parts.scheme}://{claimed}"
