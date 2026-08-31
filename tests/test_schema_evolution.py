"""The pipeline must read both generations of the wire format.

The committed fixtures were recorded before the recorder minted a per page
client id. Newer logs carry `cid`. Both have to work, and the difference has to
be visible rather than silently papered over, which is what
`has_native_client_id` is for.

These tests run the real pipeline SQL against small purpose-built logs.
"""
import json
import pathlib
import shutil

import duckdb
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW_SQL = (ROOT / "pipeline" / "00_raw.sql").read_text(encoding="utf-8")
TYPED_SQL = (ROOT / "pipeline" / "10_typed.sql").read_text(encoding="utf-8")


def write_log(path: pathlib.Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")


def session(with_cid: str | None) -> list[dict]:
    """One page load: hello, a beat, a goodbye."""
    extra = {"cid": with_cid} if with_cid else {}
    return [
        {"kind": "hello", "wall": 1_788_000_000_000, "href": "http://localhost/",
         "ua": "Chrome", "dpr": 1, "srv": 1_788_000_000_001, **extra},
        {"kind": "beat", "wall": 1_788_000_001_000, "perf": 1000, "raf": 60,
         "vis": "visible",
         "pulse": {"state": "playing", "mode": "brawl", "map": "forest",
                   "char": "archer", "t": 1.0, "lastTs": 1000, "live": True,
                   "held": 0, "hp": 9, "kills": 0, "crows": 3, "skels": 0,
                   "soldiers": 0, "arrows": 0, "boss": None},
         "events": [], "srv": 1_788_000_001_001, **extra},
        {"kind": "bye", "wall": 1_788_000_002_000, "events": [],
         "srv": 1_788_000_002_001, **extra},
    ]


@pytest.fixture
def run_pipeline(tmp_path, monkeypatch):
    """Run the real raw and typed SQL in an isolated working directory."""
    def _run(records: list[dict]):
        shutil.copytree(ROOT / "fixtures" / "reference", tmp_path / "fixtures" / "reference")
        shutil.copytree(ROOT / "contracts", tmp_path / "contracts")
        write_log(tmp_path / "source" / "session-2026-09-01T00-00-00-000Z.jsonl", records)
        (tmp_path / "warehouse").mkdir(exist_ok=True)
        monkeypatch.chdir(tmp_path)
        con = duckdb.connect()
        con.execute("SET variable raw_glob = 'source/*.jsonl'")
        con.execute(RAW_SQL)
        con.execute(TYPED_SQL)
        return con
    return _run


def test_new_format_uses_the_recorders_own_client_id(run_pipeline):
    con = run_pipeline(session(with_cid="abc-123"))
    rows = con.execute(
        "SELECT client_id, has_native_client_id FROM sessions"
    ).fetchall()
    assert rows == [("abc-123", True)]


def test_old_format_derives_a_client_id_and_says_so(run_pipeline):
    con = run_pipeline(session(with_cid=None))
    client_id, native = con.execute(
        "SELECT client_id, has_native_client_id FROM sessions"
    ).fetchone()
    assert native is False
    assert client_id.endswith("#1"), "derived ids are keyed on the hello count"


def test_both_generations_in_one_run(run_pipeline):
    """A log written across a recorder upgrade must not break the load."""
    records = session(with_cid=None)
    second = session(with_cid="new-gen")
    for rec in second:                      # keep srv strictly increasing
        rec["srv"] += 10_000
        rec["wall"] += 10_000
    con = run_pipeline(records + second)

    rows = con.execute(
        "SELECT client_id, has_native_client_id FROM sessions ORDER BY page_load_seq"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0][1] is False and rows[0][0].endswith("#1")
    assert rows[1] == ("new-gen", True)


def test_the_contract_still_reconciles_on_a_new_format_log(run_pipeline):
    con = run_pipeline(session(with_cid="abc-123"))
    assert con.execute("SELECT reconciles FROM contract_reconciliation").fetchone()[0] is True


def test_an_orphan_goodbye_is_quarantined_not_dropped(run_pipeline):
    """A page that outlived its dev server sends bye into a file with no hello."""
    orphan = [{"kind": "bye", "wall": 1_787_999_999_000, "events": [],
               "srv": 1_787_999_999_001}]
    con = run_pipeline(orphan + session(with_cid="abc-123"))

    reason, = con.execute("SELECT reason FROM quarantine").fetchone()
    assert reason == "orphan_record_no_hello"
    assert con.execute("SELECT reconciles FROM contract_reconciliation").fetchone()[0] is True


def test_a_state_outside_the_contract_is_quarantined(run_pipeline):
    records = session(with_cid="abc-123")
    records[1]["pulse"]["state"] = "not_a_real_state"
    con = run_pipeline(records)

    rows = con.execute(
        "SELECT relation, reason, detail FROM quarantine WHERE reason LIKE 'state%'"
    ).fetchall()
    assert rows == [("pulses", "state_not_in_contract", "state=not_a_real_state")]


def test_a_beat_over_the_event_cap_is_quarantined(run_pipeline):
    records = session(with_cid="abc-123")
    records[1]["events"] = [
        {"id": i, "level": "debug", "timestamp": 1, "source": "EventBus",
         "message": "x", "data": {}, "code": None}
        for i in range(1, 402)                      # cap is 400
    ]
    con = run_pipeline(records)

    reasons = [r[0] for r in con.execute("SELECT reason FROM quarantine").fetchall()]
    assert "events_per_beat_over_cap" in reasons
