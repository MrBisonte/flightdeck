# ADR 0003. Declare valid time in the reference files

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-10-02 |
| Supersedes | ADR 0002, on where `valid_from` comes from. Its choice of which dimensions to version stands |
| Relates to | `docs/hlad.md` section 4.3, `pipeline/22_gold.sql`, `fixtures/reference/README.md` |

---

## 1. Context

ADR 0002 stamped `valid_from` with `now()` on the run that first saw a value,
and kept the history in `warehouse/flightdeck.duckdb`. The Pages workflow builds
on a fresh runner, so every deploy starts from an empty warehouse.

| Symptom on the published site | Cause |
|---|---|
| `valid_from` is the time of the latest build | Every value is new to the first run of every deploy |
| Every member sits at version 1 | No earlier run survives to compare against |
| `reference_history` can never show a second version | Same cause |

The history existed only on a machine that never deleted its database.

## 2. Decision

Every versioned value carries its own dates, in the file that holds it.

| Source | One row per | `valid_from` |
|---|---|---|
| `characters.csv`, `boss_kinds.csv` | Version of a member | Commit date of the first crow-archer `master` commit whose `src/` contains the key as a quoted literal |
| `caps` in `contracts/flight_log.yml` | Value a cap has held | Commit date of the commit that declared the value in this contract |

`valid_to` stays empty while a version is in force. A change gives the old row a
`valid_to` and adds a row that starts at the same instant. A withdrawn member
gets a `valid_to` and no successor. Nobody edits a row in place or deletes one.

`dim_member` and `dim_contract_cap` become plain rebuilds of those rows. The
three passes that compared the source with an earlier run are gone.

## 3. Two sources of valid time

A member is a fact about the game, so its date comes from the game. A cap is a
rule this contract enforces, and quarantine runs here, so its date comes from
the contract.

The game cannot date the caps. Its constants reached crow-archer `master` in one
squash merge, at 21:47 UTC on 2026-08-30, and no commit from the branch before
it survives.

## 4. Consequences

### Accepted

- A rebuild from nothing produces the same history.
  `tests/test_versioned_dimensions.py` builds twice from an empty warehouse and
  compares every version and every date.
- Every member predates every fact, so an as-of join resolves.
  `tests/test_gold.py` joins each run and each boss encounter to the version in
  force when it started, and finds exactly one.
- A reader can check every date on the Governance page against a git history.
- Deleting `warehouse/flightdeck.duckdb` loses nothing.

### Paid

- A new description is two edits to a CSV, not one. A test rejects a file
  where two versions of a member overlap or a member has two open rows.
- A member's date says when the key reached the game, not when the description
  became true. The descriptions are this repository's summary of the playbook.
- Each cap in `contracts/flight_log.yml` is now a list of versions.
  `tests/test_contract.py` compares every version, dates included, with
  `pipeline/10_typed.sql`.
- `reference_governance.first_seen` is now `first_valid_from`. The old name
  described when the pipeline saw a value, which no column records any more.

### Unchanged

- Facts join the current version through `dim_character` and `dim_boss`, and no
  fact carries a version key. A test runs the as-of join, and no published view
  uses it yet.
- `dim_app_state` and `dim_mode` stay Type 1, for the reasons in ADR 0002.

## 5. Alternatives rejected

| Option | Why not |
|---|---|
| Keep the database between deploys with `actions/cache` | GitHub evicts a cache after 7 days without use, so the history could reset with no warning |
| State the limit on the page and keep `now()` | Accurate, and the published history stays meaningless |
| Date members by the playbook commit | The playbook reached `master` at 21:47 UTC on 2026-08-30, after three of the four fixture sessions. An as-of join from those runs finds nothing |
| Date members by when this repository first listed them | 2026-08-31, after every fact from 2026-08-30. Same failure |
