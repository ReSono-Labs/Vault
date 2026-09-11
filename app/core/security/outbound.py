from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from app.core.exceptions import BadRequestError


ALLOWED_URL_SCHEMES = {"http", "https"}
METADATA_SERVICE_IPS = {
    ipaddress.ip_address("169.254.169.254"),
}
EXTENSION_LOCAL_HOSTS = {"host.docker.internal"}


def validate_public_url(raw_url: str, *, target: str = "url") -> str:
    candidate = raw_url.strip()
    parsed = urlparse(candidate)
    if parsed.scheme not in ALLOWED_URL_SCHEMES or not parsed.hostname:
        raise BadRequestError(message="URL must use http or https with a valid host.", target=target)
    validate_public_host(parsed.hostname, target=target)
    return candidate


def validate_extension_url(raw_url: str, *, target: str = "url") -> str:
    """Validate an extension destination, allowing only explicit loopback exceptions.

    Remote extension traffic may use public HTTPS. Plain HTTP is confined to
    loopback, and private/link-local/metadata destinations are rejected before
    any connection is attempted.
    """
    candidate = raw_url.strip()
    parsed = urlparse(candidate)
    if parsed.scheme not in ALLOWED_URL_SCHEMES or not parsed.hostname:
        raise BadRequestError(message="URL must use http or https with a valid host.", target=target)
    local_destination = _is_extension_local_name(parsed.hostname)
    if parsed.scheme == "http" and not local_destination:
        raise BadRequestError(message="Remote extension URLs require HTTPS.", target=target)
    if not local_destination:
        try:
            literal = ipaddress.ip_address(parsed.hostname.strip("[]"))
        except ValueError:
            literal = None
        if literal is not None:
            _reject_private_address(literal, target=target)
    return candidate


def validate_extension_host(host: str, *, target: str = "host") -> str:
    """Re-resolve a destination immediately before I/O to reduce DNS rebinding risk."""
    candidate = host.strip().strip("[]").lower()
    if _is_extension_local_name(candidate):
        return candidate
    return validate_public_host(candidate, target=target)


def validate_public_host(host: str, *, target: str = "host") -> str:
    candidate = host.strip().strip("[]").lower()
    if not candidate:
        raise BadRequestError(message="Host is required.", target=target)
    if candidate in {"localhost", "localhost.localdomain"} or candidate.endswith(".localhost"):
        raise BadRequestError(message="Host must not resolve to a local or private network.", target=target)
    try:
        literal = ipaddress.ip_address(candidate)
    except ValueError:
        literal = None
    if literal is not None:
        _reject_private_address(literal, target=target)
        return candidate
    try:
        results = socket.getaddrinfo(candidate, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise BadRequestError(message="Host could not be resolved.", target=target) from exc
    addresses = {item[4][0] for item in results if item and item[4]}
    if not addresses:
        raise BadRequestError(message="Host could not be resolved.", target=target)
    for address in addresses:
        _reject_private_address(ipaddress.ip_address(address), target=target)
    return candidate


def assert_redirect_safe(original_url: str, redirect_url: str, *, allow_host_change: bool = True, target: str = "url") -> str:
    safe_url = validate_public_url(redirect_url, target=target)
    if not allow_host_change:
        original_host = (urlparse(original_url).hostname or "").lower()
        redirect_host = (urlparse(safe_url).hostname or "").lower()
        if original_host != redirect_host:
            raise BadRequestError(message="Redirects to a different host are not allowed for this request.", target=target)
    return safe_url


def _reject_private_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address, *, target: str) -> None:
    if (
        address in METADATA_SERVICE_IPS
        or address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise BadRequestError(message="Host must not resolve to a local or private network.", target=target)


def _is_loopback_name_or_literal(host: str) -> bool:
    candidate = host.strip().strip("[]").lower()
    if candidate in {"localhost", "localhost.localdomain"} or candidate.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return False


def _is_extension_local_name(host: str) -> bool:
    candidate = host.strip().strip("[]").lower()
    return candidate in EXTENSION_LOCAL_HOSTS or _is_loopback_name_or_literal(candidate)
