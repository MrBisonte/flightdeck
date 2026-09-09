---
title: Overview
sql:
  contract_reconciliation: ./data/curated/contract_reconciliation.parquet
  warehouse_manifest: ./data/curated/warehouse_manifest.parquet
  loss_accounting: ./data/curated/loss_accounting.parquet
  alarms_by_class: ./data/curated/alarms_by_class.parquet
  error_report: ./data/curated/error_report.parquet
---

# flightdeck

A browser game writes a flight log. This pipeline reads that log, checks it
against a written contract, and publishes the result as open Parquet.

Every number on this page is the result of a query. The query sits above its
result. No number is typed into the text.

## 1. Does the contract hold?

The pipeline drops nothing. A record that breaks the contract goes to
quarantine with a reason. So the two parts must add up to the whole.

```sql echo id=recon
SELECT landed_records::INTEGER      AS landed,
       clean_records::INTEGER       AS clean,
       quarantined_records::INTEGER AS quarantined,
       reconciles
FROM contract_reconciliation
```

```js
const r = recon.get(0);
display(html`<div class="grid grid-cols-3">
  <div class="card"><h2>Records landed</h2><span class="big">${r.landed}</span></div>
  <div class="card"><h2>Passed the contract</h2><span class="big">${r.clean}</span></div>
  <div class="card"><h2>Held in quarantine</h2><span class="big">${r.quarantined}</span></div>
</div>`);
```

```js
display(html`<div class="card">
  <h2>clean + quarantined = landed</h2>
  <span class="big">${r.clean} + ${r.quarantined} = ${r.landed}</span>
  <p>${r.reconciles
    ? "The counts reconcile. The pipeline lost nothing."
    : "The counts do not reconcile. Records are missing."}</p>
</div>`);
```

The pipeline computes that boolean. The page reads it. The same check runs in
CI on every commit, so a broken contract fails the build.

## 2. How fresh is this?

Two clocks, and they are not the same. One says when the site was built. One
says when the data last arrived. `srv` is the arrival time, stamped by the
server, so the page cannot write it.

```sql echo id=manifest
SELECT records::INTEGER  AS records,
       sessions::INTEGER AS sessions,
       strftime(to_timestamp(first_srv / 1000.0)::TIMESTAMP, '%Y-%m-%d %H:%M') AS first_utc,
       strftime(to_timestamp(last_srv  / 1000.0)::TIMESTAMP, '%Y-%m-%d %H:%M') AS last_utc
FROM warehouse_manifest
```

```js
const m = manifest.get(0);
const built = await FileAttachment("./data/built.json").json();
display(html`<div class="grid grid-cols-2">
  <div class="card"><h2>Data last landed</h2><span class="big">${m.last_utc}</span><p>UTC. First record ${m.first_utc}.</p></div>
  <div class="card"><h2>Site last built</h2><span class="big">${built.built_at}</span><p>UTC. Set when the build ran.</p></div>
</div>`);
```

```js
display(html`<p>The warehouse holds ${m.records} records over ${m.sessions}
page loads. That is a small sample. Read these numbers as a demonstration of
the method, not as a large study.</p>`);
```

## 3. Did anything get lost?

Every event carries an id. The ids in one page load run in sequence. A gap in
that sequence means an event never arrived.

```sql echo id=loss
SELECT events_received::INTEGER         AS received,
       ids_expected::INTEGER            AS expected,
       events_lost_by_id_gap::INTEGER   AS lost,
       peak_events_in_one_beat::INTEGER AS peak,
       cap_events_per_beat::INTEGER     AS cap,
       peak_pct_of_cap                  AS pct_of_cap
FROM loss_accounting
```

```js
const l = loss.get(0);
display(html`<div class="grid grid-cols-3">
  <div class="card"><h2>Events received</h2><span class="big">${l.received}</span></div>
  <div class="card"><h2>Events expected</h2><span class="big">${l.expected}</span></div>
  <div class="card"><h2>Lost to an id gap</h2><span class="big">${l.lost}</span></div>
</div>`);
```

The contract caps how many events one beat may carry. The bar shows the busiest
beat in the data against that cap.

```js
Plot.plot({
  height: 110,
  marginLeft: 90,
  marginRight: 40,
  x: {domain: [0, l.cap], label: "events in one beat", grid: true},
  y: {label: null},
  marks: [
    Plot.barX([{name: "busiest beat", value: l.peak}],
      {x: "value", y: "name", fill: "currentColor", fillOpacity: 0.65}),
    Plot.ruleX([l.cap], {stroke: "red", strokeWidth: 2}),
    Plot.text([{name: "busiest beat", value: l.peak}],
      {x: "value", y: "name", text: () => `${l.peak} of ${l.cap}, ${l.pct_of_cap}%`, dx: 6, textAnchor: "start"})
  ]
})
```

## 4. Alarms raised

The recorder raises an alarm when it sees trouble in the page. The pipeline
groups them by class.

```sql echo id=alarms
SELECT class,
       n::INTEGER          AS alarms,
       page_loads::INTEGER AS page_loads,
       array_to_string(states_when_raised, ', ') AS states_when_raised
FROM alarms_by_class
ORDER BY alarms DESC
```

```js
Inputs.table(alarms)
```

## 5. Errors caught

Every error the recorder caught, in arrival order, with the frame that threw it.

```sql echo id=errors
SELECT session_id,
       page_load_seq,
       strftime(arrived::TIMESTAMP, '%Y-%m-%d %H:%M:%S') AS arrived_utc,
       msg,
       top_frame,
       top_location
FROM error_report
ORDER BY arrived
```

```js
Inputs.table(errors)
```

Read [Four clocks](./four-clocks) next. It shows how the pipeline tells a page
that went quiet from a page that reported the wrong time.
