# Reference dimensions

This directory holds the second source in the pipeline.

Telemetry says which values **occurred**. It cannot say which values are
**possible**. Four of these tables carry the documented domain. The fifth,
`origins.csv`, carries the places the game runs.

```
   telemetry     "the player chose archer"      what happened
        +
   reference     "5 characters exist"           what could happen
        =
   coverage      "4 of 5 played, sapper never"  what nobody tested
```

## Source

Four tables come from the crow-archer playbook
`docs/playbooks/monitored-playtest.md`. That page is the source of truth for the
wire format.

| Table | Rows | Source in the playbook |
|---|---|---|
| `app_states.csv` | 15 | The pulse section. The render dispatch branches |
| `modes.csv` | 3 | The pulse table |
| `characters.csv` | 5 | The pulse table |
| `boss_kinds.csv` | 4 | The observed boss values |

## `origins.csv`, the fifth table

This one has a different source. The playbook documents the wire format, and
the wire format carries no origin. It carries `href`, so
[`pipeline/10_typed.sql`](../../pipeline/10_typed.sql) parses the origin out of
that and joins it here.

| Column | Meaning |
|---|---|
| `origin` | Scheme, host and port, with no path and no trailing slash |
| `kind` | `local`, `private` or `public`. The class a masked origin keeps |
| `may_publish` | Whether `warehouse/curated` may carry the origin itself |
| `note` | Which deployment this row describes |

Two consumers read the file and neither keeps its own copy.
[`scripts/sanitize_flightlog.py`](../../scripts/sanitize_flightlog.py) keeps a
listed origin in a live capture and masks the rest.
[`pipeline/25_publish.sql`](../../pipeline/25_publish.sql) applies
`may_publish` at the boundary of the public site.

The three `.invalid` rows are the masks. RFC 2606 reserves that suffix, so a
mask can never name a real host. Listing them keeps one rule for the gate and
one join for the pipeline, rather than a special case in each.

The list works one way. The sanitizer masks any origin no row names, and passes
none of them through. A missing row costs a masked value. A missing rule costs
a disclosure, and DEF-13 in [`docs/defect-log.md`](../../docs/defect-log.md)
shows what that disclosure looked like.

## Why the join matters

The join does two jobs.

1. **It conforms the dimensions.** A run state becomes a typed key. It stops
   being a loose string.
2. **It exposes coverage gaps.** A documented value that never appears is a gap
   in the recorded sessions. Telemetry alone hides that gap.

## The result on the committed fixtures

| Dimension | Played | Documented | Coverage | Never played |
|---|---|---|---|---|
| `state` | 10 | 15 | 67% | controls, inventory, mapselect, multiplayer, win |
| `mode` | 1 | 3 | 33% | siege, waves |
| `char` | 4 | 5 | 80% | sapper |
| `boss` | 4 | 4 | 100% | none |

Use the `dimension_coverage` view to reproduce this table.

## Drift protection

The contract in `contracts/flight_log.yml` and the four playbook tables come
from one page. `tests/test_contract.py` compares them. The test fails when they
differ. It pins the `kind` column of `origins.csv` against the same contract,
even though that table describes a deployment rather than the game.

```
   playbook  -->  contracts/flight_log.yml  --+
                                              +--> test_contract.py compares
   playbook  -->  fixtures/reference/*.csv  --+
```
