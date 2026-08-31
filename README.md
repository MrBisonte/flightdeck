# flightdeck

A medallion pipeline over real browser game telemetry. JSONL flight logs to Hive
partitioned Parquet, to a typed relational model enforced by a data contract, to
curated analytics, to PostgreSQL and a PostHog event stream.

The telemetry comes from the flight recorder in
[crow-archer](https://github.com/MrBisonte/crow-archer). The three sessions in
`fixtures/raw/` are real recorded play, 1260 records, not generated. Two of them
carry alarms and an uncaught error, one is clean.

Read [docs/architecture.md](docs/architecture.md) for how the whole thing fits
together, including the diagrams.

## Quickstart

You need `duckdb` on PATH, Python 3.9 or newer, and a bash shell. Docker is
optional, the load step degrades without it and says so.

```bash
git clone https://github.com/MrBisonte/flightdeck && cd flightdeck
```

```bash
pip install -r requirements.txt && ./demo.sh
```

That runs every step on the committed fixtures and prints the answers. It takes
about 3 seconds from cold.

To run one step at a time:

```bash
./demo.sh build
```

Steps are `check`, `raw`, `typed`, `curated`, `publish`, `load`, `posthog`.

## What it answers

| View | Question |
|---|---|
| `session_summary` | What happened in each page load, and how did it end |
| `clock_skew` | Does the clock the page reports agree with the one the server stamped |
| `gap_explained` | When did the page go quiet, and was throttling the reason |
| `frame_time_by_span` | p50 and p95 per frame section, over 3978 measurements |
| `loss_accounting` | How much telemetry was lost, proven rather than assumed |
| `dimension_coverage` | Which documented states, modes and characters were never played |
| `quarantine` | Every row that failed the contract, with the reason |

## The idea in one paragraph

A page can lie about the time. It cannot lie about when its data arrived. Every
record carries a server stamped `srv` alongside the three clocks the page writes
itself, so the pipeline partitions and orders on `srv` and treats the rest as
claims to check. That single decision is what lets it tell a page that went quiet
from a page that was merely wrong, and it is how the 20 background tab stalls in
this data get separated from the one stall that throttling does not explain.

## Layout

| Path | What |
|---|---|
| `contracts/flight_log.yml` | The data contract: enums, caps, required fields |
| `fixtures/raw/` | Three real sessions, sanitized. See `fixtures/SANITIZATION.md` |
| `fixtures/reference/` | The documented domain, as CSV. The second source |
| `pipeline/` | `00_raw` `10_typed` `20_curated` `25_publish` `30_load_postgres` `40_posthog_export` |
| `scripts/` | The sanitizer and a generic credential scan |
| `docs/architecture.md` | End to end, data flows, topology |
| `demo.sh` | All of it, one command |

## Notes

- **Nothing is dropped.** Rows that fail the contract go to `quarantine` with a
  reason, and `contract_reconciliation` proves clean plus quarantined equals
  landed.
- **The PostHog exporter makes no network calls.** It prints the batch it would
  send and exits. It reads no API key.
- **Snowflake is a documented path, not a live step.** The curated Parquet is
  what a `COPY INTO` would read, and the demo has no external dependencies.

## License

MIT, see [LICENSE](LICENSE).
