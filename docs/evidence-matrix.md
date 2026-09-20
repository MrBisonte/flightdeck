# Evidence matrix

Each claim on this page maps to one of three things:

```
   a command that runs   |   a file that exists   |   a commit you can open
```

`./demo.sh` produced every number here. A clean clone reproduces them.

## Claims and evidence

| Area | Claim | Repo | Artifact | Command |
|---|---|---|---|---|
| Lakehouse, open formats | Raw telemetry lands as Hive partitioned Parquet | flightdeck | `warehouse/raw/session_date=*/session_id=*/` | `./demo.sh raw` |
| Embedded analytics on open files | An embedded engine queries the curated Parquet in place | flightdeck | Every layer reads Parquet. No warehouse sits in the middle. `ls warehouse/curated` lists the files | `./demo.sh publish` |
| Governance, data contracts | A typed schema defines each record, and rows that break it go to quarantine | flightdeck | `contracts/flight_log.yml`, the `contract_caps` table, `quarantine` | `./demo.sh typed` |
| Documentation levels | Architecture pages that go from one system picture down to each table | crow-archer, flightdeck | `monitored-playtest.md`, `docs/architecture.md` | Open either page |
| Data engineering, ELT | Config, not code, defines each pipeline | quacknettor | `configs/pipelines.yml`, config driven adapters | Open the config |
| Performance engineering | Frame time by span, each percentile with its sample count | flightdeck | `frame_time_by_span`, over 5688 measurements | `./demo.sh curated` |
| Snowflake | The same Parquet loads into Snowflake. Documented, not run | quacknettor | The Snowflake adapter. `COPY INTO` reads the same Parquet | Documented only |
| Typed layer for consumers | A typed layer that downstream consumers read | flightdeck | `session_context`, one typed row per page load | `./demo.sh export` |
| Conformed dimensions | Shared reference dimensions, with their coverage reported | flightdeck | `fixtures/reference/` joined to the telemetry | `./demo.sh curated` |
| Slowly changing dimensions | Dimension history survives a fresh build | flightdeck | `dim_member`, Type 2 on characters and bosses, with ADR 0002 for the two that stay Type 1. History in `reference_history` | `./demo.sh gold` |
| Data minimization | The committed logs carry no real user agent and no real origin. A check enforces it | flightdeck | `sanitize_flightlog.py`, `SANITIZATION.md` | `python scripts/sanitize_flightlog.py --check fixtures/raw` |
| CI and test gating | CI tests every change | all three | GitHub Actions. 98 tests. CI gates the reconciliation | Open the Actions tab |
| Evidence based decisions | Decisions follow recorded evidence, from the alarm to the fix | crow-archer, flightdeck | `incident_timeline`, then the stack, then PR 42 | `./demo.sh curated` |

## The numbers

| Measure | Value | Source |
|---|---|---|
| Records processed | 1546 | `contract_reconciliation` |
| Reconciliation | 1545 clean + 1 quarantined = 1546 | `contract_reconciliation` |
| Page loads across 4 files | 17 | `sessions` |
| Clock agreement, localhost | 0 to 9 ms, mean 0.91 | `clock_skew` |
| Clock agreement, published build | 473 to 571 ms, mean 478.07 | `clock_skew` |
| Gaps that throttling explains | 20 of 25 | `gap_explained` |
| Gaps that throttling does not explain | 1, at 472.2s | `gap_explained` |
| Crash to alarm, time to detection | 1.323 s | `incident_timeline` |
| Frame time samples | 5688 | `frame_time_by_span` |
| Telemetry lost | 0 of 3152 events | `loss_accounting` |
| Ring headroom used | 32 of 400, so 8% | `loss_accounting` |
| Dimension coverage | state 10/15, mode 1/3, char 4/5 | `dimension_coverage` |
| Full run, cold | 3 to 5 seconds | `./demo.sh` |
| crow-archer tests | 1968 in 75 files | `npm test` |
| PostgreSQL relations loaded | 12, holding 84 rows | `./demo.sh load` |
| Full run with a warm container | 5 seconds | `./demo.sh` |
| Cold container start, extra | about 9 seconds | `./demo.sh`, container stopped first |

## Known gaps

Each gap states what this data does not show.

### Gap 1: one bug shown end to end, not two

The recorder caught two bugs on its first day. The fixtures evidence one of them.

```
   BUG 1, the crash            BUG 2, the latched key
   ------------------------    ------------------------------------
   err record            OK    err record          ABSENT
   loop-dead alarm       OK    heldKeys evidence   ABSENT, all show []
   stack trace           OK    fix commit          OK
   fix + regression test OK
```

Bug 1 runs end to end. The evidence chain has four links:

```
   err record  ->  loop-dead alarm  ->  stack trace  ->  fix + test
                     1.323 s later      pathfinding     crow-archer
                                        .ts:67:30       PR 42
```

Bug 2 has its fix commit only. The playbook names `heldKeys` as the field that
exposes a latched key. All four alarms in these fixtures show `heldKeys: []`.

### Gap 2: loss accounting reports zero

The ring never overflowed. Peak use was 32 events against a cap of 400.

The mechanism is real and the number is checkable, but this data does not show
the pipeline catching a loss.

The result is a proven zero, not a caught loss.

### Gap 3: the quarantine holds one row

That row is real. It is an orphan `bye` whose `hello` sits in another file.
Nobody built a synthetic fixture for it.

The test suite proves the quarantine catches more than that one case:

| Violation | Test |
|---|---|
| An orphan record with no hello | `test_an_orphan_goodbye_is_quarantined_not_dropped` |
| A state outside the contract | `test_a_state_outside_the_contract_is_quarantined` |
| A beat over the event cap | `test_a_beat_over_the_event_cap_is_quarantined` |

This data holds one row. The tests cover three violation classes.

### Gap 4: two sources, not many

The pipeline reads two sources.

| Source | Present here? |
|---|---|
| Game telemetry | yes |
| Reference dimensions | yes |
| Anything else | no |

duckEL carries the PostgreSQL, Snowflake, S3, and Parquet adapters.

### Gap 5: the percentiles parse text

| Source | Rows | Shape |
|---|---|---|
| `alarm.trace.spans` | 24 | typed |
| Trace summary in a beat | 5688 | text |

Four samples cannot support a p95. The pipeline parses the text instead. A parse
differs from a measurement, so every percentile view prints its sample count.

### Gap 6: Snowflake does not run

The curated Parquet is what a `COPY INTO` would read. The pipeline uses no account.
It makes no external call.

### Gap 7: one game mode

| Dimension | Played | Documented |
|---|---|---|
| mode | `brawl` only | `brawl`, `waves`, `siege` |
| map | `forest`, `castle`, `maze` | more exist |

A third of the mode dimension has no test coverage. The `dimension_coverage`
view states this fact rather than hiding it.
