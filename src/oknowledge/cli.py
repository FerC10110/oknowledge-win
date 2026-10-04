"""The front door. The Omarchy plugin talks to the system through here.

Messages are in English: they are answers for people at a terminal and for
scripts, not interface text. With --json, a command prints exactly one JSON
document on stdout (an object for `add`, an array for `status` and `retry`),
so a caller can parse the whole output in one go. Anything the user should
know that is not the answer (warnings, errors) goes to stderr.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from .config import CONFIG_PATH, ConfigError
from .config import load as load_config
from .pipeline import Result, add, retry
from .queue import Queue
from .vault import all_notes, rebuild_indexes

NO_CONFIG = """\
no config file at {path}

Create it with at least a line pointing at your Obsidian vault:

    vault = "/path/to/your/obsidian/vault"

Everything else has a default. Notes are written to <vault>/oknowledge/."""


def _result_dict(result: Result) -> dict:
    data = dataclasses.asdict(result)
    data["path"] = str(result.path) if result.path else None
    return data


def _entry_dict(entry) -> dict:
    data = dataclasses.asdict(entry)
    # An entry's `content` is the mode that was asked for last, which after a
    # refused re-analysis is not what the note holds. Say so in the name.
    data["requested_content"] = data.pop("content")
    return data


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oknowledge")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    subs = parser.add_subparsers(dest="command")

    add_cmd = subs.add_parser("add", help="save a link")
    add_cmd.add_argument("url")
    group = add_cmd.add_mutually_exclusive_group()
    group.add_argument("--full", action="store_true", help="keep the original text")
    group.add_argument("--summary", action="store_true", help="keep only the summary")
    add_cmd.add_argument("--engine", help="force one engine for this link")
    add_cmd.add_argument("--reprocess", action="store_true")
    add_cmd.add_argument("--json", action="store_true")

    status = subs.add_parser("status", help="what is pending or failed")
    status.add_argument("--json", action="store_true")

    subs.add_parser("reindex", help="rebuild the category indexes")

    retry_cmd = subs.add_parser("retry", help="finish the links left half done")
    retry_cmd.add_argument("--json", action="store_true")
    return parser


def _warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def _add(cfg, args) -> int:
    content = "summary" if args.summary else ("full" if args.full else None)
    result = add(cfg, args.url, content=content, engine=args.engine,
                 reprocess=args.reprocess)
    if args.json:
        print(json.dumps(_result_dict(result), ensure_ascii=False))
    else:
        if result.skipped:
            print(f"already saved: {result.path}")
        elif result.status == "ok":
            print(f"saved: {result.path}")
        elif result.status == "pending" and result.path is None:
            # The pipeline's answer to a link somebody else holds the lock on.
            print("another process is working on this link, try again in a moment",
                  file=sys.stderr)
        else:
            print(f"saved incomplete ({result.error}): {result.path}", file=sys.stderr)
        for warning in result.warnings:
            _warn(warning)
    return 0 if result.status == "ok" or result.skipped else 1


def _status(cfg, args) -> int:
    entries = Queue().entries()
    if args.json:
        print(json.dumps([_entry_dict(e) for e in entries], ensure_ascii=False))
        return 0
    print(f"{len(all_notes(cfg))} notes")
    # Only the entry's status says whether it needs attention: an `ok` entry can
    # carry the error of a re-analysis that was refused, with its note intact.
    for entry in entries:
        if entry.status != "ok":
            line = f"  {entry.status:8} {entry.title or entry.url}"
            if entry.error:
                line += f" ({entry.error})"
            print(line)
    return 0


def _reindex(cfg) -> int:
    result = rebuild_indexes(cfg, cfg.language)
    print(f"{len(result.written)} indexes rewritten")
    for path in result.blocked:
        print(f"not written: {path} is a file that is not ours, so it was left alone; "
              "rename or move it to get this index", file=sys.stderr)
    for path in result.skipped:
        print(f"could not be read: {path} is one of our notes but its header is "
              "broken, so it is missing from every index until it is fixed",
              file=sys.stderr)
    return 0


def _retry(cfg, args) -> int:
    results = retry(cfg)
    if args.json:
        print(json.dumps([_result_dict(r) for r in results], ensure_ascii=False))
    else:
        done = sum(1 for r in results if r.status == "ok")
        print(f"{done}/{len(results)} finished")
        for r in results:
            if r.status != "ok":
                print(f"  {r.status:8} {r.url}: {r.error}")
    return 0 if all(r.status == "ok" for r in results) else 1


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help(sys.stderr)
        return 2

    try:
        cfg = load_config(args.config)
    except ConfigError as error:
        message = NO_CONFIG.format(path=args.config) if not args.config.exists() else error
        print(f"oknowledge: {message}", file=sys.stderr)
        return 2

    try:
        if args.command == "add":
            return _add(cfg, args)
        if args.command == "status":
            return _status(cfg, args)
        if args.command == "reindex":
            return _reindex(cfg)
        if args.command == "retry":
            return _retry(cfg, args)
    except OSError as error:
        print(f"oknowledge: {error}", file=sys.stderr)
        return 1
    return 2
