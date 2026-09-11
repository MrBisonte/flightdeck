---
title: Explore
sql:
  alarms_by_class: ./data/curated/alarms_by_class.parquet
  boss_encounters_by_kind: ./data/curated/boss_encounters_by_kind.parquet
  character_usage: ./data/curated/character_usage.parquet
  clock_skew: ./data/curated/clock_skew.parquet
  contract_cap_history: ./data/curated/contract_cap_history.parquet
  contract_reconciliation: ./data/curated/contract_reconciliation.parquet
  dimension_coverage: ./data/curated/dimension_coverage.parquet
  error_report: ./data/curated/error_report.parquet
  fact_boss_encounter: ./data/curated/fact_boss_encounter.parquet
  fact_run: ./data/curated/fact_run.parquet
  frame_time_by_span: ./data/curated/frame_time_by_span.parquet
  game_summary: ./data/curated/game_summary.parquet
  gap_explained: ./data/curated/gap_explained.parquet
  incident_timeline: ./data/curated/incident_timeline.parquet
  loss_accounting: ./data/curated/loss_accounting.parquet
  quarantine: ./data/curated/quarantine.parquet
  reference_governance: ./data/curated/reference_governance.parquet
  reference_history: ./data/curated/reference_history.parquet
  run_outcomes: ./data/curated/run_outcomes.parquet
  session_context: ./data/curated/session_context.parquet
  session_summary: ./data/curated/session_summary.parquet
  spans: ./data/curated/spans.parquet
  srv_gaps: ./data/curated/srv_gaps.parquet
  warehouse_manifest: ./data/curated/warehouse_manifest.parquet
---

# Explore

The other pages answer questions I chose. This page lets you ask your own.

DuckDB runs inside your browser, compiled to WebAssembly. It reads the same
Parquet files the other pages read. Your query never reaches a server, and it
cannot change the published data.

<div class="only-engineering">

This page carries every published table. The catalog below shows its own SQL,
as every page here does.

</div>
<div class="only-dashboard">

This page carries every published table. This view hides the catalog query.
The box below still runs whatever you type.

</div>

## The catalog

Start here. The query below lists every column of every table the site ships,
with the type DuckDB reads it as.

```sql echo id=catalog
SELECT table_name,
       column_name,
       data_type
FROM duckdb_columns()
WHERE schema_name = 'main'
ORDER BY table_name, column_index
```

```js
display(Inputs.table(catalog, {rows: 12}));
```

## The query box

Type SQL, then press Run. A mistake costs nothing: the error appears where the
result would, and the page stays live.

```js
const query = view(Inputs.textarea({
  label: null,
  rows: 5,
  width: "100%",
  submit: "Run",
  value: "SELECT run_seq, character_key, duration_s, kills\nFROM fact_run\nORDER BY duration_s DESC\nLIMIT 10"
}));
```

```js
let result;
try {
  result = Inputs.table(await sql([query]), {rows: 15});
} catch (error) {
  result = html`<pre style="color:#c02626;white-space:pre-wrap">${error.message}</pre>`;
}
display(result);
```

Three tables reward a first look. `fact_run` holds one row per run, `spans`
holds one row per frame-time sample, and `quarantine` holds every record the
contract rejected, with the reason.
