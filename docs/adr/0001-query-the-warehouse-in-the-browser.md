# ADR 0001 — Query the warehouse in the reader's browser

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-09-10 |
| Relates to | `docs/hlad.md` section 2.1, `site/src/explore.md` |

---

## 1. Context

The site publishes twenty-two curated Parquet files. Four pages answer questions
the author picked. A reader with a different question had no way to ask it.

Observable Framework already runs DuckDB, compiled to WebAssembly, on every page
that declares a `sql` front matter block. The engine, the Parquet reader and the
declared tables all live in the reader's tab before the first paragraph appears.
A query box therefore costs one text area and one function call. It needs no
service, no endpoint and no new dependency.

Feasibility was never the open question. Cost was.

## 2. The measurement that decided it

Framework picks how to register a Parquet file by that file's size.

```js
// site/node_modules/@observablehq/framework/dist/client/stdlib/duckdb.js:218
if (/\.parquet$/i.test(file.name)) {
  const table = file.size < 5e7 ? "TABLE" : "VIEW";
  return await connection.query(`CREATE ${table} '${name}' AS SELECT * FROM parquet_scan('${file.name}')`);
}
```

Under fifty million bytes Framework writes `CREATE TABLE ... AS SELECT *`. That
downloads the whole file and materialises it into WebAssembly memory. Above the
threshold it writes a view instead, and DuckDB then reads byte ranges on demand.

So Framework loads eagerly, not lazily, at every size this project will reach.
Registration fires on the page's first `sql` call and covers every declared
table at once. A page that declares twenty-two tables pulls twenty-two files.

| Measure | Value | How to reproduce |
|---|---|---|
| Curated Parquet files | 22 | `ls warehouse/curated/*.parquet` |
| Total bytes, all files | 44,937 | `ls -l`, fifth column, summed |
| Largest file, `spans.parquet` | 11,625 bytes | `ls -l` |
| Framework's table threshold | 50,000,000 bytes | the snippet above |
| Warehouse against that threshold | under one tenth of one percent | 44,937 over 50,000,000 |

> **Note.** Measure with `ls -l` and not with `du`. `du` rounds every file up to
> a four kilobyte block, which reports this warehouse as 100 kB, more than twice
> its real size.

Three fixture sessions produce this warehouse. The whole thing is smaller than a
single web font, so eager loading costs less than range requests would.

## 3. Decision

The site gains one page, `/explore`. It declares all twenty-two tables. It
carries two blocks: a catalog query over `duckdb_columns()`, and a text area
that runs whatever the reader types.

DuckDB executes that SQL in the reader's tab. No query reaches a server.

## 4. Consequences

### Accepted

- A reader asks their own questions, against the same Parquet the other pages
  read. The two can never disagree, because they share one copy.
- The catalog costs one query. `duckdb_columns()` already knows every table and
  column, so the page needs no hand-written schema list to drift out of date.
- Nothing new runs on a server, so nothing new needs credentials, rate limits or
  patching. The attack surface does not grow.
- A wrong query fails in place. The error replaces the result and the page keeps
  running.

### Paid

- The first query on `/explore` materialises all twenty-two tables. At the
  measured size a reader will not notice. The cost grows with the warehouse.
- A runaway query, such as a cross join over `spans`, freezes the reader's tab.
  This page ships no guard against that. One tab is the whole blast radius.
- Every page listing a table pays for that table. `/explore` therefore carries
  the largest front matter block on the site.

### Revisit when

Either trigger is enough:

- Total curated bytes pass roughly ten million. The eager load then becomes a
  real page-load cost, and `/explore` should register tables on demand.
- Any single file passes fifty million bytes. Framework switches that file to a
  view on its own, and the page starts mixing eager and lazy tables.

## 5. Alternatives rejected

| Option | Why not |
|---|---|
| A query box on the Overview page | It puts twenty-two table registrations on a narrative page, and every reader of that page pays for them |
| One box per page, scoped to that page's tables | The interesting joins cross pages. `fact_run` against `quarantine` answers a real question, and no single page holds both |
| A server-side query endpoint | It needs a host, credentials, rate limits and a plan for a hostile query. The browser already runs the engine for free |
| No query box | It leaves the reader with only the questions the author picked, which is the gap this ADR closes |
