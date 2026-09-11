# QA evidence

Two artifacts, both regenerated rather than written by hand.

| Artifact | What it holds | How to rebuild |
|---|---|---|
| `e2e-evidence.csv` | One row per relation: layer, kind, row count, column list, a real sample row, and the counts the Parquet and PostgreSQL copies report | `./demo.sh all` then `python scripts/qa_evidence.py` |
| `screenshots/` | Every page of the built site, full height, in both views | See below |

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
