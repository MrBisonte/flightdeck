"""Tests for the prose selection in the STE checker.

The checker measures prose. Its docstring says it skips data: code blocks,
tables, headings, and link definitions. YAML front matter is data too. A page
that registers five data sources read as one 28 word sentence before this.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from check_ste import MAX_WORDS, check

FRONT_MATTER = """---
title: Overview
sql:
  contract_reconciliation: ./data/curated/contract_reconciliation.parquet
  warehouse_manifest: ./data/curated/warehouse_manifest.parquet
  loss_accounting: ./data/curated/loss_accounting.parquet
  alarms_by_class: ./data/curated/alarms_by_class.parquet
  error_report: ./data/curated/error_report.parquet
---
"""

LONG_SENTENCE = " ".join(["word"] * 30) + "."


def write(tmp_path: pathlib.Path, text: str) -> pathlib.Path:
    path = tmp_path / "page.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_front_matter_is_not_prose(tmp_path):
    """Five data sources must not read as one long sentence."""
    page = write(tmp_path, FRONT_MATTER + "\nThe page is short and clear.\n")
    assert check(page, MAX_WORDS) == []


def test_prose_after_front_matter_is_still_checked(tmp_path):
    """Skipping the front matter must not skip the body behind it."""
    page = write(tmp_path, FRONT_MATTER + "\n" + LONG_SENTENCE + "\n")
    problems = check(page, MAX_WORDS)
    assert len(problems) == 1
    assert "30 words" in problems[0]


def test_leading_rule_without_a_close_keeps_the_body(tmp_path):
    """A document that opens with a rule, and never closes it, stays checked."""
    page = write(tmp_path, "---\n\n" + LONG_SENTENCE + "\n")
    assert len(check(page, MAX_WORDS)) == 1
