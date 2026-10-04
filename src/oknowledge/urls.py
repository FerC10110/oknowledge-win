"""Normalizar una URL para que el mismo link no entre dos veces.

El id de un link es el hash de su forma normalizada. Dos URLs que llevan a
la misma página -- una copiada del navegador, otra reenviada por WhatsApp con
parámetros de seguimiento -- tienen que dar el mismo id.
"""

from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PREFIXES = ("utm_",)
TRACKING_EXACT = frozenset({
    "fbclid", "gclid", "msclkid", "mc_cid", "mc_eid", "igshid",
    "ref", "ref_src", "ref_url", "si", "spm", "_hsenc", "_hsmi",
})


def _is_tracking(key: str) -> bool:
    key = key.lower()
    return key in TRACKING_EXACT or any(key.startswith(p) for p in TRACKING_PREFIXES)


def normalize(url: str) -> str:
    raw = url.strip()
    if "//" not in raw.split("?", 1)[0][:8]:
        raw = "https://" + raw
    parts = urlsplit(raw)

    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    netloc = host
    if parts.port and parts.port not in (80, 443):
        netloc = f"{host}:{parts.port}"

    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    query = sorted(
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking(k)
    )

    return urlunsplit((parts.scheme.lower() or "https", netloc, path, urlencode(query), ""))


def link_id(url: str) -> str:
    return hashlib.sha256(normalize(url).encode("utf-8")).hexdigest()[:12]
