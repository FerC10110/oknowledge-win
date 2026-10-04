"""Normalizar una URL para que el mismo link no entre dos veces.

El id de un link es el hash de su forma normalizada. Dos URLs que llevan a
la misma página -- una copiada del navegador, otra reenviada por WhatsApp con
parámetros de seguimiento -- tienen que dar el mismo id.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PREFIXES = ("utm_",)
TRACKING_EXACT = frozenset({
    "fbclid", "gclid", "msclkid", "mc_cid", "mc_eid", "igshid",
    "ref_src", "ref_url", "si", "spm", "_hsenc", "_hsmi",
})
SCHEME_PATTERN = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
SCHEME_COLON_PATTERN = re.compile(r"^[a-z][a-z0-9+-]*:", re.IGNORECASE)
PORT_PATTERN = re.compile(r"^\d+($|[/?#])")


def _is_tracking(key: str) -> bool:
    key = key.lower()
    return key in TRACKING_EXACT or any(key.startswith(p) for p in TRACKING_PREFIXES)


def normalize(url: str) -> str:
    raw = url.strip()

    # Rule 1: Empty input returns empty string
    if not raw:
        return ""

    original_raw = raw  # Save original for fallback

    # Rule 2: Check for :// scheme
    has_scheme_match = SCHEME_PATTERN.match(raw)
    if has_scheme_match:
        scheme = has_scheme_match.group(0)[:-3]  # Remove ://
        # Only normalize http and https; return other schemes as-is
        if scheme.lower() not in ("http", "https"):
            return raw
    # Rule 3: Check for scheme-relative URL
    elif raw.startswith("//"):
        raw = "https:" + raw
    # Rule 4: Check for single-colon non-http scheme
    elif ":" in raw:
        colon_idx = raw.index(":")
        prefix = raw[:colon_idx]
        suffix = raw[colon_idx + 1:]

        # Check if prefix has no dot and suffix is not a port
        if "." not in prefix and not PORT_PATTERN.match(suffix):
            # This is a non-http scheme, return unchanged
            return raw

        # Rule 5: Prepend https:// and normalize
        raw = "https://" + raw
    else:
        # Rule 5: No colon, prepend https://
        raw = "https://" + raw

    try:
        parts = urlsplit(raw)

        # Check if the netloc has IPv6 brackets
        is_ipv6 = parts.netloc.startswith("[")

        if is_ipv6:
            # IPv6 address: preserve brackets and don't lowercase
            host = parts.hostname  # This returns the IPv6 without brackets
            netloc = f"[{host}]"
        else:
            host = (parts.hostname or "").lower()
            if host.startswith("www."):
                host = host[4:]
            netloc = host

        if parts.port and parts.port not in (80, 443):
            netloc = f"{netloc}:{parts.port}"

        path = parts.path or "/"
        if len(path) > 1 and path.endswith("/"):
            path = path.rstrip("/")

        query = sorted(
            (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not _is_tracking(k)
        )

        return urlunsplit((parts.scheme.lower() or "https", netloc, path, urlencode(query), ""))
    except Exception:
        # Never raise: return the stripped original input on any error
        return original_raw


def link_id(url: str) -> str:
    return hashlib.sha256(normalize(url).encode("utf-8")).hexdigest()[:12]
