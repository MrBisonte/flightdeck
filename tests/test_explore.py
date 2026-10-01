"""Explore says it carries every published table. This keeps that true.

The list lives in two places: the COPY statements in pipeline/25_publish.sql and
the front matter of site/src/explore.md. Nine tables reached the first and not
the second before this test existed.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_explore_declares_every_published_table():
    publish = (ROOT / "pipeline" / "25_publish.sql").read_text(encoding="utf-8")
    published = set(re.findall(r"TO 'warehouse/curated/(\w+)\.parquet'", publish))
    page = (ROOT / "site" / "src" / "explore.md").read_text(encoding="utf-8")
    front = page.split("---\n")[1]
    declared = set(re.findall(r"^  (\w+): \./data/curated/\1\.parquet$", front, re.MULTILINE))
    assert published, "no COPY target found"
    assert declared == published
