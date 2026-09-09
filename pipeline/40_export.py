#!/usr/bin/env python3
"""Export curated telemetry in three wire formats. Dry run only.

The point of this file is to show one curated layer serving many consumers with
no second pipeline behind it. PostgreSQL gets relational tables from the same
Parquet. Every format below reads those same files and nothing else.

Formats, in the order a backend usually prefers them:

  cloudevents  CloudEvents 1.0 JSON batch. The open envelope that business
               event ingest endpoints accept, media type
               application/cloudevents-batch+json.
  otlp         OpenTelemetry OTLP/HTTP with JSON encoding. Signals: logs,
               traces, metrics. Default port 4318, paths /v1/logs, /v1/traces
               and /v1/metrics, Content-Type application/json.
  posthog      The original vendor capture shape, kept so the "one layer, many
               consumers" claim has more than one consumer in it.

Both open formats are plain JSON over HTTP, so this file needs no dependency
beyond the duckdb already in requirements.txt. Protobuf and gRPC are the other
two OTLP transports. Neither is built here, because neither earns its
dependency for a demo that makes no network call.

It makes no network calls, ever. There is no token, no endpoint call and no
retry logic, because none of that is what the exercise is about, and a demo
should not depend on somebody else's uptime.

TODO before this could post for real:
  - take the endpoint and the token from the environment, never a file, and
    never a command line argument, because argv lands in shell history
  - POST batches with backoff on 429 and 5xx, honouring Retry-After
  - persist a high water mark on srv so re-runs do not double count
  - round trip test: post a few tuples, read them back, assert they match
  - fix the span id collision this file reports, see docs/hlad.md section 6
  - decide the retention and deletion story before sending anything real
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import sys

import duckdb

ROOT = pathlib.Path(__file__).resolve().parents[1]
CURATED = ROOT / "warehouse" / "curated"

# The service every payload claims to come from. One string, one home.
SERVICE_NAME = "flightdeck"

# OTLP SeverityNumber, from the logs data model. Only the levels this data uses.
SEVERITY = {"INFO": 9, "WARN": 13, "ERROR": 17}


def _hex_id(*parts: object, nbytes: int) -> str:
    """Build a deterministic hex id from a natural key.

    OTLP wants a 16 byte trace id and an 8 byte span id, hex encoded. This data
    carries neither, so the id has to come from the key. A hash keeps the same
    row mapping to the same id on every run, which a random id would not, and a
    re-run that changes every id is a re-run nobody can diff.
    """
    material = "\x1f".join(str(p) for p in parts).encode("utf-8")
    return hashlib.sha256(material).digest()[:nbytes].hex()


def _nanos(value: object) -> str:
    """Convert a timestamp or an epoch millisecond count to OTLP nanoseconds.

    proto3 JSON maps 64 bit integers to strings, so the return type is str and
    not int. A backend that reads this as a number will lose precision.
    """
    if isinstance(value, dt.datetime):
        # Integer arithmetic, not value.timestamp() * 1e9. A float64 cannot hold
        # nanoseconds since 1970 at this magnitude, and rounds the last three
        # digits. This project is about clocks, so a clock it invents is worse
        # than no clock at all.
        delta = value - dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
        return str(delta.days * 86_400_000_000_000
                   + delta.seconds * 1_000_000_000
                   + delta.microseconds * 1_000)
    return str(int(value) * 1_000_000)


def _attrs(pairs: dict) -> list[dict]:
    """Render a plain dict as an OTLP KeyValue list, skipping empty values."""
    out = []
    for key, value in pairs.items():
        if value is None:
            continue
        if isinstance(value, bool):
            typed = {"boolValue": value}
        elif isinstance(value, int):
            typed = {"intValue": str(value)}
        elif isinstance(value, float):
            typed = {"doubleValue": value}
        else:
            typed = {"stringValue": str(value)}
        out.append({"key": key, "value": typed})
    return out


def _resource() -> dict:
    return {"attributes": _attrs({"service.name": SERVICE_NAME})}


def _rows(con: duckdb.DuckDBPyConnection, relation: str) -> list[dict]:
    """Read one published Parquet file as a list of dicts."""
    path = (CURATED / f"{relation}.parquet").as_posix()
    cur = con.execute(f"SELECT * FROM read_parquet('{path}')")
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# OTLP logs. Source: the three relations that record something going wrong.
# ---------------------------------------------------------------------------
def build_otlp_logs(con: duckdb.DuckDBPyConnection) -> dict:
    records = []

    for row in _rows(con, "error_report"):
        records.append({
            "timeUnixNano": _nanos(row["arrived"]),
            "severityNumber": SEVERITY["ERROR"],
            "severityText": "ERROR",
            "body": {"stringValue": row["msg"]},
            "attributes": _attrs({
                "session.id": row["session_id"],
                "page_load.seq": row["page_load_seq"],
                "code.function": row["top_frame"],
                "code.location": row["top_location"],
            }),
        })

    for row in _rows(con, "incident_timeline"):
        records.append({
            "timeUnixNano": _nanos(row["occurred_at"]),
            "severityNumber": SEVERITY["ERROR" if row["event"] == "error" else "WARN"],
            "severityText": "ERROR" if row["event"] == "error" else "WARN",
            "body": {"stringValue": row["detail"]},
            "attributes": _attrs({
                "session.id": row["session_id"],
                "page_load.seq": row["page_load_seq"],
                "incident.kind": row["event"],
                "incident.s_since_previous": row["s_since_previous"],
            }),
        })

    # A quarantined record is a data quality event. It belongs in the log
    # stream, because a backend that never sees it cannot alert on it.
    for row in _rows(con, "quarantine"):
        records.append({
            "timeUnixNano": _nanos(row["srv"]),
            "severityNumber": SEVERITY["WARN"],
            "severityText": "WARN",
            "body": {"stringValue": row["detail"]},
            "attributes": _attrs({
                "session.id": row["session_id"],
                "page_load.seq": row["page_load_seq"],
                "record.kind": row["kind"],
                "quarantine.reason": row["reason"],
                "quarantine.relation": row["relation"],
            }),
        })

    return {"resourceLogs": [{
        "resource": _resource(),
        "scopeLogs": [{"scope": {"name": SERVICE_NAME}, "logRecords": records}],
    }]}


# ---------------------------------------------------------------------------
# OTLP traces. Source: spans, the per frame section timings.
# ---------------------------------------------------------------------------
def build_otlp_traces(con: duckdb.DuckDBPyConnection) -> tuple[dict, int]:
    """Build the trace payload, and count how many span ids collide.

    One trace per trace summary. One child span per frame section inside it.

    The duration is the mean frame time for that section, not the length of one
    real frame, so these spans measure an aggregate rather than an occurrence.
    ms_max and frames ride along as attributes, so the worst case survives.
    """
    grouped: dict[tuple, list[dict]] = {}
    for row in _rows(con, "spans"):
        key = (row["session_id"], row["page_load_seq"], row["srv"], row["origin"])
        grouped.setdefault(key, []).append(row)

    spans_out: list[dict] = []
    seen_ids: set[str] = set()
    collisions = 0

    for (session_id, page_load_seq, srv, origin), sections in grouped.items():
        trace_id = _hex_id(session_id, page_load_seq, srv, origin, nbytes=16)
        root_id = _hex_id(trace_id, "root", nbytes=8)
        start = _nanos(srv)
        total_ms = sum(s["ms"] for s in sections)

        spans_out.append({
            "traceId": trace_id,
            "spanId": root_id,
            "name": f"frame.{origin}",
            "kind": 1,
            "startTimeUnixNano": start,
            "endTimeUnixNano": str(int(start) + int(total_ms * 1_000_000)),
            "attributes": _attrs({
                "session.id": session_id,
                "page_load.seq": page_load_seq,
                "trace.origin": origin,
                "frame.sections": len(sections),
            }),
        })

        for section in sections:
            span_id = _hex_id(trace_id, section["span"], nbytes=8)
            if span_id in seen_ids:
                collisions += 1
            seen_ids.add(span_id)
            spans_out.append({
                "traceId": trace_id,
                "spanId": span_id,
                "parentSpanId": root_id,
                "name": f"frame.{section['span']}",
                "kind": 1,
                "startTimeUnixNano": start,
                "endTimeUnixNano": str(int(start) + int(section["ms"] * 1_000_000)),
                "attributes": _attrs({
                    "frame.section": section["span"],
                    "frame.mean_ms": section["ms"],
                    "frame.max_ms": section["ms_max"],
                    "frame.count": section["frames"],
                }),
            })

    payload = {"resourceSpans": [{
        "resource": _resource(),
        "scopeSpans": [{"scope": {"name": SERVICE_NAME}, "spans": spans_out}],
    }]}
    return payload, collisions


# ---------------------------------------------------------------------------
# OTLP metrics. Source: the four relations that already hold a number.
# ---------------------------------------------------------------------------
def build_otlp_metrics(con: duckdb.DuckDBPyConnection) -> dict:
    now = _nanos(dt.datetime.now(dt.timezone.utc))
    metrics: list[dict] = []

    def gauge(name: str, unit: str, points: list[tuple[float, dict]]) -> None:
        metrics.append({
            "name": name,
            "unit": unit,
            "gauge": {"dataPoints": [
                {"asDouble": float(value), "timeUnixNano": now,
                 "attributes": _attrs(labels)}
                for value, labels in points
            ]},
        })

    loss = _rows(con, "loss_accounting")[0]
    gauge("flightdeck.events.received", "{event}", [(loss["events_received"], {})])
    gauge("flightdeck.events.lost", "{event}", [(loss["events_lost_by_id_gap"], {})])
    gauge("flightdeck.beat.peak_pct_of_cap", "%", [(loss["peak_pct_of_cap"], {})])

    recon = _rows(con, "contract_reconciliation")[0]
    gauge("flightdeck.records.landed", "{record}", [(recon["landed_records"], {})])
    gauge("flightdeck.records.quarantined", "{record}", [(recon["quarantined_records"], {})])

    gauge("flightdeck.alarms", "{alarm}", [
        (row["n"], {"alarm.class": row["class"]}) for row in _rows(con, "alarms_by_class")
    ])

    frames = _rows(con, "frame_time_by_span")
    gauge("flightdeck.frame.p50", "ms",
          [(row["p50_ms"], {"frame.section": row["span"]}) for row in frames])
    gauge("flightdeck.frame.p95", "ms",
          [(row["p95_ms"], {"frame.section": row["span"]}) for row in frames])

    return {"resourceMetrics": [{
        "resource": _resource(),
        "scopeMetrics": [{"scope": {"name": SERVICE_NAME}, "metrics": metrics}],
    }]}


# ---------------------------------------------------------------------------
# CloudEvents 1.0 JSON batch. The business event shape.
# ---------------------------------------------------------------------------
def build_cloudevents(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """Build a CloudEvents batch.

    specversion, type and source are required. id and time are optional in the
    spec, and every ingest endpoint worth posting to wants them anyway.
    """
    source = f"/{SERVICE_NAME}"
    events: list[dict] = []

    def event(kind: str, key: tuple, when: object, data: dict, subject: str | None = None) -> None:
        # An unset optional attribute is omitted, never sent as null. The spec
        # permits both, and ingest endpoints in the wild reject the null.
        events.append({
            "specversion": "1.0",
            "type": f"com.flightdeck.{kind}",
            "source": source,
            "id": _hex_id(kind, *key, nbytes=16),
            **({"time": when} if when else {}),
            "datacontenttype": "application/json",
            **({"subject": subject} if subject else {}),
            "data": data,
        })

    for row in _rows(con, "session_summary"):
        event("session.completed",
              (row["session_id"], row["page_load_seq"]),
              None,
              {k: row[k] for k in (
                  "duration_s", "outcome", "final_state", "kills", "hp_first",
                  "hp_last", "alarms", "errors", "beats", "ua", "states_visited")},
              subject=row["client_id"])

    for row in _rows(con, "error_report"):
        event("client.error",
              (row["session_id"], row["page_load_seq"], row["msg"]),
              row["arrived"].isoformat(),
              {"message": row["msg"], "top_frame": row["top_frame"],
               "location": row["top_location"]},
              subject=f"{row['session_id']}#{row['page_load_seq']}")

    for row in _rows(con, "alarms_by_class"):
        event("alarm.summary", (row["class"],), None,
              {"class": row["class"], "count": row["n"],
               "page_loads": row["page_loads"],
               "states_when_raised": list(row["states_when_raised"] or [])})

    return events


# ---------------------------------------------------------------------------
# The original vendor capture shape, unchanged in meaning.
# ---------------------------------------------------------------------------
def build_posthog(con: duckdb.DuckDBPyConnection) -> list[dict]:
    events: list[dict] = []

    for row in _rows(con, "session_summary"):
        events.append({
            "event": "session_completed",
            "distinct_id": row["client_id"],
            "properties": {
                "duration_s": row["duration_s"], "outcome": row["outcome"],
                "final_state": row["final_state"], "kills": row["kills"],
                "hp_first": row["hp_first"], "hp_last": row["hp_last"],
                "alarm_count": row["alarms"], "error_count": row["errors"],
                "beat_count": row["beats"], "browser": row["ua"],
            },
        })

    for row in _rows(con, "error_report"):
        events.append({
            "event": "client_error",
            "distinct_id": f"{row['session_id']}#{row['page_load_seq']}",
            "timestamp": row["arrived"].isoformat(),
            "properties": {"message": row["msg"], "top_frame": row["top_frame"],
                           "location": row["top_location"]},
        })

    for row in _rows(con, "alarms_by_class"):
        events.append({
            "event": "alarm_summary",
            "distinct_id": "aggregate",
            "properties": {"class": row["class"], "count": row["n"],
                           "page_loads": row["page_loads"]},
        })

    return events


# ---------------------------------------------------------------------------
# Assembly. One dict per payload: the file stem, the HTTP path, the media type.
# ---------------------------------------------------------------------------
def build(con: duckdb.DuckDBPyConnection, fmt: str, signal: str) -> tuple[list[dict], int]:
    """Return the payloads for one format, and the span id collision count."""
    payloads: list[dict] = []
    collisions = 0

    if fmt == "otlp":
        if signal in ("logs", "all"):
            payloads.append({"stem": "otlp-logs", "path": "/v1/logs",
                             "media": "application/json",
                             "body": build_otlp_logs(con)})
        if signal in ("traces", "all"):
            body, collisions = build_otlp_traces(con)
            payloads.append({"stem": "otlp-traces", "path": "/v1/traces",
                             "media": "application/json", "body": body})
        if signal in ("metrics", "all"):
            payloads.append({"stem": "otlp-metrics", "path": "/v1/metrics",
                             "media": "application/json",
                             "body": build_otlp_metrics(con)})
    elif fmt == "cloudevents":
        payloads.append({"stem": "cloudevents", "path": "(ingest endpoint)",
                         "media": "application/cloudevents-batch+json",
                         "body": build_cloudevents(con)})
    else:
        payloads.append({"stem": "posthog", "path": "/batch/",
                         "media": "application/json",
                         "body": build_posthog(con)})

    return payloads, collisions


def _count(body: object) -> int:
    """Count the records a payload carries, whatever its shape."""
    if isinstance(body, list):
        return len(body)
    for outer, inner, leaf in (
        ("resourceLogs", "scopeLogs", "logRecords"),
        ("resourceSpans", "scopeSpans", "spans"),
        ("resourceMetrics", "scopeMetrics", "metrics"),
    ):
        if outer in body:
            return sum(len(s[leaf]) for r in body[outer] for s in r[inner])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("otlp", "cloudevents", "posthog"),
                        default="otlp", help="wire format (default otlp)")
    parser.add_argument("--signal", choices=("logs", "traces", "metrics", "all"),
                        default="all", help="OTLP signal, ignored otherwise")
    parser.add_argument("--out", type=pathlib.Path, default=None,
                        help="write each payload to this directory as JSON")
    parser.add_argument("--limit", type=int, default=2,
                        help="how many records to print per payload (default 2)")
    args = parser.parse_args()

    if not (CURATED / "session_summary.parquet").exists():
        print("FAIL: curated Parquet is missing.", file=sys.stderr)
        print("Hint: run ./demo.sh build first.", file=sys.stderr)
        return 1

    con = duckdb.connect()
    payloads, collisions = build(con, args.format, args.signal)

    print()
    print("  DRY RUN. No network call is made and no token is read.")
    print()

    for payload in payloads:
        body = payload["body"]
        total = _count(body)
        print(f"  {payload['stem']}  {total} records")
        print(f"    POST {payload['path']}")
        print(f"    Content-Type: {payload['media']}")
        print()

        sample = body[:args.limit] if isinstance(body, list) else [body]
        for record in sample:
            text = json.dumps(record, default=str)
            print("    " + (text[:300] + " ..." if len(text) > 300 else text))
        print()

        if args.out:
            args.out.mkdir(parents=True, exist_ok=True)
            target = args.out / f"{payload['stem']}.json"
            target.write_text(json.dumps(body, indent=2, default=str), encoding="utf-8")
            print(f"    wrote {target}")
            print()

    if collisions:
        print(f"  WARNING: {collisions} span ids collide.")
        print("    One beat can drain two trace summaries, and spans carries no")
        print("    column to tell them apart. See docs/hlad.md section 6, item 1.")
        print()

    print("  Same Parquet files PostgreSQL read. One curated layer, three consumers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
