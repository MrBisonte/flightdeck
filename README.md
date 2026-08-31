# flightdeck

A medallion pipeline over real browser game telemetry.

```
   JSONL  -->  Parquet  -->  typed model  -->  curated views  -->  PostgreSQL
   raw log     partitioned   under a         analytics           and PostHog
                             contract
```

The telemetry comes from the flight recorder in
[crow-archer](https://github.com/MrBisonte/crow-archer). The three sessions in
`fixtures/raw/` hold 1260 records of real play. Two sessions contain alarms and
an uncaught error. One session is clean.

Read [docs/architecture.md](docs/architecture.md) for the full picture.

## Quickstart

You need three things:

| Tool | Version |
|---|---|
| `duckdb` on PATH | 1.0 or newer |
| Python | 3.9 or newer |
| A bash shell | any |

Docker is optional. The load step works without it.

```bash
git clone https://github.com/MrBisonte/flightdeck && cd flightdeck
```

```bash
pip install -r requirements.txt && ./demo.sh
```

That command runs every step and prints the answers. It takes 3 to 5 seconds
from cold.

Run one step at a time with a step name:

```bash
./demo.sh curated
```

Steps: `check`, `raw`, `typed`, `curated`, `publish`, `load`, `posthog`.

## The idea

A page can report the wrong time. A page cannot change when its data arrived.

```
   wall, perf, timestamp  -->  written by the page   -->  claims
   srv                    -->  written by the server -->  fact
```

The pipeline partitions and orders on `srv`. It treats the other three clocks as
claims to check.

That one decision separates a page that went quiet from a page that was wrong.
It is how the pipeline sorts 20 background-tab stalls from the 1 stall that
throttling does not explain.

## What it answers

| View | Question |
|---|---|
| `session_summary` | What happened in each page load? How did it end? |
| `clock_skew` | Does the page clock agree with the server clock? |
| `gap_explained` | When did the page stop? Why? |
| `incident_timeline` | How long after a crash did the watchdog notice? |
| `frame_time_by_span` | What is p50 and p95 per frame section? |
| `loss_accounting` | How much telemetry did the system lose? |
| `dimension_coverage` | Which documented values did nobody play? |
| `quarantine` | Which records failed the contract, and why? |

## Layout

| Path | Content |
|---|---|
| `contracts/flight_log.yml` | The data contract: enums, caps, required fields |
| `contracts/wire_schema.jsonl` | One record of each kind. Fixes the column set |
| `fixtures/raw/` | Three real sessions, sanitized |
| `fixtures/reference/` | The documented domain, as CSV. The second source |
| `pipeline/` | The six pipeline steps, in order |
| `scripts/` | The sanitizer, a credential scan, an STE doc check |
| `docs/architecture.md` | End to end, data flows, topology |
| `demo.sh` | Every step, one command |

## Three rules this repository follows

| Rule | Result |
|---|---|
| **Drop nothing** | A bad record moves to `quarantine` with a reason. The counts reconcile |
| **Make no network calls** | The PostHog exporter prints its batch and exits. It reads no key |
| **Claim only what runs** | Snowflake stays a documented path. The demo needs no external service |

## License

MIT. See [LICENSE](LICENSE).
