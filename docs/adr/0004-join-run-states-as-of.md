# ADR 0004. Version the run states and join them as-of

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-10-02 |
| Supersedes | ADR 0002 and ADR 0003, where each keeps `dim_app_state` at Type 1 |
| Relates to | `docs/hlad.md` section 4.3, `pipeline/22_gold.sql` |

---

## 1. Context

`app_states.csv` gives each run state two flags. `in_run` says the state occurs
during a run. `is_run_state` says the simulation clock advances.
`fact_run.sim_active_s` sums the time of the pulses that `is_run_state` flags.

ADR 0002 kept `dim_app_state` at Type 1 for two reasons. Versioning it without a
fact that joins as-of records a change and fixes nothing. And the CSV carried no
date to join on. ADR 0003 gave the reference files declared dates, which
removes the second reason.

At Type 1, reclassifying one state rewrites the play time of every past run.

## 2. Decision

| Part | Change |
|---|---|
| `app_states.csv` | One row per version, with `valid_from` and `valid_to`, dated the way ADR 0003 dates a member |
| `dim_app_state` | Type 2, rebuilt from those rows |
| `run_pulse` | Joins the version in force when each pulse arrived, on `srv` |
| `app_state_history` | New published view, one row per version of a state |

The as-of join needs no surrogate key on the fact. `run_pulse` reads the flags
it needs at join time, and every fact above it sums those flags.

`app_state_history` is its own file rather than more rows in
`reference_history`. A state carries two flags and a member carries a
description. A shared table would hide a change to a flag behind an unchanged
description.

## 3. Consequences

### Accepted

- A state reclassified from a later date changes the runs after that date and
  no run before it. `tests/test_versioned_dimensions.py` pins both directions.
- `run_pulse` uses an inner join, so a pulse whose state had no version in
  force would vanish. A test fails if any pulse finds other than exactly one
  version.

### Paid

- One more published file, `app_state_history.parquet`. ADR 0001 tracks the
  cost of each file a page loads.
- `srv_time()`, a macro in `00_raw.sql`, replaces three copies of the same
  conversion from epoch milliseconds, and the join is its fourth caller.

### Unchanged

- `dim_mode` stays Type 1. Nothing published names a mode.
- Characters and bosses still reach a fact through the current version.
