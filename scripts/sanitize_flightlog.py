#!/usr/bin/env python3
"""Sanitize flight recorder logs for public distribution.

Two kinds of environment detail do not belong in a public repo. ``ua``
identifies the exact browser build, and an http origin carries the host and the
port that served the page. Both walks below visit every string in the record,
at any depth, because a host reaches the log through more fields than a list
can track: an exception message, a log line, a nested payload. Paths, line
numbers and column numbers survive, because they are the evidence.

An origin takes one of two routes, and the caller picks which.

``scrub_origins`` rewrites every origin to ``http://localhost``. The fixtures
under ``fixtures/raw`` take this route. That directory sits in a public repo,
so it is already published and carries no origin at all.

``mask_origins`` keeps an origin that ``fixtures/reference/origins.csv`` lists
and masks every other one down to its class. A live capture takes this route,
because the origin a session came from is data worth keeping. The allowlist
fails closed. An origin nobody listed is masked, never passed through, which is
the property a denylist cannot offer. See DEF-13 in ``docs/defect-log.md``.

The script is deterministic and re-runnable: sanitizing an already sanitized
file is a no-op, which is what makes ``--check`` meaningful.

Usage
    sanitize_flightlog.py SRC_DIR DST_DIR          rewrite every origin
    sanitize_flightlog.py --live SRC_DIR DST_DIR   keep a listed origin
    sanitize_flightlog.py --check DST_DIR          assert DST_DIR is clean
"""
from __future__ import annotations

import csv
import functools
import json
import pathlib
import re
import sys

#: The known origins, one row each, with the class and the publish decision.
#: pipeline/10_typed.sql reads the same file, so the two can never drift.
REFERENCE = (pathlib.Path(__file__).resolve().parents[1]
             / "fixtures" / "reference" / "origins.csv")

# Order matters. An Edge user agent also contains "Chrome/", and Chrome also
# contains "Safari/", so the most specific token has to win.
BROWSER_FAMILIES = (
    ("Edg/", "Edge"),
    ("OPR/", "Opera"),
    ("Firefox/", "Firefox"),
    ("Chrome/", "Chrome"),
    ("Safari/", "Safari"),
)

# Any http(s) origin. Paths, line numbers and column numbers sit after the
# first slash and are preserved, because they are the evidence.
ORIGIN = re.compile(r"https?://[^/\s\"')]+")

#: The one origin the hard scrub can produce, so the one a fixture may carry.
LOCALHOST = "http://localhost"
FIXTURE_ORIGINS = frozenset({LOCALHOST})

#: What an origin the reference does not list becomes.
#:
#: One mask, not one per class. Classifying an unlisted origin would mean
#: guessing from its host name and then publishing the guess, and an origin
#: nobody listed is precisely the one nothing is known about. `.invalid` is
#: reserved by RFC 2606, so a mask can never collide with a real host. The mask
#: is itself a row in the reference, which keeps one rule for the gate and one
#: join for the pipeline rather than a special case in each.
MASK = "http://masked.invalid"

# Shapes that must never survive into a published fixture.
#
# Deliberately generic. A cloud sync folder or a machine account name only ever
# appears underneath one of these roots, so naming them individually would add
# nothing except a hardcoded list of the very strings this file exists to keep
# out. Browser build tokens are covered by the user agent family check instead,
# which allows only known families and is stricter than any pattern list.
#
# Origins are not here. They are checked against an allowlist rather than a
# pattern, because the answer depends on the reference file and not on shape.
FORBIDDEN = (
    (re.compile(r"[A-Za-z]:\\"), "Windows drive path"),
    (re.compile(r"/Users/"), "Unix home path"),
    (re.compile(r"/home/"), "Unix home path"),
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


@functools.lru_cache(maxsize=1)
def listed_origins() -> frozenset[str]:
    """Every origin the reference names. The allowlist, read once."""
    with REFERENCE.open(encoding="utf-8", newline="") as fh:
        return frozenset(row["origin"] for row in csv.DictReader(fh))


def scrub_origins(text: str) -> str:
    """Rewrite every origin to localhost. The rule for a committed fixture."""
    return ORIGIN.sub(LOCALHOST, text)


def mask_origins(text: str) -> str:
    """Keep a listed origin, mask the rest. The rule for a live capture."""
    allowed = listed_origins()
    return ORIGIN.sub(lambda m: m.group(0) if m.group(0) in allowed else MASK, text)


def scrub_deep(value, rewrite=scrub_origins):
    """Apply ``rewrite`` to every string reachable from ``value``.

    Naming the fields to scrub was the earlier design and it leaked. An origin
    in ``err.msg`` reached three published relations, and an origin inside a
    nested event body reached the raw layer, because neither field was on the
    list. Walking the record needs no list to keep current.
    """
    if isinstance(value, str):
        return rewrite(value)
    if isinstance(value, dict):
        return {k: scrub_deep(v, rewrite) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub_deep(v, rewrite) for v in value]
    return value


def sanitize_record(rec: dict, rewrite=scrub_origins) -> dict:
    """Sanitize one record. The default rewrite is the stricter of the two, so
    a caller that never chooses gets the scrub rather than the allowlist."""
    rec = scrub_deep(rec, rewrite)
    if "ua" in rec:
        rec["ua"] = browser_family(rec["ua"])
    return rec


def check_clean(path: pathlib.Path, allowed=FIXTURE_ORIGINS) -> list[str]:
    """Return a list of violations found in a file. Empty means clean.

    ``allowed`` is the set of origins this file may carry. A committed fixture
    may carry only the scrub output; a live capture may carry anything the
    reference lists. Every other origin is a violation, which is default-deny
    stated as a gate.
    """
    problems: list[str] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        for pattern, label in FORBIDDEN:
            if pattern.search(line):
                problems.append(f"{path.name}:{lineno}: {label}")
        # dict.fromkeys, so a line repeating one origin reports it once.
        for origin in dict.fromkeys(ORIGIN.findall(line)):
            if origin not in allowed:
                problems.append(f"{path.name}:{lineno}: unlisted origin {origin}")
        rec = json.loads(line)
        ua = rec.get("ua")
        if ua is not None and ua not in KNOWN_FAMILIES:
            problems.append(f"{path.name}:{lineno}: un-trimmed ua {ua!r}")
    return problems


def sanitize_dir(src: pathlib.Path, dst: pathlib.Path, rewrite, allowed) -> int:
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
            out_lines.append(json.dumps(sanitize_record(json.loads(line), rewrite),
                                        separators=(",", ":"), sort_keys=False))
        target = dst / path.name
        target.write_text("\n".join(out_lines) + "\n", encoding="utf-8",
                          newline="\n")
        print(f"  {path.name}: {len(out_lines)} records")

    problems = [p for f in sorted(dst.glob("*.jsonl")) for p in check_clean(f, allowed)]
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
    if len(argv) == 4 and argv[1] == "--live":
        return sanitize_dir(pathlib.Path(argv[2]), pathlib.Path(argv[3]),
                            mask_origins, listed_origins())
    if len(argv) == 3:
        return sanitize_dir(pathlib.Path(argv[1]), pathlib.Path(argv[2]),
                            scrub_origins, FIXTURE_ORIGINS)
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
