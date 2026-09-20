"""The colours on this site that carry text, checked against WCAG AA.

`--amber-ink` paints every table header, and `--amber-soft` over `--panel` is
the background behind it. That pair is the one that has already failed once:
the dashboard accent read 4.35:1 against it and missed the 4.5:1 floor for text
below 18.66px, and table headers here are 13px.

Both views are checked, because both now own their palette. Engineering is dark
and dashboard is light, so the same token name means a different colour in each
and neither can be assumed to inherit the other's result.

A browser is the only honest way to measure a rendered page, and CI has no
browser. Every value is a literal in one file, so the ratio can be checked
without one.
"""
from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CSS = ROOT / "site" / "src" / "components" / "presentation.css"

#: WCAG 2.1 AA, text under 18.66px or under 24px when it is not bold.
FLOOR = 4.5

#: The selector that opens each view's token block.
VIEWS = {
    "engineering": 'html:not([data-view="dashboard"]) {',
    "dashboard": 'html[data-view="dashboard"] {',
}


def block(view: str) -> str:
    """The token declarations for one view, and nothing else."""
    text = CSS.read_text(encoding="utf-8")
    start = text.index(VIEWS[view]) + len(VIEWS[view])
    return text[start:text.index("}", start)]


def token(view: str, name: str, over: tuple[int, int, int] | None = None):
    """One token as RGB. A translucent value is composited over `over`.

    An alpha token has no colour of its own. Reading its literal and calling it
    a background is how a tinted table header gets checked against the wrong
    surface, so the base has to be named at the call site.
    """
    declarations = block(view)
    hexed = re.search(rf"^\s*--{name}:\s*#([0-9a-fA-F]{{6}});", declarations, re.MULTILINE)
    if hexed:
        value = hexed.group(1)
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
    rgba = re.search(
        rf"^\s*--{name}:\s*rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\);",
        declarations, re.MULTILINE)
    assert rgba, f"--{name} is not a plain colour literal in the {view} block"
    assert over is not None, f"--{name} is translucent, so a base is required"
    r, g, b, alpha = int(rgba[1]), int(rgba[2]), int(rgba[3]), float(rgba[4])
    return tuple(round(alpha * c + (1 - alpha) * base)
                 for c, base in zip((r, g, b), over))


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


@pytest.mark.parametrize("view", sorted(VIEWS))
@pytest.mark.parametrize("surface", ["ground", "panel"])
def test_the_accent_carries_text_at_aa(view, surface):
    ratio = contrast(token(view, "amber-ink"), token(view, surface))
    assert ratio >= FLOOR, f"{view}: --amber-ink on --{surface} is {ratio:.2f}:1"


@pytest.mark.parametrize("view", sorted(VIEWS))
def test_the_accent_carries_a_table_header_at_aa(view):
    """The pair that failed before. The header tint is alpha over the panel."""
    header = token(view, "amber-soft", over=token(view, "panel"))
    ratio = contrast(token(view, "amber-ink"), header)
    assert ratio >= FLOOR, f"{view}: --amber-ink on the table header is {ratio:.2f}:1"


@pytest.mark.parametrize("view", sorted(VIEWS))
@pytest.mark.parametrize("surface", ["ground", "panel"])
def test_muted_prose_reads_at_aa(view, surface):
    """--muted is body text in both views, not decoration."""
    ratio = contrast(token(view, "muted"), token(view, surface))
    assert ratio >= FLOOR, f"{view}: --muted on --{surface} is {ratio:.2f}:1"


@pytest.mark.parametrize("view, ink", [("engineering", "ground"), ("dashboard", "ink")])
def test_the_pressed_switch_reads_at_aa(view, ink):
    """The one solid accent fill on the site. Its ink is named, not inherited.

    Each view names the dark token it has: engineering paints the button ink
    with its ground, dashboard with its foreground. White fails here, which is
    what the pair exists to catch.
    """
    ratio = contrast(token(view, ink), token(view, "amber"))
    assert ratio >= FLOOR, f"{view}: the pressed switch reads {ratio:.2f}:1"


def test_one_home_for_the_accent():
    """Framework's focus token points at the accent instead of repeating it."""
    text = CSS.read_text(encoding="utf-8")
    assert "--theme-foreground-focus: var(--amber-ink);" in text
