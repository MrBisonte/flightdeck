"""The `--live` flag, end to end.

Three of the twelve logged defects came from this path and none of them had a
test. DEF-08 broke the path outright, DEF-09 typed a real client id wrongly,
and DEF-12 let a live capture reach the output unsanitized.

These tests run the real `demo.sh` against a synthetic capture that looks like
a live one: the new wire format with a real client id, a full user agent, and a
dev server origin in the fields a scrub that names its fields would miss.

`demo.sh` starts with `cd "$(dirname "$0")"`, so it always runs from the
directory holding it. The whole tree it needs is therefore copied into a
temporary directory, which keeps the repository warehouse out of reach.
"""
from __future__ import annotations

import contextlib
import json
import os
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: A private address is easier to spot in a failure message than a hostname.
DEV_ORIGIN = "http://192.168.1.50:5173"
CID = "3f2a1c88-9b4e-4d21-8f7a-5c6d0e1b2a34"
FULL_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.3537.57")

#: Everything demo.sh reads for `build`. The raw fixtures are not among them,
#: because `--live` replaces that source.
NEEDED = ("pipeline", "contracts", "scripts", "demo.sh")


def _pulse(t: int, kills: int) -> dict:
    return {"state": "playing", "mode": "brawl", "map": "forest",
            "char": "archer", "t": t, "lastTs": t * 1000, "live": True,
            "held": 0, "hp": 9, "kills": kills, "crows": 0, "skels": 0,
            "soldiers": 0, "arrows": 0, "boss": None}


def capture(first_srv: int, beats: int) -> list[dict]:
    """One page load carrying a dev origin in four different fields."""
    srv = first_srv
    records = [{"kind": "hello", "cid": CID, "wall": srv,
                "href": DEV_ORIGIN + "/crow-archer/", "ua": FULL_UA,
                "dpr": 1, "srv": srv}]
    for i in range(1, beats + 1):
        srv += 1000
        events = []
        if i == 2:
            events = [{"id": 1, "level": "warn", "timestamp": srv, "source": "net",
                       "message": "asset fetch failed from " + DEV_ORIGIN + "/assets/crow.png",
                       "data": {"url": DEV_ORIGIN + "/assets/crow.png"}}]
        records.append({"kind": "beat", "cid": CID, "wall": srv, "perf": i * 1000,
                        "raf": 60, "vis": "visible", "pulse": _pulse(i, i),
                        "events": events, "dropped": 0, "srv": srv})
    srv += 1000
    records.append({"kind": "err", "cid": CID, "wall": srv,
                    "msg": "Uncaught TypeError: failed to load " + DEV_ORIGIN + "/src/game.ts",
                    "stack": "TypeError: x is undefined\n    at update ("
                             + DEV_ORIGIN + "/src/game.ts:67:30)",
                    "events": [], "srv": srv})
    srv += 1000
    records.append({"kind": "bye", "cid": CID, "wall": srv, "events": [], "srv": srv})
    return records


def write_log(path: pathlib.Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")


@pytest.fixture(scope="module")
def live_run(tmp_path_factory):
    """Run `demo.sh --live DIR build` once, in an isolated copy of the tree."""
    if shutil.which("duckdb") is None:
        pytest.skip("duckdb is not on PATH")
    if shutil.which("bash") is None:
        pytest.skip("bash is not on PATH")

    work = tmp_path_factory.mktemp("live")
    for name in NEEDED:
        source = ROOT / name
        target = work / name
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
    shutil.copytree(ROOT / "fixtures" / "reference", work / "fixtures" / "reference")
    (work / "warehouse").mkdir()

    source_dir = work / "captures"
    # Two captures, so "newest wins" has something to choose between. The older
    # one carries twice the beats, which makes the wrong choice obvious.
    older = source_dir / "session-2026-09-11T08-00-00-000Z.jsonl"
    newer = source_dir / "session-2026-09-11T09-00-00-000Z.jsonl"
    write_log(older, capture(1_789_000_000_000, beats=9))
    write_log(newer, capture(1_789_100_000_000, beats=3))
    # demo.sh picks with `ls -1t`, which sorts on the modification time. Two
    # files written in the same instant tie, and the tie breaks arbitrarily, so
    # the times are set apart here rather than left to the filesystem clock.
    os.utime(older, (1_000_000, 1_000_000))
    os.utime(newer, (2_000_000, 2_000_000))

    done = subprocess.run(
        ["bash", "./demo.sh", "--live", str(source_dir), "build"],
        cwd=work, capture_output=True, timeout=600,
        encoding="utf-8", errors="replace",
    )
    assert done.returncode == 0, done.stdout + done.stderr
    return work


@contextlib.contextmanager
def warehouse(run: pathlib.Path):
    """Open the run's database with the run as the working directory.

    The curated views wrap `read_parquet('warehouse/raw/**/*.parquet')`, a
    relative path. Reading them from anywhere else re-binds them against
    another warehouse and DuckDB reports the view as altered.
    """
    import duckdb

    previous = os.getcwd()
    os.chdir(run)
    con = duckdb.connect("warehouse/flightdeck.duckdb", read_only=True)
    try:
        yield con
    finally:
        con.close()
        os.chdir(previous)


def test_an_empty_capture_directory_fails_with_a_reason(tmp_path):
    if shutil.which("bash") is None:
        pytest.skip("bash is not on PATH")
    empty = tmp_path / "empty"
    empty.mkdir()
    done = subprocess.run(
        ["bash", str(ROOT / "demo.sh"), "--live", str(empty), "build"],
        capture_output=True, timeout=120,
        encoding="utf-8", errors="replace",
    )
    assert done.returncode != 0
    assert "no *.jsonl under" in done.stderr


def test_the_newest_capture_wins(live_run):
    """One page load, from the later file. The older file has nine beats."""
    with warehouse(live_run) as con:
        sessions, beats = con.execute(
            "SELECT count(*), (SELECT count(*) FROM beats) FROM sessions").fetchone()
    assert sessions == 1
    assert beats == 3


def test_the_contract_reconciles_on_a_live_capture(live_run):
    with warehouse(live_run) as con:
        landed, clean, quarantined, reconciles = con.execute(
            "SELECT landed_records, clean_records, quarantined_records, reconciles "
            "FROM contract_reconciliation").fetchone()
    assert reconciles is True
    assert landed == clean + quarantined


def test_no_published_file_carries_the_dev_origin(live_run):
    """DEF-12, pinned. The scrub runs before the pipeline reads the capture."""
    carriers = [p.name for p in sorted((live_run / "warehouse" / "curated").glob("*.parquet"))
                if DEV_ORIGIN.encode() in p.read_bytes()]
    assert carriers == []


def test_no_raw_partition_carries_the_dev_origin(live_run):
    carriers = [str(p) for p in (live_run / "warehouse" / "raw").rglob("*.parquet")
                if DEV_ORIGIN.encode() in p.read_bytes()]
    assert carriers == []


def test_the_full_user_agent_never_lands(live_run):
    with warehouse(live_run) as con:
        agents = [row[0] for row in con.execute("SELECT DISTINCT ua FROM sessions").fetchall()]
    assert agents == ["Chrome"] or agents == ["Edge"], agents


def test_the_recorders_own_client_id_survives(live_run):
    """DEF-09, pinned. A real UUID has to read as text, not as a UUID column."""
    with warehouse(live_run) as con:
        client_id, native = con.execute(
            "SELECT client_id, has_native_client_id FROM sessions").fetchone()
    assert client_id == CID
    assert native is True
