"""The one colour on this site that carries text on a tinted background.

`--dash-accent` paints every table header, and `--dash-accent-soft` is the
background behind it. The pair read 4.35:1, which misses the WCAG AA floor of
4.5:1 for text below 18.66px. Table headers here are 13px.

A browser is the only honest way to measure a rendered page, and CI has no
browser. The two values are plain literals in one file, so the ratio can be
checked without one.
"""
from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CSS = ROOT / "site" / "src" / "components" / "presentation.css"

#: WCAG 2.1 AA, text under 18.66px or under 24px when it is not bold.
FLOOR = 4.5


def token(name: str) -> tuple[int, int, int]:
    text = CSS.read_text(encoding="utf-8")
    match = re.search(rf"^\s*--{name}:\s*#([0-9a-fA-F]{{6}});", text, re.MULTILINE)
    assert match, f"--{name} is no longer a plain hex literal in {CSS.name}"
    value = match.group(1)
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def luminance(rgb: tuple[int, int, int]) -> float:
    channels = []
    for raw in rgb:
        v = raw / 255
        channels.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    lighter, darker = sorted((luminance(a), luminance(b)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.parametrize("background", ["dash-accent-soft", "dash-bg", "dash-card"])
def test_the_accent_carries_text_at_aa(background):
    ratio = contrast(token("dash-accent"), token(background))
    assert ratio >= FLOOR, f"--dash-accent on --{background} is {ratio:.2f}:1"


def test_one_home_for_the_accent():
    """Framework's focus token points at the accent instead of repeating it."""
    text = CSS.read_text(encoding="utf-8")
    assert "--theme-foreground-focus: var(--dash-accent);" in text
