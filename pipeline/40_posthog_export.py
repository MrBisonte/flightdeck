#!/usr/bin/env python3
"""Export curated telemetry to the PostHog capture shape. Dry run only.

The point of this file is to show one curated layer serving a second consumer
with no second pipeline behind it. PostgreSQL gets relational tables from the
same Parquet; PostHog gets an event stream from the same Parquet.

It makes no network calls, ever. There is no API key, no endpoint call and no
retry logic, because none of that is what the exercise is about, and a demo
should not depend on somebody else's uptime.

TODO before this could ship for real:
  - accept a project API key from the environment, never a file
  - POST batches of at most 500 to /batch/ with backoff on 429 and 5xx
  - persist a high water mark on srv so re-runs do not double count
  - decide the retention and deletion story before sending anything real
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import duckdb

ROOT = pathlib.Path(__file__).resolve().parents[1]
CURATED = ROOT / "warehouse" / "curated"


def build_events(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """Build the event stream from the curated relations."""
    curated = CURATED.as_posix()
    events: list[dict] = []

    sessions = con.execute(f"""
        SELECT client_id, duration_s, outcome, final_state, kills,
               hp_first, hp_last, alarms, errors, ua, beats
        FROM read_parquet('{curated}/session_summary.parquet')
    """).fetchall()
    for (client_id, duration_s, outcome, final_state, kills,
         hp_first, hp_last, alarms, errors, ua, beats) in sessions:
        events.append({
            "event": "session_completed",
            "distinct_id": client_id,
            "properties": {
                "duration_s": duration_s, "outcome": outcome,
                "final_state": final_state, "kills": kills,
                "hp_first": hp_first, "hp_last": hp_last,
                "alarm_count": alarms, "error_count": errors,
                "beat_count": beats, "browser": ua,
            },
        })

    errors_rows = con.execute(f"""
        SELECT session_id, page_load_seq, arrived, msg, top_frame, top_location
        FROM read_parquet('{curated}/error_report.parquet')
    """).fetchall()
    for session_id, page_load_seq, arrived, msg, top_frame, top_location in errors_rows:
        events.append({
            "event": "client_error",
            "distinct_id": f"{session_id}#{page_load_seq}",
            "timestamp": arrived.isoformat() if hasattr(arrived, "isoformat") else str(arrived),
            "properties": {
                "message": msg, "top_frame": top_frame, "location": top_location,
            },
        })

    alarms_rows = con.execute(f"""
        SELECT class, n, page_loads FROM read_parquet('{curated}/alarms_by_class.parquet')
    """).fetchall()
    for klass, n, page_loads in alarms_rows:
        events.append({
            "event": "alarm_summary",
            "distinct_id": "aggregate",
            "properties": {"class": klass, "count": n, "page_loads": page_loads},
        })

    return events


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=3,
                        help="how many payloads to print (default 3)")
    args = parser.parse_args()

    if not (CURATED / "session_summary.parquet").exists():
        print("FAIL: curated Parquet is missing.", file=sys.stderr)
        print("Hint: run ./demo.sh build first.", file=sys.stderr)
        return 1

    con = duckdb.connect()
    events = build_events(con)

    by_type: dict[str, int] = {}
    for e in events:
        by_type[e["event"]] = by_type.get(e["event"], 0) + 1

    print()
    print("  DRY RUN. No network call is made and no API key is read.")
    print()
    print(f"  {len(events)} events would be sent, in {len(events) // 500 + 1} batch(es) of <=500:")
    for name, count in sorted(by_type.items()):
        print(f"    {name:<20} {count:>4}")
    print()
    print(f"  First {args.limit}, as they would appear in the batch body:")
    print()
    for e in events[:args.limit]:
        print("    " + json.dumps(e, default=str))
    print()
    print("  Same Parquet files PostgreSQL read. One curated layer, two consumers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
