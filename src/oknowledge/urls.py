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
SCHEME_COLON_PATTERN = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)


def _is_tracking(key: str) -> bool:
    key = key.lower()
    return key in TRACKING_EXACT or any(key.startswith(p) for p in TRACKING_PREFIXES)


def normalize(url: str) -> str:
    raw = url.strip()

    # Detect if there's a scheme using regex or scheme-relative URL
    has_scheme_match = SCHEME_PATTERN.match(raw)
    has_scheme_colon = SCHEME_COLON_PATTERN.match(raw)
    has_scheme_relative = raw.startswith("//")

    if has_scheme_match:
        scheme = has_scheme_match.group(0)[:-3]  # Remove ://
        # Only normalize http and https; return other schemes as-is
        if scheme.lower() not in ("http", "https"):
            return raw
    elif has_scheme_colon:
        scheme = has_scheme_colon.group(0)[:-1]  # Remove :
        # Only normalize http and https; return other schemes as-is
        if scheme.lower() not in ("http", "https"):
            return raw
    elif not has_scheme_relative:
        # No scheme, prepend https://
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
        # Never raise: return the stripped input on any error
        return raw


def link_id(url: str) -> str:
    return hashlib.sha256(normalize(url).encode("utf-8")).hexdigest()[:12]
