#!/usr/bin/env python3
"""Check Markdown prose against Simplified Technical English rules.

STE keeps technical writing readable. This script checks the rules that a
machine can check:

  1. Sentence length. A descriptive sentence uses 25 words or fewer.
  2. Passive voice. STE prefers the active voice.
  3. Paragraph length. A paragraph uses 6 sentences or fewer.

The script skips code blocks, tables, headings, and link definitions. Prose is
the target, not data.

Usage
    check_ste.py FILE [FILE ...]      report problems
    check_ste.py --max-words N FILE   change the sentence limit
"""
from __future__ import annotations

import argparse
import pathlib
import re

MAX_WORDS = 25
MAX_SENTENCES_PER_PARAGRAPH = 6

#: "is written", "was found", "are dropped". A rough but useful signal.
PASSIVE = re.compile(
    r"\b(is|are|was|were|be|been|being)\s+(?:\w+ly\s+)?(\w+(?:ed|en))\b",
    re.IGNORECASE,
)

#: Past participles that read as adjectives, not as passive voice.
PASSIVE_ALLOWED = {
    "based", "used", "named", "typed", "documented", "committed", "recorded",
    "related", "detailed", "limited", "fixed", "closed", "open", "hidden",
    "needed", "required", "supposed", "advanced", "involved",
}

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def prose_lines(text: str) -> list[tuple[int, str]]:
    """Return (line number, line) for prose only."""
    out: list[tuple[int, str]] = []
    in_code = False
    for n, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if not stripped:
            out.append((n, ""))               # blank: a paragraph boundary
            continue
        if stripped.startswith("#"):          # heading
            out.append((n, ""))
            continue
        if stripped.startswith("|"):          # table
            out.append((n, ""))
            continue
        if stripped.startswith(">"):          # quote
            out.append((n, ""))
            continue
        if set(stripped) <= set("-|: "):      # table rule
            out.append((n, ""))
            continue
        out.append((n, stripped))
    return out


def sentences(line: str) -> list[str]:
    # Protect common abbreviations that end in a period.
    guarded = line.replace("e.g.", "eg").replace("i.e.", "ie")
    return [s for s in SENTENCE_END.split(guarded) if s.strip()]


def word_count(sentence: str) -> int:
    without_code = re.sub(r"`[^`]*`", "X", sentence)
    without_links = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", without_code)
    return len(re.findall(r"[A-Za-z0-9_'-]+", without_links))


def paragraphs(text: str) -> list[tuple[int, str]]:
    """Group prose lines into paragraphs.

    Markdown wraps a sentence across lines. Checking line by line would split
    one long sentence into two short fragments and miss it, so the lines of a
    paragraph are joined before any check runs.
    """
    out: list[tuple[int, str]] = []
    buffer: list[str] = []
    start = 0
    for n, line in prose_lines(text) + [(0, "")]:
        if line:
            if not buffer:
                start = n
            buffer.append(line)
            continue
        if buffer:
            out.append((start, " ".join(buffer)))
            buffer = []
    return out


def check(path: pathlib.Path, max_words: int) -> list[str]:
    text = path.read_text(encoding="utf-8")
    problems: list[str] = []

    for line_no, paragraph in paragraphs(text):
        found = sentences(paragraph)

        if len(found) > MAX_SENTENCES_PER_PARAGRAPH:
            problems.append(
                f"{path}:{line_no}: paragraph has {len(found)} sentences "
                f"(limit {MAX_SENTENCES_PER_PARAGRAPH})"
            )

        for sentence in found:
            count = word_count(sentence)
            if count > max_words:
                preview = sentence[:70].rstrip()
                problems.append(
                    f"{path}:{line_no}: {count} words (limit {max_words}): {preview}..."
                )

            for match in PASSIVE.finditer(sentence):
                if match.group(2).lower() in PASSIVE_ALLOWED:
                    continue
                problems.append(
                    f"{path}:{line_no}: passive voice '{match.group(0)}': "
                    f"{sentence[:60].rstrip()}..."
                )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=pathlib.Path)
    parser.add_argument("--max-words", type=int, default=MAX_WORDS)
    parser.add_argument("--quiet", action="store_true",
                        help="print the count only")
    args = parser.parse_args()

    all_problems: list[str] = []
    for path in args.files:
        all_problems.extend(check(path, args.max_words))

    if all_problems:
        if not args.quiet:
            for problem in all_problems:
                print(problem)
        print(f"\n{len(all_problems)} STE problems in {len(args.files)} files")
        return 1

    print(f"ok    {len(args.files)} files pass the STE checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
