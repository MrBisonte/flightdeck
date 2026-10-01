"""Type 2 versioning on dim_character and dim_boss, from declared dates.

characters.csv and boss_kinds.csv hold one row per version, and each row
declares the dates it was valid. The committed files only carry first versions,
so this module writes a longer history into a copy of the tree and asserts what
the dimension builds from it:

  - archer gains a second version, which opens on the date the first one closes
  - minotaur is withdrawn, so its only version closes and nothing opens
  - paladin joins, which opens a first version

Two more properties come from the dates living in committed files rather than in
the database. A rebuild from an empty warehouse, which is what every Pages
deploy does, must produce the same history. And every committed file must be a
history the pipeline can read without ambiguity.

`demo.sh` starts with `cd "$(dirname "$0")"`, so the tree it needs is copied to
a temporary directory. That also keeps the repository files unedited.
"""
from __future__ import annotations

import csv
import datetime as dt
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "fixtures" / "reference"

#: Everything demo.sh reads for `build`, including the committed captures.
NEEDED = ("pipeline", "contracts", "scripts", "fixtures", "demo.sh")

#: The versioned reference files and the column that keys each one.
VERSIONED = {"characters.csv": "char", "boss_kinds.csv": "boss"}

#: The earliest fact in the fixtures. Every first version must start before it,
#: or an as-of join from that fact finds nothing.
FIRST_FACT = dt.datetime(2026, 8, 30, tzinfo=dt.timezone.utc)


def parse(stamp: str) -> dt.datetime | None:
    return dt.datetime.fromisoformat(stamp.replace("Z", "+00:00")) if stamp else None


@pytest.mark.parametrize("name", sorted(VERSIONED))
def test_the_committed_file_is_a_readable_history(name):
    """At most one open version per member, no two versions of a member in force
    at once, and every version ends after it starts."""
    key = VERSIONED[name]
    with (REFERENCE / name).open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    by_member: dict[str, list[tuple]] = {}
    for row in rows:
        start, end = parse(row["valid_from"]), parse(row["valid_to"])
        assert start is not None, row
        assert end is None or end > start, row
        by_member.setdefault(row[key], []).append((start, end))
    for member, versions in by_member.items():
        versions.sort()
        assert sum(1 for _, end in versions if end is None) <= 1, member
        for (_, end), (start, _) in zip(versions, versions[1:]):
            assert end is not None and end <= start, member
        assert versions[0][0] < FIRST_FACT, member


def run(work: pathlib.Path, *args: str) -> None:
    done = subprocess.run(
        ["bash", "./demo.sh", *args],
        cwd=work, capture_output=True, timeout=600,
        encoding="utf-8", errors="replace",
    )
    assert done.returncode == 0, done.stdout + done.stderr


def copy_tree(work: pathlib.Path) -> pathlib.Path:
    for name in NEEDED:
        source = ROOT / name
        target = work / name
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
    (work / "warehouse").mkdir()
    return work


def query(work: pathlib.Path, sql: str) -> list[tuple]:
    """Timestamps arrive as epoch milliseconds. Handing a TIMESTAMP WITH TIME
    ZONE to Python makes the DuckDB driver import pytz, which this project does
    not depend on."""
    import duckdb

    con = duckdb.connect((work / "warehouse" / "flightdeck.duckdb").as_posix(),
                         read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


HISTORY = (
    "SELECT dimension, member_key, version_seq, description, "
    "       epoch_ms(valid_from), epoch_ms(valid_to), is_current "
    "FROM dim_member ORDER BY dimension, member_key, version_seq"
)
CAPS = (
    "SELECT cap_key, cap_value, epoch_ms(valid_from), epoch_ms(valid_to), is_current "
    "FROM dim_contract_cap ORDER BY cap_key, valid_from"
)


@pytest.fixture(scope="module")
def tools():
    if shutil.which("duckdb") is None:
        pytest.skip("duckdb is not on PATH")
    if shutil.which("bash") is None:
        pytest.skip("bash is not on PATH")


@pytest.fixture(scope="module")
def versioned(tools, tmp_path_factory):
    """Declare a second history in a copy of the tree, then build it."""
    work = copy_tree(tmp_path_factory.mktemp("versioned"))

    chars = work / "fixtures" / "reference" / "characters.csv"
    text = chars.read_text(encoding="utf-8")
    first = "archer,starting character,2026-07-19T22:24:09Z,"
    assert first in text, text
    chars.write_text(
        text.replace(first, first + "2026-09-20T00:00:00Z")
        + "archer,fast glass cannon,2026-09-20T00:00:00Z,\n"
        + "paladin,tank,2026-09-21T00:00:00Z,\n",
        encoding="utf-8",
    )

    bosses = work / "fixtures" / "reference" / "boss_kinds.csv"
    text = bosses.read_text(encoding="utf-8")
    minotaur = "minotaur,labyrinth warden,2026-08-22T12:19:46Z,"
    assert minotaur in text, text
    bosses.write_text(text.replace(minotaur, minotaur + "2026-09-22T00:00:00Z"),
                      encoding="utf-8")

    run(work, "build")
    return work


@pytest.fixture(scope="module")
def rows(versioned):
    return query(versioned, HISTORY)


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


def test_the_old_version_closes_when_the_new_one_opens(rows):
    first, second = member(rows, "character", "archer")
    assert first[5] == second[4]


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
    for dimension, key in (("character", "knight"), ("boss", "crowking")):
        versions = member(rows, dimension, key)
        assert [r[2] for r in versions] == [1], (dimension, key, versions)
        assert versions[0][6] is True


def test_the_current_dimension_hides_the_superseded_rows(versioned):
    """dim_character is what the metric views join, so it carries one row each."""
    chars = dict(query(versioned, "SELECT character_key, description FROM dim_character"))
    bosses = [r[0] for r in query(versioned, "SELECT boss_key FROM dim_boss")]
    assert chars["archer"] == "fast glass cannon"
    assert chars["paladin"] == "tank"
    assert "minotaur" not in bosses


def test_a_withdrawn_member_leaves_the_checked_domain(versioned, monkeypatch):
    """ref_bosses is what the typed layer checks a pulse against. A withdrawn
    boss leaves it, exactly as deleting the row used to. The view reads its file
    by a relative path, so the query runs from the copied tree."""
    monkeypatch.chdir(versioned)
    bosses = [r[0] for r in query(versioned, "SELECT boss FROM ref_bosses")]
    assert "minotaur" not in bosses
    assert len(bosses) == 3


def test_a_rebuild_from_nothing_reproduces_the_history(tools, tmp_path_factory):
    """The Pages deploy starts from an empty warehouse every time. Two such
    builds must agree on every version and every date."""
    builds = []
    for name in ("first", "second"):
        work = copy_tree(tmp_path_factory.mktemp(name))
        run(work, "build")
        builds.append((query(work, HISTORY), query(work, CAPS)))
    assert builds[0] == builds[1]
    history, caps = builds[0]
    assert len(history) == 9 and all(r[2] == 1 for r in history)
    assert len(caps) == 5
