# ADR 0002. Version the reference dimensions on transaction time

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-09-12 |
| Relates to | `docs/hlad.md` section 4.3, `pipeline/22_gold.sql` |

---

## 1. Context

The gold layer held four dimensions. Three were Type 1, rebuilt from the
reference CSVs on every run. The fourth, `dim_contract_cap`, was Type 2, and
nothing read it.

That is the wrong shape twice over.

A Type 2 dimension that no fact joins is a history table wearing a dimension's
name. `dim_contract_cap` was written by `22_gold.sql` and read by
`contract_cap_history`, and by nothing else. Meanwhile the two dimensions a
reader actually meets, characters and bosses, took a rewrite in the playbook
with no record of what they said before.

So the question was not whether to add Type 2. It was where the history earns
its cost, and what a version boundary means when the source carries no dates.

## 2. The problem with the timestamp

`fixtures/reference/characters.csv` holds a key and a note. No dates. So a
version boundary has to come from somewhere other than the source.

Three options were on the table.

| Option | Where `valid_from` comes from | Cost |
|---|---|---|
| Declared | A new `valid_from` column in each reference CSV | Changes the reference contract and its tests |
| Detected | `now()`, at the run that first sees the value | An as-of join against a fact timestamp resolves nothing |
| Backdated | First version starts at a sentinel, later ones at `now()` | The first version's start date is fiction |

Every fact in this warehouse carries a timestamp from 2026-08-30. A detected
`valid_from` therefore starts after every fact, so no as-of join against
`fact_run.started_srv` can find a version in force.

## 3. Decision

`dim_character` and `dim_boss` become Type 2. The pipeline detects
`valid_from` rather than reading it: it is the moment this run first saw the
value.

`valid_from` is therefore transaction time and not valid time. It answers "when
did the warehouse learn this", not "when did this become true in the game". The
source carries no dates, so nothing else is available from it.

Facts keep joining the current version. An as-of join against a fact's own
timestamp is not supported, and `docs/hlad.md` section 4.3 says so where a
reader will meet it.

`dim_app_state` and `dim_mode` stay Type 1. Section 5 gives the reasons.

Characters and bosses share one table, `dim_member`, with the dimension name as
a column. Both hold a key and a description, so two Type 2 dimensions would
otherwise be two copies of the same three passes. `dim_contract_cap` keeps its
own table, because a cap is a `BIGINT` and folding it in would store 400 as
text.

## 4. Consequences

### Accepted

- A rewritten description no longer erases what the playbook said before.
  `reference_history` publishes every version of every member.
- One table holds the passes, so a third dimension of the same shape costs one
  line in `ref_members` and no new logic.
- `dim_character` and `dim_boss` keep the columns every metric view already
  reads. No consumer changed.
- `tests/test_versioned_dimensions.py` edits the playbook between two gold
  runs, so a test exercises the second version rather than assuming it.

### Paid

- The history lives in `warehouse/flightdeck.duckdb` and nowhere else. Deleting
  that file resets it. `demo.sh` leaves it in place, which is the only
  protection a design here can offer.
- A reader cannot ask what a run looked like under the playbook of its day. The
  timestamps do not support the question, and pretending otherwise would be
  worse than declining it.
- Two more published files, `reference_history.parquet` and
  `reference_governance.parquet`, 2,864 bytes together. ADR 0001 tracks the
  page-load cost that every published table adds.

### Triggers to revisit

- A reference CSV gains real dates. The declared option then becomes available,
  and an as-of join starts answering something.
- A fact needs the version in force at its own timestamp. That needs a
  surrogate key on the fact, which this decision deliberately does not add.

## 5. Alternatives rejected

| Option | Why not |
|---|---|
| Version `dim_app_state` too | `is_run_state` is arithmetic, not description. `fact_run.sim_active_s` sums the pulses it flags, so reclassifying one state rewrites every historical run's play time. Versioning it without a fact that joins as-of records the change and fixes nothing. It is the strongest remaining candidate and section 6 of the HLAD tracks it |
| Version `dim_mode` | Same shape as characters, and one line to add. Nothing published names a mode, so the history would hold rows no query reads. That is the `dim_contract_cap` mistake again |
| Declared dates in the CSVs | The honest option, and the only one where a boundary is a fact rather than an artifact of when the pipeline ran. It changes the reference contract, which is a larger decision than this one |
| Backdate the first version | An as-of join would resolve, on a date nobody observed. A query that works on fiction is worse than a query that declines |
| Add a surrogate key now | No fact can use it, because no as-of join is supported. A key with no query behind it is scaffolding |
