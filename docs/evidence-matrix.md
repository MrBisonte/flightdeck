# Evidence matrix

Every claim below maps to something that runs, a file that exists, or a commit
that can be opened. Claims are quoted from the CV as sent. Nothing is asserted
here that cannot be shown on screen in under a minute.

Numbers were produced by `./demo.sh` on the committed fixtures and are
reproducible from a clean clone.

## The matrix

| Role competency | CV claim | Repo | Artifact | Live command | Fallback |
|---|---|---|---|---|---|
| Lakehouse, open formats | "open lakehouse formats, Apache Parquet, Apache Iceberg, Apache Arrow, Hive partitioned object storage" | flightdeck | `warehouse/raw/session_date=*/session_id=*/` | `./demo.sh raw` | Partition tree screenshot |
| De-vendoring the analytics path | "Re-engineered proprietary warehouse aggregations into an open lakehouse format, Hive partitioned Parquet on object storage queryable from an embedded engine" | flightdeck | Every layer reads Parquet directly, no warehouse in the middle | `./demo.sh publish` | `ls warehouse/curated` |
| Governance, data contracts | "typed data contracts, governance as code, data quality and lineage" | flightdeck | `contracts/flight_log.yml`, `contract_caps` table, `quarantine` | `./demo.sh typed` | Reconciliation table |
| Governance, documentation levels | "architecture documentation at conceptual, logical and physical levels" | crow-archer, flightdeck | `docs/playbooks/monitored-playtest.md`, `docs/architecture.md` | Open either | Printed |
| Data engineering, ELT | "metadata driven ETL and ELT engines, data pipelines" | quacknettor | `configs/pipelines.yml`, config driven adapters | Open the config | README |
| Performance engineering | "performance engineering at query, parameter and OS level" | flightdeck | `frame_time_by_span`, p50 and p95 over 3978 measurements | `./demo.sh curated` | Cast recording |
| Snowflake | "Snowflake (SnowPro Core certified)" | quacknettor | Snowflake adapter, `COPY INTO` reads the same Parquet | Documented, not live | Documented path |
| Typed layer for downstream consumers | "typed data layers for downstream AI consumption" | flightdeck | `session_context`, one compact typed row per page load | `./demo.sh posthog` | Printed payload |
| Conformed dimensions, two sources | "data quality", "metadata driven ETL" | flightdeck | `fixtures/reference/` joined to telemetry | `./demo.sh curated` | Coverage table |
| Data minimization | "GDPR compliant design in regulated European industries" | flightdeck | `scripts/sanitize_flightlog.py`, `fixtures/SANITIZATION.md` | `python scripts/sanitize_flightlog.py --check fixtures/raw` | The sanitization table |
| CI and test gating | "CI/CD with automated test gating on every change" | all three | GitHub Actions, 26 tests, contract reconciliation gated in CI | Open the Actions tab | Badge |
| Evidence based decisions | "shipping working proofs of concept before asking for investment" | crow-archer | The `err` record, its stack, the fix commit, the regression test | Beat 1 | Log excerpt |

## The numbers, all reproducible

| Claim | Number | Where it comes from |
|---|---|---|
| Records processed | 1260 | `contract_reconciliation` |
| Contract reconciles | 1259 clean + 1 quarantined = 1260 | `contract_reconciliation` |
| Page loads, not files | 16 across 3 files | `sessions` |
| Clock agreement | `srv - wall` in [0, 9] ms, mean 0.92 | `clock_skew` |
| Gaps explained by tab throttling | 20 of 25, all at ~60s while hidden | `gap_explained` |
| Gaps not explained | 1, at 472.2s, visible throughout | `gap_explained` |
| Frame time samples | 3978, from 663 parsed summaries | `frame_time_by_span` |
| Telemetry lost | 0 of 2079 events | `loss_accounting` |
| Ring headroom used | 32 of a 400 cap, 8 percent | `loss_accounting` |
| Dimension coverage | state 10/15, mode 1/3, char 4/5, boss 4/4 | `dimension_coverage` |
| Full run, cold | about 3 seconds | `./demo.sh` |
| Quickstart from clean clone | verified, well under 5 minutes | Clone and run |

## Honest gaps, stated before anyone asks

These are on the record so the demo never has to bluff.

| Gap | The honest position |
|---|---|
| **Only one bug is shown live, not two** | The recorder caught two on its first day. The crash is fully evidenced: log record, stack at `pathfinding.ts:67:30`, fix commit `28da21a`, regression test `d127a7e`. The latched key bug is evidenced by fix commit `7a02a55` only. Its session is not in the fixture set, and the playbook says `heldKeys` is the field that would show it, which is empty in all four alarms here. So: one shown end to end, one cited |
| **Loss accounting reports zero** | The ring never overflowed, peak 32 against a cap of 400. The mechanism is real and the number is checkable, but this data does not demonstrate loss being caught. The claim is "proven zero", not "caught loss" |
| **The quarantine has one row** | It is a real one, an orphan `bye` whose `hello` is in another file. Not a synthetic fixture. One row is a small demonstration and it should be described that way |
| **One source, not many** | The CV claims multi source ingestion. This demo has telemetry plus a reference dimension set, which is two, and duckEL carries the Postgres, Snowflake, S3 and Parquet adapters. The genuinely multi source work is at the day job and cannot be shown |
| **Percentiles come from parsed text** | The structurally clean source has four rows. Parsing the once-a-second summary gives 3978. That is the right call, and it is a parse, not a measurement, so the sample count is always printed with it |
| **Snowflake is not run** | Documented path only. The curated Parquet is what a `COPY INTO` would read. No account is used, and the demo makes no external calls |
| **One game mode only** | Every recorded session is `brawl`. `waves` and `siege` are documented but never played, so a third of the mode dimension is untested. Three maps do appear, `forest`, `castle` and `maze`. The coverage view states both rather than hiding either |
