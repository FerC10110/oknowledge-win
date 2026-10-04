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


def _text(repo: dict, key: str) -> str:
    value = repo.get(key)
    if value is not None and not isinstance(value, str):
        raise Unreadable(f"unexpected GitHub payload: {key} is {type(value).__name__}, not text")
    return (value or "").strip()


def from_api(repo: dict, readme: str, url: str) -> Extracted:
    description = _text(repo, "description")
    language = _text(repo, "language")
    topics = repo.get("topics") or []
    if not isinstance(topics, list) or not all(isinstance(t, str) for t in topics):
        raise Unreadable("unexpected GitHub payload: topics is not a list of text")
    owner = repo.get("owner") or {}
    if not isinstance(owner, dict):
        raise Unreadable(f"unexpected GitHub payload: owner is {type(owner).__name__}, not an object")
    login = owner.get("login")
    full_name = _text(repo, "full_name")
    pushed = str(repo.get("pushed_at") or "")[:10] or None

    if not description and not readme.strip():
        # The language and star count alone are not a note worth keeping.
        raise Unreadable(f"the repository has no description or readme: {url}")
    facts = [
        description,
        f"Primary language: {language or 'unknown'}.",
        f"Stars: {repo.get('stargazers_count', 0)}.",
    ]
    if topics:
        facts.append("Topics: " + ", ".join(topics) + ".")
    text = "\n".join(f for f in facts if f.strip())
    if readme.strip():
        text += "\n\n" + readme.strip()

    return Extracted(
        title=full_name or _slug(url) or url,
        text=text,
        type="github",
        source=_host(url),
        author=login if isinstance(login, str) else None,
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


def _as_page(url: str, reason: str | None = None) -> Extracted:
    """Read the URL as an ordinary web page (what a non-repository GitHub URL is)."""
    try:
        return article.from_url(url)
    except NetworkError as error:
        raise Unreadable(f"{reason + '; and ' if reason else ''}could not read {url}: {error}") from error
    except Unreadable as error:
        if reason:
            raise Unreadable(f"{reason}; and as a page: {error}") from error
        raise


def from_url(url: str) -> Extracted:
    slug = _slug(url)
    if slug is None:
        # gist.github.com, docs.github.com, a user page, /features, /orgs/...
        return _as_page(url)

    try:
        repo = json.loads(fetch(f"{API}/{slug}").text)
    except NetworkError as error:
        if error.status == 404:
            # github.com/solutions/ci looks like owner/repo but is a site page.
            return _as_page(url, _explain(error, slug))
        raise Unreadable(_explain(error, slug)) from error
    except ValueError as error:
        raise Unreadable(f"GitHub gave an unreadable answer for {slug}") from error
    if not isinstance(repo, dict):
        raise Unreadable(f"GitHub gave an unexpected answer for {slug}")

    readme = ""
    try:
        payload = json.loads(fetch(f"{API}/{slug}/readme").text)
        readme = base64.b64decode(payload.get("content", "")).decode("utf-8", "replace")
    except NetworkError as error:
        if error.status != 404:    # a repo with no README is normal; a 5xx or a limit is not
            raise Unreadable(_explain(error, slug)) from error
    except (ValueError, AttributeError, binascii.Error):
        readme = ""    # a README we cannot decode: the description still makes a note
    return from_api(repo, readme, url)
