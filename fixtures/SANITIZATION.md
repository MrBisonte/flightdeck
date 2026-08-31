# What changed in these fixtures

The three files in `raw/` hold real recorded play from 2026-08-30. Nobody
generated them. Nobody edited them by hand.

The sanitizer rewrites two fields and nothing else. See
[`scripts/sanitize_flightlog.py`](../scripts/sanitize_flightlog.py). It runs the
same way every time.

```
   original log  -->  sanitizer  -->  committed fixture
                        |
                        +-- rewrites: ua, href, URLs in stack
                        +-- keeps:    every other field, byte for byte
```

## The changes

| Field | Before | After | Reason |
|---|---|---|---|
| `ua` | The full user agent, with the build | `Chrome` or `Edge` | The build string identifies the exact client |
| `href` | `http://localhost:8090/` | `http://localhost/` | Removes the dev server port |
| URLs in `stack` | `http://localhost:8090/src/...` | `http://localhost/src/...` | The same rule, applied consistently |

## What the sanitizer keeps

The sanitizer keeps timestamps, telemetry, event bodies, and stack frames.

It also keeps file names, line numbers, and column numbers. **Those are the
evidence.** `pathfinding.ts:67:30` still reads `pathfinding.ts:67:30`.

## What the sanitizer checks

The script fails when any of these shapes survive into the output. It runs as a
gate, not as an afterthought.

| Shape | Result |
|---|---|
| Windows drive path, `C:\...` | none found |
| Unix home path, `/Users/`, `/home/` | none found |
| A cloud folder name, always under one of the above | none found |
| A browser build token | removed with the user agent |
| An untrimmed user agent | none remain |

Check the committed fixtures yourself:

```bash
python scripts/sanitize_flightlog.py --check fixtures/raw
```

## Record counts

The sanitizer changes field values. It never changes record counts.

| File | Records | Contents |
|---|---|---|
| `session-2026-08-30T14-58-28-391Z.jsonl` | 282 | 1 alarm, 1 err (a self-test) |
| `session-2026-08-30T15-04-51-872Z.jsonl` | 640 | 3 alarms, 1 err (a real crash) |
| `session-2026-08-30T15-39-43-490Z.jsonl` | 338 | clean, no alarm, no err |
| **Total** | **1260** | |

## A note on the two error records

Only one error record shows a real defect.

| Record | Message | Type |
|---|---|---|
| Session B | `Uncaught TypeError ... reading 'length'` | A real crash |
| Session A | `Uncaught Error: flight-recorder self-test` | A deliberate test |

The self-test proves the error hook works. It stays in the fixture. Removal
would misrepresent the session.
