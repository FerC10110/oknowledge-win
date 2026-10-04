"""GitHub repositories, via the public API."""

from __future__ import annotations

import base64
import binascii
import datetime
import json
import re
from urllib.parse import urlsplit

from ..model import Extracted
from ..net import NetworkError, fetch
from . import Unreadable, _host
from . import article

API = "https://api.github.com/repos"

# First path segments of github.com that are site sections, not owners.
RESERVED = frozenset({
    "about", "apps", "codespaces", "collections", "customer-stories", "enterprise",
    "events", "explore", "features", "issues", "login", "marketplace", "new",
    "notifications", "orgs", "organizations", "pricing", "pulls", "readme", "search",
    "security", "settings", "sponsors", "team", "topics", "trending", "users",
})
_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


def _slug(url: str) -> str | None:
    """owner/repo for a repository URL, None for anything else on GitHub."""
    if _host(url) != "github.com":
        return None
    parts = [p for p in urlsplit(url).path.split("/") if p]
    if len(parts) < 2 or parts[0].lower() in RESERVED:
        return None
    owner, repo = parts[0], parts[1].removesuffix(".git")
    if not (_NAME.match(owner) and _NAME.match(repo)) or repo in (".", ".."):
        return None
    return f"{owner}/{repo}"


def from_api(repo: dict, readme: str, url: str) -> Extracted:
    facts = [
        repo.get("description") or "",
        f"Lenguaje principal: {repo.get('language') or 'desconocido'}.",
        f"Estrellas: {repo.get('stargazers_count', 0)}.",
    ]
    topics = repo.get("topics") or []
    if topics:
        facts.append("Temas: " + ", ".join(topics) + ".")
    text = "\n".join(f for f in facts if f.strip())
    if readme.strip():
        text += "\n\n" + readme.strip()
    if not text.strip():
        raise Unreadable(f"the repository has no description or readme: {url}")

    pushed = str(repo.get("pushed_at") or "")[:10] or None
    return Extracted(
        title=repo.get("full_name") or _slug(url) or url,
        text=text,
        type="github",
        source=_host(url),
        author=(repo.get("owner") or {}).get("login"),
        published=pushed,
        cover_url=None,
    )


def _explain(error: NetworkError, slug: str) -> str:
    if error.status == 404:
        return f"repository {slug} not found or private"
    limited = error.status in (403, 429) and (
        error.headers.get("x-ratelimit-remaining") == "0" or "retry-after" in error.headers)
    if limited:
        reset = error.headers.get("x-ratelimit-reset", "")
        when = ""
        if reset.isdigit():
            moment = datetime.datetime.fromtimestamp(int(reset), datetime.timezone.utc)
            when = f"; it resets at {moment:%Y-%m-%d %H:%M} UTC"
        return f"GitHub API rate limit reached while reading {slug}{when}"
    return f"could not read {slug}: {error}"


def from_url(url: str) -> Extracted:
    slug = _slug(url)
    if slug is None:
        # gist.github.com, docs.github.com, a user page, /features, /orgs/...:
        # not a repository, so read it as the web page it is.
        return article.from_url(url)

    try:
        repo = json.loads(fetch(f"{API}/{slug}").text)
    except NetworkError as error:
        raise Unreadable(_explain(error, slug)) from error
    except ValueError as error:
        raise Unreadable(f"GitHub gave an unreadable answer for {slug}") from error
    if not isinstance(repo, dict):
        raise Unreadable(f"GitHub gave an unexpected answer for {slug}")

    readme = ""
    try:
        payload = json.loads(fetch(f"{API}/{slug}/readme").text)
        readme = base64.b64decode(payload.get("content", "")).decode("utf-8", "replace")
    except (NetworkError, ValueError, AttributeError, binascii.Error):
        readme = ""    # no readme, or one we cannot read: the repo facts still make a note
    return from_api(repo, readme, url)
