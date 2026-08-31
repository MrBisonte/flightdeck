# What was changed in these fixtures, and what was not

The three files in `raw/` are real recorded play sessions from the crow-archer
flight recorder, captured on 2026-08-30. They are not generated and not edited
by hand. Exactly two fields were rewritten, by
[`scripts/sanitize_flightlog.py`](../scripts/sanitize_flightlog.py), which is
deterministic and re-runnable.

## The two changes

| Field | Before | After | Why |
|---|---|---|---|
| `ua` | Full user agent, naming the browser build | `Chrome` or `Edge` | The build string identifies the exact client. Browser family is all the analysis needs |
| `href` | `http://localhost:8090/` | `http://localhost/` | Normalizes the dev server origin |
| URLs inside `stack` | `http://localhost:8090/src/...` | `http://localhost/src/...` | Same rule applied consistently |

Nothing else was touched. Timestamps, telemetry, event bodies, stack frames,
file names, line numbers and column numbers are byte for byte as recorded.

**File paths, line numbers and column numbers in stack traces are preserved on
purpose.** They are the evidence. `pathfinding.ts:67:30` still reads
`pathfinding.ts:67:30`.

## What was checked and found absent

The sanitizer fails if any of these survive into the output, and it was run as a
gate, not an afterthought:

| Shape | Found |
|---|---|
| Windows drive paths, `C:\...` | none |
| Unix home paths, `/Users/`, `/home/` | none |
| Cloud sync folder names, always under one of the above | none |
| In-app browser build tokens | removed with the user agent |
| Un-trimmed user agents | none remaining |

Verify it yourself against the committed fixtures:

```bash
python scripts/sanitize_flightlog.py --check fixtures/raw
```

## Record counts, before and after

Sanitizing changes field values, never record counts.

| File | Records | Contains |
|---|---|---|
| `session-2026-08-30T14-58-28-391Z.jsonl` | 282 | 1 alarm, 1 err (a recorder self-test) |
| `session-2026-08-30T15-04-51-872Z.jsonl` | 640 | 3 alarms, 1 err (a real crash) |
| `session-2026-08-30T15-39-43-490Z.jsonl` | 338 | clean session, no alarm, no err |
| **Total** | **1260** | |

## An honest note on the two err records

Only one of the two `err` records is a real defect. The other, in the first
session, is `flight-recorder self-test`, deliberately thrown to prove the error
hook worked. It is left in because removing it would misrepresent what the
session contained.
