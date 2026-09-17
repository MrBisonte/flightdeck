"""Tests for the pure logic in the flight log sanitizer."""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from sanitize_flightlog import (browser_family, check_clean, listed_origins, mask_origins,
                                MASK, publishable_origins, sanitize_record, scrub_origins)


@pytest.mark.parametrize(
    "ua, expected",
    [
        # Edge advertises Chrome and Safari too. Most specific token wins.
        ("Mozilla/5.0 (Windows NT 10.0) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0", "Edge"),
        # An embedded browser build token must not survive.
        ("Mozilla/5.0 (Windows NT 10.0) SomeApp/1.4 Chrome/148.0.7778.280 Safari/537.36", "Chrome"),
        ("Mozilla/5.0 (X11; Linux x86_64) Firefox/130.0", "Firefox"),
        ("Mozilla/5.0 (Macintosh) Version/17.0 Safari/605.1.15", "Safari"),
        ("Mozilla/5.0 Chrome/120 Safari/537.36 OPR/106.0", "Opera"),
        ("something entirely unknown", "Other"),
    ],
)
def test_browser_family_keeps_only_the_family(ua, expected):
    assert browser_family(ua) == expected


def test_browser_family_output_carries_no_version():
    trimmed = browser_family("Mozilla/5.0 App/9.9.9 Chrome/148.0.7778.280 Safari/537.36")
    assert not any(ch.isdigit() for ch in trimmed)


def test_scrub_origins_preserves_file_line_and_column():
    stack = (
        "TypeError: Cannot read properties of undefined (reading 'length')\n"
        "    at PathScheduler.invalidateThrough (http://localhost:8090/src/sim/pathfinding.ts:67:30)"
    )
    out = scrub_origins(stack)
    # The evidence must survive intact.
    assert "pathfinding.ts:67:30" in out
    assert "PathScheduler.invalidateThrough" in out
    assert ":8090" not in out
    assert "http://localhost/src/sim/pathfinding.ts:67:30" in out


def test_scrub_origins_rewrites_a_remote_host():
    assert scrub_origins("https://example.internal:443/a/b.js:1:2") == "http://localhost/a/b.js:1:2"


def test_sanitize_record_leaves_telemetry_untouched():
    rec = {
        "kind": "beat", "wall": 1788102296269, "perf": 1922, "raf": 7,
        "vis": "visible", "pulse": {"state": "playing", "hp": 9, "kills": 3},
        "srv": 1788102296270,
    }
    before = json.dumps(rec, sort_keys=True)
    assert json.dumps(sanitize_record(dict(rec)), sort_keys=True) == before


def test_sanitize_record_is_idempotent():
    rec = {"kind": "hello", "ua": "Mozilla/5.0 Chrome/148 Safari/537.36",
           "href": "http://localhost:8090/"}
    once = sanitize_record(dict(rec))
    twice = sanitize_record(dict(once))
    assert once == twice == {"kind": "hello", "ua": "Chrome", "href": "http://localhost/"}


def test_check_clean_flags_a_drive_path(tmp_path):
    bad = tmp_path / "bad.jsonl"
    sep = chr(92)  # avoid literal escapes in the test source
    stack = f"at C:{sep}Users{sep}someone{sep}game.js"
    bad.write_text(json.dumps({"kind": "err", "stack": stack}) + chr(10),
                   encoding="utf-8")
    problems = check_clean(bad)
    assert any("Windows drive path" in p for p in problems)


def test_check_clean_flags_an_untrimmed_user_agent(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({"kind": "hello", "ua": "Mozilla/5.0 Chrome/148"}) + "\n",
                   encoding="utf-8")
    assert any("un-trimmed ua" in p for p in check_clean(bad))


def test_committed_fixtures_are_clean():
    """The published fixtures must pass their own gate."""
    raw = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "raw"
    files = sorted(raw.glob("*.jsonl"))
    assert len(files) == 4, "expected four fixture sessions"
    for path in files:
        assert check_clean(path) == []


# The scrub used to name three fields, ua, href and stack. Everything below is
# a field it did not name. An origin in msg reached error_report,
# incident_timeline and session_context, all of them published.
def test_scrub_reaches_an_error_message():
    rec = sanitize_record({
        "kind": "err",
        "msg": "Uncaught TypeError: failed to load http://192.168.1.50:5173/src/game.ts",
    })
    assert "192.168.1.50" not in rec["msg"]
    assert rec["msg"].endswith("http://localhost/src/game.ts")


def test_scrub_reaches_a_nested_event_body():
    rec = sanitize_record({
        "kind": "beat",
        "events": [{
            "id": 1, "level": "warn",
            "message": "asset fetch failed from http://192.168.1.50:5173/assets/crow.png",
            "data": {"url": "http://192.168.1.50:5173/assets/crow.png"},
        }],
    })
    event = rec["events"][0]
    assert "192.168.1.50" not in json.dumps(rec)
    assert event["message"].endswith("http://localhost/assets/crow.png")
    assert event["data"]["url"] == "http://localhost/assets/crow.png"


def test_check_clean_flags_a_remote_origin(tmp_path):
    """The gate reported clean while a private address sat in the output.

    The rule behind this test moved. It used to read "the host is not
    localhost", which refused a capture from the published build. It now reads
    "no reference row names this origin", which refuses the same address for a
    better reason and keeps the DEF-13 outcome.
    """
    bad = tmp_path / "bad.jsonl"
    bad.write_text(
        json.dumps({"kind": "err", "msg": "boom at http://192.168.1.50:5173/x.js"}) + "\n",
        encoding="utf-8")
    assert any("unlisted origin" in p for p in check_clean(bad))


@pytest.mark.parametrize("href", ["http://localhost/", "http://localhost"])
def test_check_clean_allows_the_scrubbed_fixture_origin(tmp_path, href):
    ok = tmp_path / "ok.jsonl"
    ok.write_text(json.dumps({"kind": "hello", "ua": "Chrome", "href": href}) + "\n",
                  encoding="utf-8")
    assert check_clean(ok) == []


@pytest.mark.parametrize("href", ["http://localhost:5173/game", "https://localhost/game"])
def test_check_clean_flags_an_unlisted_localhost(tmp_path, href):
    """Default-deny reaches localhost too.

    A fixture may carry only what the hard scrub produces. A port or a scheme
    the scrub never writes means the file did not come from the scrub, which is
    exactly how a stale fixture kept a dev server port. See DEF-15.
    """
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({"kind": "hello", "ua": "Chrome", "href": href}) + "\n",
                   encoding="utf-8")
    assert any("unlisted origin" in p for p in check_clean(bad))


# ---------------------------------------------------------------------------
# The live route. A listed origin is data; everything else is masked.
# ---------------------------------------------------------------------------
def test_mask_keeps_a_listed_origin_verbatim():
    stack = "at update (https://mrbisonte.github.io/crow-archer/game.ts:67:30)"
    assert mask_origins(stack) == stack


def test_mask_replaces_an_unlisted_origin():
    out = mask_origins("boom at http://192.168.1.50:5173/src/game.ts:1:2")
    assert "192.168.1.50" not in out
    assert out.endswith(f"{MASK}/src/game.ts:1:2")


def test_mask_reaches_a_nested_event_body():
    """The live route walks the record, exactly as the scrub does."""
    rec = sanitize_record({
        "kind": "beat",
        "events": [{"id": 1, "message": "fetch failed from http://192.168.1.50:5173/a.png",
                    "data": {"url": "http://192.168.1.50:5173/a.png"}}],
    }, mask_origins)
    assert "192.168.1.50" not in json.dumps(rec)
    assert rec["events"][0]["data"]["url"] == f"{MASK}/a.png"


def test_masking_is_idempotent():
    """A mask is itself a listed origin, so a second pass changes nothing."""
    once = mask_origins("boom at http://192.168.1.50:5173/a.js")
    assert mask_origins(once) == once


def test_the_mask_is_a_listed_origin():
    """Otherwise the gate would refuse the sanitizer's own output."""
    assert MASK in listed_origins()


def test_the_live_gate_accepts_a_listed_public_origin(tmp_path):
    """The point of the change. A capture from the published build passes."""
    ok = tmp_path / "ok.jsonl"
    ok.write_text(json.dumps({"kind": "hello", "ua": "Chrome",
                              "href": "https://mrbisonte.github.io/crow-archer/"}) + "\n",
                  encoding="utf-8")
    assert check_clean(ok, listed_origins()) == []
    # And so does the committing gate, because the reference says it may publish.
    assert check_clean(ok) == []


# ---------------------------------------------------------------------------
# may_publish, the one column that decides what a public repository may hold.
# ---------------------------------------------------------------------------
def test_the_committing_gate_refuses_a_withheld_origin(tmp_path):
    """DEF-15, restated. The dev server port is listed, and still refused.

    The rule used to read "localhost only", which kept a stale capture out by
    keeping everything out. It now reads "the reference says this may publish",
    which keeps the same capture out for the reason that was always meant.
    """
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({"kind": "hello", "ua": "Chrome",
                               "href": "http://localhost:8090/"}) + "\n",
                   encoding="utf-8")
    assert "http://localhost:8090" in listed_origins()
    assert any("unlisted origin" in p for p in check_clean(bad))
    # The same file is legitimate data for a capture nobody is committing.
    assert check_clean(bad, listed_origins()) == []


def test_publishable_origins_is_a_strict_subset():
    assert publishable_origins() < listed_origins()
    assert MASK in publishable_origins()


def test_the_live_gate_still_refuses_an_unlisted_origin(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({"kind": "hello", "ua": "Chrome",
                               "href": "https://someone-elses.example/game"}) + "\n",
                   encoding="utf-8")
    assert any("unlisted origin" in p for p in check_clean(bad, listed_origins()))
