# Evidence matrix

Every claim below maps to something that runs, a file that exists, or a commit
that can be opened.

Numbers were produced by `./demo.sh` on the committed fixtures and are
reproducible from a clean clone.

## The matrix

| Area | Claim | Repo | Artifact | Command |
|---|---|---|---|---|
| Lakehouse, open formats | Raw telemetry lands as Hive partitioned Parquet | flightdeck | `warehouse/raw/session_date=*/session_id=*/` | `./demo.sh raw` |
| Embedded analytics on open files | An embedded engine queries the curated Parquet in place | flightdeck | Every layer reads Parquet directly, no warehouse in the middle. `ls warehouse/curated` lists the files | `./demo.sh publish` |
| Governance, data contracts | A typed schema defines each record, and rows that break it go to quarantine | flightdeck | `contracts/flight_log.yml`, `contract_caps` table, `quarantine` | `./demo.sh typed` |
| Governance, documentation levels | Architecture pages that go from one system picture down to each table | crow-archer, flightdeck | `docs/playbooks/monitored-playtest.md`, `docs/architecture.md` | Open either |
| Data engineering, ELT | Config, not code, defines each pipeline | quacknettor | `configs/pipelines.yml`, config driven adapters | Open the config |
| Performance engineering | Frame time by span, each percentile with its sample count | flightdeck | `frame_time_by_span`, p50 and p95 over 3978 measurements | `./demo.sh curated` |
| Snowflake | The same Parquet loads into Snowflake. Documented, not run | quacknettor | Snowflake adapter, `COPY INTO` reads the same Parquet | Documented, not live |
| Typed layer for downstream consumers | A typed layer that downstream consumers read | flightdeck | `session_context`, one compact typed row per page load | `./demo.sh posthog` |
| Conformed dimensions, two sources | Shared reference dimensions, with their coverage reported | flightdeck | `fixtures/reference/` joined to telemetry | `./demo.sh curated` |
| Data minimization | The committed logs carry no real user agent and no real origin. A check enforces it | flightdeck | `scripts/sanitize_flightlog.py`, `fixtures/SANITIZATION.md` | `python scripts/sanitize_flightlog.py --check fixtures/raw` |
| CI and test gating | CI tests every change | all three | GitHub Actions, 26 tests, contract reconciliation gated in CI | Open the Actions tab |
| Evidence based decisions | Decisions follow recorded evidence, from the alarm to the fix | crow-archer, flightdeck | `incident_timeline`, then the stack, then [PR #42](https://github.com/MrBisonte/crow-archer/pull/42) and its regression test | `./demo.sh curated` |

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
| Time to detection, crash to alarm | 1.323 s | `incident_timeline` |

## Known gaps

Each gap states what this data does not show.

| Gap | Detail |
|---|---|
| **Only one bug is shown end to end, not two** | The recorder caught two on its first day. The crash is fully evidenced end to end: the `err` record, a `loop-dead` alarm 1.323 s later from a different code path, the stack at `pathfinding.ts:67:30`, and the fix plus regression test in [PR #42](https://github.com/MrBisonte/crow-archer/pull/42). The latched key bug is evidenced by its fix commit only. Its session is not in the fixture set, and the playbook says `heldKeys` is the field that would show it, which is empty in all four alarms here. So: one shown end to end, one cited |
| **Loss accounting reports zero** | The ring never overflowed, peak 32 against a cap of 400. The mechanism is real and the number is checkable, but this data does not demonstrate loss being caught. The claim is "proven zero", not "caught loss" |
| **The quarantine has one row** | It is a real one, an orphan `bye` whose `hello` is in another file. Not a synthetic fixture. One row is a small demonstration and it should be described that way |
| **Two sources, not many** | The pipeline reads telemetry plus a reference dimension set, which is two, and duckEL carries the Postgres, Snowflake, S3 and Parquet adapters |
| **Percentiles come from parsed text** | The structurally clean source has four rows. Parsing the once-a-second summary gives 3978. That is the right call, and it is a parse, not a measurement, so the sample count is always printed with it |
| **Snowflake is not run** | Documented path only. The curated Parquet is what a `COPY INTO` would read. No account is used, and the pipeline makes no external calls |
| **One game mode only** | Every recorded session is `brawl`. `waves` and `siege` are documented but never played, so a third of the mode dimension is untested. Three maps do appear, `forest`, `castle` and `maze`. The coverage view states both rather than hiding either |
