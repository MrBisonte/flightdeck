# QA evidence

Two artifacts, both regenerated rather than written by hand.

| Artifact | What it holds | How to rebuild |
|---|---|---|
| `e2e-evidence.csv` | One row per relation, from the committed fixtures | `./demo.sh all` then `python scripts/qa_evidence.py` |
| `e2e-evidence-live.csv` | The same rows, from one capture through `--live` | See "Both inputs" below |
| `screenshots/` | Every page of the built site, full height, in both views | See "Rebuilding the screenshots" |

Each row carries the layer, the kind, the row count and the column list with
types. It also carries a real sample row, plus the counts the Parquet and
PostgreSQL copies report.

## What the CSV proves

Three sinks answer for each relation, and the CSV keeps the three counts side by
side. The warehouse builds every layer. `warehouse/curated/*.parquet` is what the
site reads. The `curated` schema in PostgreSQL is what the load step writes.

Publishing reads the database and PostgreSQL reads the Parquet, so a silent loss
at either hop reads as a mismatch in the `verdict` column. A plausible smaller
number never passes.

`postgres_rows` is empty for a relation the load step does not carry. It loads
the twelve curated relations and no gold relation, which the column shows
without needing a note.

`empty` is a separate column from `verdict`, on purpose. A count that disagrees
is always a defect. A relation with no rows is a property of the input. One
capture holds no alarm and no error, so six relations land empty while every
count still agrees.

## Both inputs

`./demo.sh build` reads the three committed captures. `./demo.sh --live DIR`
reads the newest capture in `DIR`, through the sanitizer. The second path has
its own defects in the log, so it earns its own evidence.

Run it from a copy of the tree, not from the repository, because `--live`
replaces the warehouse the site reads:

```
mkdir -p /tmp/livecheck && cd /tmp/livecheck
cp -r <repo>/{pipeline,contracts,scripts,fixtures,tests,docs} . && cp <repo>/{demo.sh,README.md,docker-compose.yml} .
mkdir -p warehouse captures && cp <repo>/fixtures/raw/*.jsonl captures/
bash ./demo.sh --live captures all
python scripts/qa_evidence.py --out docs/qa/e2e-evidence-live.csv --raw-glob warehouse/live/<the capture demo.sh picked>
```

`--raw-glob` matters. `raw_landed` wraps a DuckDB variable that `demo.sh` sets,
so without the flag that one relation reports the fixtures while every other
relation reports the capture.

The two runs agree where they should and differ where the input differs:

| Relation | Fixtures, 3 captures | Live, newest capture |
|---|---|---|
| `landed` | 1260 | 338 |
| `clean` | 1259 | 337 |
| `quarantine` | 1 | 1 |
| `sessions` | 16 | 4 |
| `spans` | 4002 | 1068 |
| `fact_run` | 6 | 2 |
| `dim_member` | 9 | 9 |
| `alarms`, `errors` | 4, 2 | 0, 0 |

`clean` plus `quarantine` equals `landed` in both, which is the whole point of
the reconciliation. `dim_member` holds nine either way, because the reference
playbook decides that number and the telemetry does not.

## Rebuilding the screenshots

The page results come from DuckDB compiled to WebAssembly, so a capture taken on
the load event arrives before the first query answers. Chrome's `--screenshot`
flag fires exactly then. A script drives these over the DevTools protocol
instead, which waits for the rendered result count to settle.

```
npm run build --prefix site
python -m http.server --directory site/dist    # or serve dist under /flightdeck/
chrome --headless=new --remote-debugging-port=9222 about:blank
```

Then drive `Page.navigate`, poll until the count of rendered tables, cards and
charts stops rising, and call `Page.captureScreenshot` with
`captureBeyondViewport`.
