---
title: Four clocks
sql:
  clock_skew: ./data/curated/clock_skew.parquet
  srv_gaps: ./data/curated/srv_gaps.parquet
  gap_explained: ./data/curated/gap_explained.parquet
  incident_timeline: ./data/curated/incident_timeline.parquet
---

# Four clocks

A page reports four clocks. The page writes three of them. The server writes one.

```
   wall, perf, timestamp  -->  written by the page   -->  claims
   srv                    -->  written by the server -->  fact
```

The pipeline orders every record on `srv`. It treats the other clocks as claims, and checks them.

<div class="only-engineering">

Every number on this page is the result of a query. The query sits above its result.

</div>
<div class="only-dashboard">

Every number on this page is the result of a query. The queries are hidden in
this view. Switch to Engineering, top right, to read them.

</div>

## 1. Do the clocks agree?

`srv` minus `wall`, over every clean record, split by the origin that served
the page.

```sql echo id=skew
SELECT origin_kind           AS origin,
       records::INTEGER      AS records,
       skew_min_ms::INTEGER  AS min_ms,
       skew_mean_ms          AS mean_ms,
       skew_max_ms::INTEGER  AS max_ms
FROM clock_skew
ORDER BY origin
```

```js
const rows = skew.toArray?.() ?? Array.from(skew);
display(html`<div class="grid grid-cols-2">${rows.map((r) => html`<div class="card">
  <h2>${r.origin}</h2>
  <span class="big">${r.min_ms} to ${r.max_ms} ms</span>
  <p>Mean ${r.mean_ms} ms over ${r.records} records.</p>
</div>`)}</div>`);
```

A browser on the same machine as the recorder has almost nothing to disagree
about. A browser reaching a server over the internet carries the trip in its
skew. Reporting one number over both would describe neither, so the pipeline
splits them and the page prints what it is given.

## 2. Gaps between arrivals

A beat arrives every second. A gap of more than three seconds is worth a look. The pipeline measures the gap on `srv`, so the page cannot hide it.

```sql echo id=gaps
SELECT session_id,
       page_load_seq::INTEGER      AS page_load,
       gap_s,
       prev_vis || ' -> ' || vis   AS visibility
FROM srv_gaps
ORDER BY gap_s
```

```js
Plot.plot({
  title: `${gaps.numRows} gaps longer than three seconds, on the server clock`,
  subtitle: "A hidden tab has its one second timer clamped to about sixty seconds. That is the cluster on the line.",
  marginLeft: 180,
  x: {type: "log", label: "gap (seconds), log scale", grid: true},
  y: {label: null},
  color: {legend: true, label: "tab visibility, before -> after"},
  marks: [
    Plot.ruleX([60], {stroke: "currentColor", strokeOpacity: 0.3}),
    Plot.dot(gaps, {x: "gap_s", y: "session_id", fill: "visibility", r: 6, tip: true})
  ]
})
```

The pipeline explains each gap from `vis` alone.

```sql echo id=explained
SELECT * FROM gap_explained
```

```js
Inputs.table(explained)
```

A gap with the tab visible on both sides has no throttling explanation. The pipeline labels it and keeps it visible, rather than dropping it.

## 3. Time to detection

Every error and every alarm, in arrival order, with the seconds since the previous incident in the same session.

```sql echo id=incidents
SELECT session_id,
       page_load_seq::INTEGER                                         AS page_load,
       strftime(occurred_at::TIMESTAMP, '%Y-%m-%d %H:%M:%S.%g')       AS occurred_at_utc,
       event,
       detail,
       s_since_previous
FROM incident_timeline
ORDER BY session_id, occurred_at
```

```js
Inputs.table(incidents)
```

Read `s_since_previous` on an `alarm` row that follows an `error` row. That is the time the recorder took to notice a dead loop.
