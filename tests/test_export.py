"""The export payloads must satisfy the specs they claim to follow.

pipeline/40_export.py emits three wire formats. Two of them are open specs with
rules a backend enforces on arrival, so the rules belong in a test rather than
in a comment. The third is a vendor shape kept for comparison.

The two rules that caught real defects while writing this file:

  - OTLP timestamps are nanoseconds. Computing them as a float loses the last
    three digits at 2026 magnitudes, so the arithmetic must stay integer.
  - CloudEvents optional attributes are omitted when unset, never sent as null.

These tests read the published Parquet. They skip when it is missing, because
a checkout without a build has nothing to export.
"""
import datetime as dt
import importlib.util
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CURATED = ROOT / "warehouse" / "curated"

pytestmark = pytest.mark.skipif(
    not (CURATED / "session_summary.parquet").exists(),
    reason="curated Parquet is missing, run ./demo.sh build first",
)


def load_module():
    """Import the exporter by path. Its name starts with a digit."""
    path = ROOT / "pipeline" / "40_export.py"
    spec = importlib.util.spec_from_file_location("flightdeck_export", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def export():
    return load_module()


@pytest.fixture(scope="module")
def con(export):
    import duckdb
    return duckdb.connect()


# --------------------------------------------------------------------------
# Timestamps
# --------------------------------------------------------------------------
def test_epoch_millis_convert_to_exact_nanoseconds(export):
    """An epoch millisecond count scales by exactly one million."""
    assert export._nanos(1788101938203) == "1788101938203000000"


def test_datetime_nanoseconds_keep_every_digit(export):
    """A float64 cannot hold nanoseconds at this magnitude. Integers can.

    This is the regression: value.timestamp() * 1e9 returned
    1788101938203000064, inventing 64 nanoseconds that no clock measured.
    """
    when = dt.datetime.fromtimestamp(1788101938.203, tz=dt.timezone.utc)
    assert export._nanos(when) == "1788101938203000000"


def test_otlp_log_timestamps_are_digit_strings(export, con):
    """proto3 JSON maps 64 bit integers to strings, not numbers."""
    records = export.build_otlp_logs(con)["resourceLogs"][0]["scopeLogs"][0]["logRecords"]
    assert records, "no log records built"
    for record in records:
        value = record["timeUnixNano"]
        assert isinstance(value, str)
        assert value.isdigit()


# --------------------------------------------------------------------------
# OTLP identifiers
# --------------------------------------------------------------------------
def test_trace_and_span_ids_are_hex_of_the_required_length(export, con):
    """OTLP/JSON wants a 32 character trace id and a 16 character span id."""
    payload, _ = export.build_otlp_traces(con)
    spans = payload["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert spans, "no spans built"
    for span in spans:
        assert re.fullmatch(r"[0-9a-f]{32}", span["traceId"])
        assert re.fullmatch(r"[0-9a-f]{16}", span["spanId"])


def test_ids_are_deterministic_across_runs(export, con):
    """The same row must map to the same id, so two exports can be diffed."""
    first, _ = export.build_otlp_traces(con)
    second, _ = export.build_otlp_traces(con)
    ids = [s["spanId"] for s in first["resourceSpans"][0]["scopeSpans"][0]["spans"]]
    again = [s["spanId"] for s in second["resourceSpans"][0]["scopeSpans"][0]["spans"]]
    assert ids == again


def test_span_id_collisions_are_reported_not_hidden(export, con):
    """spans has no primary key, so some ids collide. Silence would be worse.

    docs/hlad.md section 6 item 1 tracks the fix. Until it lands, the exporter
    must keep saying how many rows are affected.
    """
    payload, collisions = export.build_otlp_traces(con)
    spans = payload["resourceSpans"][0]["scopeSpans"][0]["spans"]
    children = [s for s in spans if "parentSpanId" in s]
    distinct = len({s["spanId"] for s in children})
    assert collisions == len(children) - distinct


def test_every_child_span_points_at_a_root_in_the_same_trace(export, con):
    payload, _ = export.build_otlp_traces(con)
    spans = payload["resourceSpans"][0]["scopeSpans"][0]["spans"]
    roots = {(s["traceId"], s["spanId"]) for s in spans if "parentSpanId" not in s}
    for span in spans:
        if "parentSpanId" in span:
            assert (span["traceId"], span["parentSpanId"]) in roots


# --------------------------------------------------------------------------
# CloudEvents
# --------------------------------------------------------------------------
def test_cloudevents_carry_every_required_attribute(export, con):
    """specversion, type and source are required by the 1.0 JSON format."""
    events = export.build_cloudevents(con)
    assert events, "no events built"
    for event in events:
        assert event["specversion"] == "1.0"
        assert event["type"]
        assert event["source"]


def test_cloudevents_omit_unset_attributes_rather_than_sending_null(export, con):
    """The regression: session_summary has no timestamp, so time was null."""
    for event in export.build_cloudevents(con):
        for key, value in event.items():
            assert value is not None, f"{event['type']} sent {key} as null"


def test_cloudevent_ids_are_unique(export, con):
    events = export.build_cloudevents(con)
    ids = [e["id"] for e in events]
    assert len(ids) == len(set(ids))


# --------------------------------------------------------------------------
# The payload set
# --------------------------------------------------------------------------
@pytest.mark.parametrize("fmt, signal, stems", [
    ("otlp", "all", ["otlp-logs", "otlp-traces", "otlp-metrics"]),
    ("otlp", "logs", ["otlp-logs"]),
    ("cloudevents", "all", ["cloudevents"]),
    ("posthog", "all", ["posthog"]),
])
def test_each_format_builds_the_payloads_it_promises(export, con, fmt, signal, stems):
    payloads, _ = export.build(con, fmt, signal)
    assert [p["stem"] for p in payloads] == stems
    for payload in payloads:
        assert export._count(payload["body"]) > 0
        assert payload["media"]
        assert payload["path"]


def test_the_exporter_opens_no_socket():
    """The file promises no network call. Prove it imports nothing that could."""
    source = (ROOT / "pipeline" / "40_export.py").read_text(encoding="utf-8")
    for banned in ("import requests", "import socket", "import urllib",
                   "from urllib", "http.client"):
        assert banned not in source, f"{banned} would break the no-network promise"
