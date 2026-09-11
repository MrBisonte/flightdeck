---
title: Governance
sql:
  reference_governance: ./data/curated/reference_governance.parquet
  reference_history: ./data/curated/reference_history.parquet
  contract_cap_history: ./data/curated/contract_cap_history.parquet
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

Three of the four gold dimensions keep their history. A version opens when this
pipeline first sees a value and closes when the value moves.

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
const g = totals.get(0);
display(html`<div class="grid grid-cols-3">
  <div class="card"><h2>Members under version control</h2><span class="big">${g.members}</span></div>
  <div class="card"><h2>Versions on record</h2><span class="big">${g.versions}</span></div>
  <div class="card"><h2>Superseded versions</h2><span class="big">${g.superseded}</span></div>
</div>`);
```

Zero superseded versions is the true reading, not a broken query. No reference
value has moved since this warehouse first ran. The history exists so that the
first move leaves a record, and `tests/test_versioned_dimensions.py` edits the
playbook between two runs to prove that it does.

## 2. One policy per dimension

`contract cap` carries an older first version than the other two. It was the
first dimension here to keep a history, and the timestamps say so.

```sql echo id=policy
SELECT dimension,
       members,
       members_in_force,
       versions,
       superseded,
       first_seen,
       last_change
FROM reference_governance
WHERE dimension <> 'every dimension'
ORDER BY dimension
```

```js
display(Inputs.table(policy, {rows: 8, width: {first_seen: 190, last_change: 190}}));
```

`dim_app_state` and `dim_mode` are absent, and that is a decision rather than an
omission. Nothing published names a mode. `dim_app_state` carries a flag that
arithmetic reads, so versioning it without a fact that joins as-of would record
the change and fix nothing. ADR 0002 carries both arguments.

## 3. What the playbook says today

Nine members, each at version 1, each with the moment this pipeline first read
it. A rewritten description closes the row you see here and opens the next one.

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
display(Inputs.table(history, {rows: 16, width: {valid_from: 190}}));
```

## 4. What the contract allowed

A record sits in quarantine because a cap said so. Move the cap and that
decision stops being reproducible, unless the old value survives. It does.

```sql echo id=caps
SELECT cap_key,
       cap_value::INTEGER AS cap_value,
       valid_from,
       status
FROM contract_cap_history
ORDER BY cap_key, valid_from
```

```js
display(Inputs.table(caps, {rows: 10}));
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
display(Inputs.table(coverage, {rows: 9, width: {never_seen: 420}}));
```

A third of the mode dimension and a third of the app states never appear. Three
fixture sessions from one player produce that, and a wider capture would close
most of the gap.

## What this page cannot tell you

It cannot tell you what a run looked like under the playbook of its day.
`valid_from` records when this pipeline learned a value, not when the value
became true in the game. The reference files carry a key and a note, and no
dates, so an as-of join against a run's own timestamp would resolve nothing.
ADR 0002 records that cost and the two options rejected to accept it.
