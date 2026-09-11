#!/usr/bin/env python3
"""Sanitize flight recorder logs for public distribution.

Two kinds of environment detail do not belong in a public repo. ``ua``
identifies the exact browser build, and any http origin carries the dev server
host and port. The origin scrub walks every string in the record, at any depth,
because a host reaches the log through more fields than a list can track: an
exception message, a log line, a nested payload. Paths, line numbers and column
numbers survive, because they are the evidence.

The script is deterministic and re-runnable: sanitizing an already sanitized
file is a no-op, which is what makes ``--check`` meaningful.

Usage
    sanitize_flightlog.py SRC_DIR DST_DIR    sanitize every *.jsonl
    sanitize_flightlog.py --check DST_DIR    assert DST_DIR is clean
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

# Order matters. An Edge user agent also contains "Chrome/", and Chrome also
# contains "Safari/", so the most specific token has to win.
BROWSER_FAMILIES = (
    ("Edg/", "Edge"),
    ("OPR/", "Opera"),
    ("Firefox/", "Firefox"),
    ("Chrome/", "Chrome"),
    ("Safari/", "Safari"),
)

# Any http(s) origin becomes a bare localhost origin. Paths, line numbers and
# column numbers are preserved, because they are the evidence.
ORIGIN = re.compile(r"https?://[^/\s\"')]+")

# Shapes that must never survive into a published fixture.
#
# Deliberately generic. A cloud sync folder or a machine account name only ever
# appears underneath one of these roots, so naming them individually would add
# nothing except a hardcoded list of the very strings this file exists to keep
# out. Browser build tokens are covered by the user agent family check instead,
# which allows only known families and is stricter than any pattern list.
FORBIDDEN = (
    (re.compile(r"[A-Za-z]:\\"), "Windows drive path"),
    (re.compile(r"/Users/"), "Unix home path"),
    (re.compile(r"/home/"), "Unix home path"),
    (re.compile(r"https?://(?!localhost(?::\d+)?(?:[\s/\"')]|$))[^/\s\"')]+"), "non-local origin"),
)


#: Every value browser_family is allowed to return.
KNOWN_FAMILIES = frozenset(family for _, family in BROWSER_FAMILIES) | {"Other"}


def browser_family(ua: str) -> str:
    """Reduce a full user agent string to a bare browser family name.

    Idempotent. An already trimmed value is returned unchanged, because it no
    longer carries the ``Chrome/`` style token the table matches on and would
    otherwise degrade to ``Other`` on a second pass.
    """
    if ua in KNOWN_FAMILIES:
        return ua
    for token, family in BROWSER_FAMILIES:
        if token in ua:
            return family
    return "Other"


def scrub_origins(text: str) -> str:
    return ORIGIN.sub("http://localhost", text)


def scrub_deep(value):
    """Scrub origins from every string reachable from ``value``.

    Naming the fields to scrub was the earlier design and it leaked. An origin
    in ``err.msg`` reached three published relations, and an origin inside a
    nested event body reached the raw layer, because neither field was on the
    list. Walking the record needs no list to keep current.
    """
    if isinstance(value, str):
        return scrub_origins(value)
    if isinstance(value, dict):
        return {k: scrub_deep(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub_deep(v) for v in value]
    return value


def sanitize_record(rec: dict) -> dict:
    rec = scrub_deep(rec)
    if "ua" in rec:
        rec["ua"] = browser_family(rec["ua"])
    return rec


def check_clean(path: pathlib.Path) -> list[str]:
    """Return a list of violations found in a file. Empty means clean."""
    problems: list[str] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        for pattern, label in FORBIDDEN:
            if pattern.search(line):
                problems.append(f"{path.name}:{lineno}: {label}")
        rec = json.loads(line)
        ua = rec.get("ua")
        if ua is not None and ua not in KNOWN_FAMILIES:
            problems.append(f"{path.name}:{lineno}: un-trimmed ua {ua!r}")
    return problems


def sanitize_dir(src: pathlib.Path, dst: pathlib.Path) -> int:
    dst.mkdir(parents=True, exist_ok=True)
    files = sorted(src.glob("*.jsonl"))
    if not files:
        print(f"no *.jsonl under {src}", file=sys.stderr)
        return 1
    for path in files:
        out_lines = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            out_lines.append(json.dumps(sanitize_record(json.loads(line)),
                                        separators=(",", ":"), sort_keys=False))
        target = dst / path.name
        target.write_text("\n".join(out_lines) + "\n", encoding="utf-8",
                          newline="\n")
        print(f"  {path.name}: {len(out_lines)} records")

    problems = [p for f in sorted(dst.glob("*.jsonl")) for p in check_clean(f)]
    if problems:
        print("\nFAIL, sanitized output still contains:", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1
    print(f"\nclean: {len(files)} files verified after sanitizing")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[1] == "--check":
        target = pathlib.Path(argv[2])
        problems = [p for f in sorted(target.glob("*.jsonl")) for p in check_clean(f)]
        if problems:
            print("FAIL, fixtures are not clean:", file=sys.stderr)
            for p in problems:
                print(f"  {p}", file=sys.stderr)
            return 1
        n = len(list(target.glob("*.jsonl")))
        print(f"ok    {n} fixture files clean")
        return 0
    if len(argv) == 3:
        return sanitize_dir(pathlib.Path(argv[1]), pathlib.Path(argv[2]))
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
