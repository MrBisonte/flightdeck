# flightdeck

A medallion pipeline over telemetry from a real browser game.

```
   JSONL  -->  Parquet  -->  typed model  -->  curated views  -->  PostgreSQL
   raw log     partitioned   under a         analytics           and exporters
                             contract
```

The telemetry comes from the flight recorder in
[crow-archer](https://github.com/MrBisonte/crow-archer). The three sessions in
`fixtures/raw/` hold 1260 records of real play. Two sessions contain alarms and
an uncaught error. One session is clean.

Read [docs/architecture.md](docs/architecture.md) for the full picture. Read
[docs/defect-log.md](docs/defect-log.md) for what broke on the way there.

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

Steps: `check`, `raw`, `typed`, `curated`, `gold`, `publish`, `load`,
`export`. `build` runs the five steps that write the warehouse.

## The idea

A page can report the wrong time. A page cannot change when its data arrived.

```
   wall, perf, timestamp  -->  written by the page   -->  claims
   srv                    -->  written by the server -->  fact
```

The pipeline partitions and orders on `srv`. It treats the other three clocks as
claims to check.

That one decision separates a page that went quiet from a page that was wrong.
It is how the pipeline sorts 20 stalls in a background tab from the 1 stall
that throttling does not explain.

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
| `fact_run` | What happened in one run, at the run grain rather than the page load? |
| `character_usage` | Which characters do players pick, and how many kills do they get? |
| `reference_history` | What did the playbook say about this character before, and when did it change? |

## Layout

| Path | Content |
|---|---|
| `contracts/flight_log.yml` | The data contract: enums, caps, required fields |
| `contracts/wire_schema.jsonl` | One record of each kind. Fixes the column set |
| `fixtures/raw/` | Three real sessions, sanitized |
| `fixtures/reference/` | The documented domain, as CSV. The second source |
| `pipeline/` | The seven pipeline steps, in order |
| `scripts/` | The sanitizer, a credential scan, an STE doc check |
| `site/` | The analytics site over the curated Parquet |
| `docs/architecture.md` | End to end, data flows, ownership |
| `docs/hlad.md` | The relational model: objects, units, keys, runtime topology, worked records |
| `docs/adr/` | One file per decision that would otherwise need re-arguing |
| `docs/runbook-export.md` | Human setup for sending telemetry to a backend |
| `docs/defect-log.md` | Every defect found while building this, and its fix |
| `demo.sh` | Every step, one command |

## The site

The curated Parquet also feeds a static site, built with Observable Framework.
Every number on a page is the result of a query, and the engineering view
prints that query above its result. The site holds no query that the pipeline
holds. It reads what `./demo.sh build`
published, and nothing else.

Run it locally:

```bash
npm install --prefix site && npm run dev --prefix site
```

Pages today: Start here, Overview, Four clocks, The game, and Explore. Start
here is the introduction. Overview is the dashboard. The game reads the gold
layer. Explore runs the reader's own SQL.

DuckDB compiles to WebAssembly and runs inside the reader's tab, so Explore
needs no server to answer a query. It declares every published table, lists
their columns from `duckdb_columns()`, and runs whatever the reader types.
[docs/adr/0001-query-the-warehouse-in-the-browser.md](docs/adr/0001-query-the-warehouse-in-the-browser.md)
records the sizing that makes this work.

[docs/adr/0002-version-the-reference-dimensions.md](docs/adr/0002-version-the-reference-dimensions.md)
records why two dimensions keep their history and the other two do not.

Every page has two views, switched from the control in the top right.
Engineering prints each query above its result. Dashboard hides the SQL and
restyles the page for a reader who wants the answer. Neither view recomputes
anything, so the two cannot disagree.

The site is live at https://mrbisonte.github.io/flightdeck/. A push to `main`
rebuilds it, and a weekly cron rebuilds it on Mondays.

## Three rules this repository follows

| Rule | Result |
|---|---|
| **Drop nothing** | A bad record moves to `quarantine` with a reason. The counts reconcile |
| **Make no network calls** | The exporter prints its payloads and exits. It reads no token |
| **Claim only what runs** | Snowflake stays a documented path. The demo needs no external service |

## License

MIT. See [LICENSE](LICENSE).
