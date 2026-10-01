---
title: Governance
sql:
  reference_governance: ./data/curated/reference_governance.parquet
  reference_history: ./data/curated/reference_history.parquet
  contract_cap_history: ./data/curated/contract_cap_history.parquet
  app_state_history: ./data/curated/app_state_history.parquet
  dimension_coverage: ./data/curated/dimension_coverage.parquet
---

# Governance

The game page reads the gold layer to ask what happened in the game. This page
reads the same layer to ask a different question. Who decided what a value
means, and would anyone notice if that decision moved?

<div class="only-engineering">

Every number here is the result of a query, and its SQL syntax sits above its
result for transparency. There are no hardcoded values typed into the text.

</div>
<div class="only-dashboard">

Every number here is the result of a query. The queries are hidden in this view.
Switch to Engineering, top right, to read the SQL above each result.

</div>

## 1. What is under version control

The gold dimensions that keep their history are named below. Each version
carries the dates its source file declares, so every rebuild shows the same
history.

```sql echo id=totals
SELECT members,
       members_in_force,
       versions,
       superseded,
       deepest_history,
       last_change
FROM reference_governance
WHERE dimension = 'every dimension'
```

```js
// Minutes in UTC, which is what every timestamp in this warehouse means. The
// full value stays in the published Parquet for anyone who needs the second.
const utc = (d) => d == null ? "" : new Date(d).toISOString().slice(0, 16).replace("T", " ");

// The two columns that hold a sentence rather than a word. presentation.css
// puts a floor under every table, which is enough for the rest.
const WIDTHS = {description: 150, never_seen: 300};
```

```js
const g = totals.get(0);
display(html`<div class="grid grid-cols-3">
  <div class="card"><h2>Members under version control</h2><span class="big">${g.members}</span></div>
  <div class="card"><h2>Versions on record</h2><span class="big">${g.versions}</span></div>
  <div class="card"><h2>Superseded versions</h2><span class="big">${g.superseded}</span></div>
</div>`);
```

Every version is still current, because no reference value has changed since
its source declared it. The history exists so that the first change leaves a
record, and `tests/test_versioned_dimensions.py` declares a second version to
prove that it does.

## 2. One policy per dimension

A character or a boss dates from the first game commit that names it. A
contract cap dates from the commit that put it in the contract.

```sql echo id=policy
SELECT dimension,
       members,
       versions,
       superseded,
       first_valid_from
FROM reference_governance
WHERE dimension <> 'every dimension'
ORDER BY dimension
```

```js
display(Inputs.table(policy, {rows: 8, format: {first_valid_from: utc}, width: WIDTHS}));
```

`dim_mode` is absent, and that is a decision rather than an omission. Nothing
published names a mode, so a history would hold rows nobody reads. ADR 0002
carries the argument.

## 3. What the playbook says today

The table below gives each version the date it took effect. A rewritten
description closes the row you see here and opens the next one.

```sql echo id=history
SELECT dimension,
       member_key,
       version_seq,
       description,
       valid_from,
       status
FROM reference_history
ORDER BY dimension, member_key, version_seq
```

```js
display(Inputs.table(history, {rows: 16, format: {valid_from: utc}, width: WIDTHS}));
```

A run state carries two flags rather than a description, so it keeps its own
table. `is_run_state` decides which pulses count as play time, and every run
reads the version in force while it ran. A state reclassified tomorrow
changes the runs after tomorrow and no run before it.

```sql echo id=states
SELECT state_key,
       version_seq,
       is_run_state,
       in_run,
       valid_from,
       status
FROM app_state_history
ORDER BY state_key, version_seq
```

```js
display(Inputs.table(states, {rows: 16, format: {valid_from: utc}, width: WIDTHS}));
```

## 4. What the contract allowed

Each quarantine decision depends on the cap in force at the time. The contract
keeps every value a cap has held, with its dates, so a reader can still check an
old decision against its cap.

```sql echo id=caps
SELECT cap_key,
       cap_value::INTEGER AS cap_value,
       valid_from,
       status
FROM contract_cap_history
ORDER BY cap_key, valid_from
```

```js
display(Inputs.table(caps, {rows: 10, format: {valid_from: utc}, width: WIDTHS}));
```

## 5. What nobody exercised

A documented value that never appears in the data is a governance question, not
a bug. It means the reference and the telemetry disagree about what the game can
do, and one of the two needs a look.

```sql echo id=coverage
SELECT dimension,
       documented::INTEGER AS documented,
       exercised::INTEGER  AS exercised,
       array_to_string(never_seen, ', ') AS never_seen
FROM dimension_coverage
ORDER BY dimension
```

```js
display(Inputs.table(coverage, {rows: 9, width: WIDTHS}));
```

The never seen column names every documented value the data does not show. A
narrow capture from one player produces that, and a wider one would close most
of the gap.

## What this page cannot tell you

Each date answers one narrow question.

| Date | Records | Does not record |
|---|---|---|
| `valid_from`, member | the first game commit that names the key | when the description became true |
| `valid_from`, cap | the commit that put the value in the contract | when the game adopted the limit |
