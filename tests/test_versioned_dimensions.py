"""Type 2 versioning on dim_character and dim_boss.

A Type 2 dimension that has never recorded a second version is untested
scaffolding, and the fixtures only ever produce a first version. So this module
edits the reference playbook between two runs of the gold step and asserts what
the dimension did about it.

Three edits, one per case the three passes claim to handle:

  - archer's description changes, which must close version 1 and open version 2
  - minotaur leaves the playbook, which must close its row and open nothing
  - paladin joins it, which must open a first version

The fourth case is the one that breaks quietly: a member nobody touched must
keep exactly one row. A pass that reopens unchanged members looks correct on a
first run and fills the table on every run after it. The final gold run happens
with no edits at all, so idempotence is pinned as well.

`demo.sh` starts with `cd "$(dirname "$0")"`, so the tree it needs is copied to
a temporary directory. That also keeps the repository playbook unedited.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Everything demo.sh reads for `build`, including the committed captures.
NEEDED = ("pipeline", "contracts", "scripts", "fixtures", "demo.sh")


def run(work: pathlib.Path, *args: str) -> None:
    done = subprocess.run(
        ["bash", "./demo.sh", *args],
        cwd=work, capture_output=True, timeout=600,
        encoding="utf-8", errors="replace",
    )
    assert done.returncode == 0, done.stdout + done.stderr


@pytest.fixture(scope="module")
def versioned(tmp_path_factory):
    """Build, edit the playbook, rebuild gold twice."""
    if shutil.which("duckdb") is None:
        pytest.skip("duckdb is not on PATH")
    if shutil.which("bash") is None:
        pytest.skip("bash is not on PATH")

    work = tmp_path_factory.mktemp("versioned")
    for name in NEEDED:
        source = ROOT / name
        target = work / name
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
    (work / "warehouse").mkdir()

    run(work, "build")

    chars = work / "fixtures" / "reference" / "characters.csv"
    text = chars.read_text(encoding="utf-8")
    assert "archer,starting character" in text, text
    chars.write_text(
        text.replace("archer,starting character", "archer,fast glass cannon")
        + "paladin,tank\n",
        encoding="utf-8",
    )

    bosses = work / "fixtures" / "reference" / "boss_kinds.csv"
    lines = bosses.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [ln for ln in lines if not ln.startswith("minotaur,")]
    assert len(kept) == len(lines) - 1, lines
    bosses.write_text("".join(kept), encoding="utf-8")

    run(work, "gold")
    # A second run with nothing changed. Any row this adds is a defect.
    run(work, "gold")
    return work


@pytest.fixture(scope="module")
def rows(versioned):
    """dim_member as plain tuples. It is a table, so no relative path binds."""
    import duckdb

    con = duckdb.connect((versioned / "warehouse" / "flightdeck.duckdb").as_posix(),
                         read_only=True)
    try:
        return con.execute(
            "SELECT dimension, member_key, version_seq, description, "
            "       valid_from, valid_to, is_current "
            "FROM dim_member ORDER BY dimension, member_key, version_seq"
        ).fetchall()
    finally:
        con.close()


def member(rows, dimension: str, key: str) -> list[tuple]:
    return [r for r in rows if r[0] == dimension and r[1] == key]


def test_a_changed_description_opens_a_second_version(rows):
    versions = member(rows, "character", "archer")
    assert [r[2] for r in versions] == [1, 2]
    first, second = versions
    assert first[3] == "starting character"
    assert second[3] == "fast glass cannon"
    assert first[6] is False and first[5] is not None
    assert second[6] is True and second[5] is None


def test_the_old_version_closes_before_the_new_one_opens(rows):
    first, second = member(rows, "character", "archer")
    assert first[5] <= second[4]


def test_a_withdrawn_member_closes_and_opens_nothing(rows):
    versions = member(rows, "boss", "minotaur")
    assert len(versions) == 1
    assert versions[0][6] is False
    assert versions[0][5] is not None


def test_a_new_member_opens_a_first_version(rows):
    versions = member(rows, "character", "paladin")
    assert [r[2] for r in versions] == [1]
    assert versions[0][3] == "tank"
    assert versions[0][6] is True


def test_an_untouched_member_keeps_one_row(rows):
    """Two further gold runs, and knight must still hold a single version."""
    for dimension, key in (("character", "knight"), ("boss", "crowking")):
        versions = member(rows, dimension, key)
        assert [r[2] for r in versions] == [1], (dimension, key, versions)
        assert versions[0][6] is True


def test_every_member_has_at_most_one_current_row(rows):
    current = [(r[0], r[1]) for r in rows if r[6]]
    assert len(current) == len(set(current)), current


def test_the_current_dimension_hides_the_superseded_rows(versioned):
    """dim_character is what the metric views join, so it carries one row each."""
    import duckdb

    con = duckdb.connect((versioned / "warehouse" / "flightdeck.duckdb").as_posix(),
                         read_only=True)
    try:
        chars = dict(con.execute(
            "SELECT character_key, description FROM dim_character").fetchall())
        bosses = [r[0] for r in con.execute("SELECT boss_key FROM dim_boss").fetchall()]
    finally:
        con.close()
    assert chars["archer"] == "fast glass cannon"
    assert chars["paladin"] == "tank"
    assert "minotaur" not in bosses
