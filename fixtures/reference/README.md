# Reference dimensions

This directory holds the second source in the pipeline.

Telemetry says which values **occurred**. It cannot say which values are
**possible**. These four tables carry the documented domain.

```
   telemetry     "the player chose archer"      what happened
        +
   reference     "5 characters exist"           what could happen
        =
   coverage      "4 of 5 played, sapper never"  what nobody tested
```

## Source

The tables come from the crow-archer playbook
`docs/playbooks/monitored-playtest.md`. That page is the source of truth for the
wire format.

| Table | Rows | Origin in the playbook |
|---|---|---|
| `app_states.csv` | 15 | The pulse section. The render dispatch branches |
| `modes.csv` | 3 | The pulse table |
| `characters.csv` | 5 | The pulse table |
| `boss_kinds.csv` | 4 | The observed boss values |

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

The contract in `contracts/flight_log.yml` and these CSV files share one origin.
`tests/test_contract.py` compares them. The test fails when they differ.

```
   playbook  -->  contracts/flight_log.yml  --+
                                              +--> test_contract.py compares
   playbook  -->  fixtures/reference/*.csv  --+
```
