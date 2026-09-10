# Evidence matrix

Each claim on this page maps to one of three things:

```
   a command that runs   |   a file that exists   |   a commit you can open
```

`./demo.sh` produced every number here. A clean clone reproduces them.

## Claims and evidence

| Competency | CV claim | Repo | Artifact | Command | Fallback |
|---|---|---|---|---|---|
| Lakehouse, open formats | "open lakehouse formats, Apache Parquet, Apache Iceberg, Apache Arrow, Hive partitioned object storage" | flightdeck | `warehouse/raw/session_date=*/session_id=*/` | `./demo.sh raw` | Screenshot of the tree |
| De-vendoring the analytics path | "Re-engineered proprietary warehouse aggregations into an open lakehouse format ... queryable from an embedded engine" | flightdeck | Every layer reads Parquet. No warehouse sits in the middle | `./demo.sh publish` | `ls warehouse/curated` |
| Governance, data contracts | "typed data contracts, governance as code, data quality and lineage" | flightdeck | `contracts/flight_log.yml`, the `contract_caps` table, `quarantine` | `./demo.sh typed` | The reconciliation table |
| Documentation levels | "architecture documentation at conceptual, logical and physical levels" | crow-archer, flightdeck | `monitored-playtest.md`, `docs/architecture.md` | Open either page | Printed copy |
| Data engineering, ELT | "metadata driven ETL and ELT engines, data pipelines" | quacknettor | `configs/pipelines.yml`, config driven adapters | Open the config | The README |
| Performance engineering | "performance engineering at query, parameter and OS level" | flightdeck | `frame_time_by_span`, over 3978 measurements | `./demo.sh curated` | The terminal cast |
| Snowflake | "Snowflake (SnowPro Core certified)" | quacknettor | The Snowflake adapter. `COPY INTO` reads the same Parquet | Documented only | The documented path |
| Typed layer for consumers | "typed data layers for downstream AI consumption" | flightdeck | `session_context`, one typed row per page load | `./demo.sh export` | The printed payload |
| Conformed dimensions | "data quality", "metadata driven ETL" | flightdeck | `fixtures/reference/` joined to the telemetry | `./demo.sh curated` | The coverage table |
| Data minimization | "GDPR compliant design in regulated European industries" | flightdeck | `sanitize_flightlog.py`, `SANITIZATION.md` | `python scripts/sanitize_flightlog.py --check fixtures/raw` | The change table |
| CI and test gating | "CI/CD with automated test gating on every change" | all three | GitHub Actions. 35 tests. CI gates the reconciliation | Open the Actions tab | The badge |
| Evidence based decisions | "shipping working proofs of concept before asking for investment" | crow-archer, flightdeck | `incident_timeline`, then the stack, then PR 42 | `./demo.sh curated` | The log excerpt |

## The numbers

| Measure | Value | Source |
|---|---|---|
| Records processed | 1260 | `contract_reconciliation` |
| Reconciliation | 1259 clean + 1 quarantined = 1260 | `contract_reconciliation` |
| Page loads across 3 files | 16 | `sessions` |
| Clock agreement | 0 to 9 ms, mean 0.92 | `clock_skew` |
| Gaps that throttling explains | 20 of 25 | `gap_explained` |
| Gaps that throttling does not explain | 1, at 472.2s | `gap_explained` |
| Crash to alarm, time to detection | 1.323 s | `incident_timeline` |
| Frame time samples | 3978 | `frame_time_by_span` |
| Telemetry lost | 0 of 2079 events | `loss_accounting` |
| Ring headroom used | 32 of 400, so 8% | `loss_accounting` |
| Dimension coverage | state 10/15, mode 1/3, char 4/5 | `dimension_coverage` |
| Full run, cold | 3 to 5 seconds | `./demo.sh` |
| crow-archer tests | 1968 in 75 files | `npm test` |
| PostgreSQL relations loaded | 12, holding 84 rows | `./demo.sh load` |
| Full run with a warm container | 5 seconds | `./demo.sh` |
| Cold container start, extra | about 9 seconds | Pre-warm before the call |

## Known gaps

These gaps are on the record. The demo never needs to bluff.

### Gap 1: one bug shown live, not two

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

**Position:** show one bug end to end. Cite the second.

### Gap 2: loss accounting reports zero

The ring never overflowed. Peak use was 32 events against a cap of 400.

The mechanism is real and the number is checkable, but this data does not show
the pipeline catching a loss.

**Position:** the claim is "proven zero", not "caught loss".

### Gap 3: the quarantine holds one row

That row is real. It is an orphan `bye` whose `hello` sits in another file.
Nobody built a synthetic fixture for it.

The test suite proves the quarantine catches more than that one case:

| Violation | Test |
|---|---|
| An orphan record with no hello | `test_an_orphan_goodbye_is_quarantined_not_dropped` |
| A state outside the contract | `test_a_state_outside_the_contract_is_quarantined` |
| A beat over the event cap | `test_a_beat_over_the_event_cap_is_quarantined` |

**Position:** one row on this data. Three violation classes proven by test.

### Gap 4: one source, not many

The CV claims multi source ingestion.

| Source | Present here? |
|---|---|
| Game telemetry | yes |
| Reference dimensions | yes |
| Anything else | no |

duckEL carries the PostgreSQL, Snowflake, S3, and Parquet adapters. The day job
holds the genuinely multi source work. Nobody can show that work.

**Position:** two sources here. Name the limit first.

### Gap 5: the percentiles parse text

| Source | Rows | Shape |
|---|---|---|
| `alarm.trace.spans` | 24 | typed |
| Trace summary in a beat | 3978 | text |

Four samples cannot support a p95. The pipeline parses the text instead. A parse
differs from a measurement, so every percentile view prints its sample count.

**Position:** state the source. Print the count.

### Gap 6: Snowflake does not run

The curated Parquet is what a `COPY INTO` would read. The demo uses no account.
It makes no external call.

**Position:** a documented path, never a live step.

### Gap 7: one game mode

| Dimension | Played | Documented |
|---|---|---|
| mode | `brawl` only | `brawl`, `waves`, `siege` |
| map | `forest`, `castle`, `maze` | more exist |

A third of the mode dimension has no test coverage. The `dimension_coverage`
view states this fact rather than hiding it.

**Position:** the coverage view answers this question directly.
