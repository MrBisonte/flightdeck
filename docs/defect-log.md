# Defect log

This page records every defect found while building this repository. It records
what broke, why, and what fixed it.

The log exists because a pipeline that claims to find problems in other people's
data has to account for the problems in its own build. This log lists twelve
defects. All twelve are closed.

## Summary

| Severity | Count | Meaning |
|---|---|---|
| High | 7 | Would reach a user, break the demo, or disclose information |
| Medium | 5 | Caught inside the build, or degrades quality without breaking it |

| Category | Count |
|---|---|
| Data contract and schema | 3 |
| Tooling and gates | 5 |
| Build and packaging | 2 |
| Process | 2 |

## Which control caught what

This is the useful part of the table. It shows which control earned its place.

| Found by | Count | Defects |
|---|---|---|
| Running a gate | 2 | DEF-01, DEF-03 |
| Unit or integration test | 3 | DEF-02, DEF-04, DEF-11 |
| Live rehearsal | 2 | DEF-08, DEF-09 |
| CI | 2 | DEF-05, DEF-06 |
| Manual check | 2 | DEF-07, DEF-12 |
| Peer review | 1 | DEF-10 |

```
   tests + gates   ->  5 defects   found before anything ran end to end
   CI              ->  2 defects   found on a clean machine, not this one
   rehearsal       ->  2 defects   found only by running the real path
   review          ->  1 defect    found only by a second reader
```

Two defects, DEF-08 and DEF-09, were reachable only by running a live capture.
No test found them. That is the argument for rehearsing rather than assuming.

## The register

### DEF-01. The contamination gate matched its own wordlist

| Field | Detail |
|---|---|
| **Severity** | High |
| **Category** | Tooling and gates |
| **Symptom** | The gate reported its own source file as contaminated |
| **Root cause** | The gate held the suppressed names as a literal list inside a tracked file. Publishing the gate would publish the names it exists to hide |
| **Resolution** | The full gate moved to an untracked local directory. The published scan checks credential shapes only, and names nothing |
| **Found by** | Running the gate |
| **Fixed in** | `8b1c020` |

### DEF-02. The sanitizer was not idempotent

| Field | Detail |
|---|---|
| **Severity** | Medium |
| **Category** | Tooling and gates |
| **Symptom** | A second sanitizer run changed `Chrome` to `Other` |
| **Root cause** | The browser family lookup matched on a version token such as `Chrome/`. An already trimmed value carries no token, so it fell through to the default |
| **Resolution** | The lookup returns an already trimmed value unchanged. A byte comparison on the committed fixtures proves the second run changes nothing |
| **Found by** | Unit test |
| **Fixed in** | `bc14ccf` |

### DEF-03. Every contract cap check passed without testing anything

| Field | Detail |
|---|---|
| **Severity** | High |
| **Category** | Data contract and schema |
| **Symptom** | The curated layer reported the event cap as `NULL` |
| **Root cause** | The caps were session variables. A session variable does not survive a new connection, so a later layer read `NULL`. Every comparison against `NULL` passed silently |
| **Resolution** | The caps are a table in the warehouse. A test forbids the session variable form returning |
| **Found by** | Running the layer and reading the output |
| **Fixed in** | `e50d12f` |

**Note.** This defect is the reason the log is worth keeping. A control that
always passes looks identical to a control that works.

### DEF-04. A session with no alarm and no error crashed the typed layer

| Field | Detail |
|---|---|
| **Severity** | High |
| **Category** | Data contract and schema |
| **Symptom** | The typed layer failed to bind against a clean session |
| **Root cause** | A log with no alarm and no error contains no `class`, `blockers`, `trace`, `msg` or `stack` column at all. The typed layer referenced columns that the source never created |
| **Resolution** | `contracts/wire_schema.jsonl` holds one populated record of each kind. The raw layer reads zero rows from it and unions by name, so every documented column exists whatever the source contained |
| **Found by** | Integration test |
| **Fixed in** | `2d20a25` |

**Note.** A clean session is the most likely result of a live capture. This
defect would have stopped a live demonstration.

### DEF-05. The demo script was not executable

| Field | Detail |
|---|---|
| **Severity** | High |
| **Category** | Build and packaging |
| **Symptom** | CI stopped with exit code 126 |
| **Root cause** | Windows does not track the execute bit. Every file with a shebang entered the repository as mode 644 |
| **Resolution** | The execute bit is set in the index for the six affected files |
| **Found by** | CI |
| **Fixed in** | `b203b15` |

**Note.** The CI failure was the smaller problem. The quickstart in the README
starts with `./demo.sh`, so it would have failed for every reader on Linux or
macOS.

### DEF-06. The CI install step could not fetch the query engine

| Field | Detail |
|---|---|
| **Severity** | Medium |
| **Category** | Build and packaging |
| **Symptom** | The install step returned HTTP 404 and the build stopped |
| **Root cause** | The step piped an install script into `sh`. The script requires `bash`, and it resolved a 404 for the latest release tag |
| **Resolution** | CI downloads a pinned release asset. The engine version is now explicit in the workflow |
| **Found by** | CI |
| **Fixed in** | `67ad544` |

### DEF-07. The documentation checker missed long sentences

| Field | Detail |
|---|---|
| **Severity** | Medium |
| **Category** | Tooling and gates |
| **Symptom** | Documents passed the checker while breaking its rules |
| **Root cause** | The checker read one line at a time. Markdown wraps a sentence over several lines, so one long sentence counted as two short ones |
| **Resolution** | The checker joins a paragraph before it measures anything. The corrected version found two real violations on its first run |
| **Found by** | Manual check of a passing result |
| **Fixed in** | `bef2d53` |

### DEF-08. The live capture path was unreadable by the query engine

| Field | Detail |
|---|---|
| **Severity** | High |
| **Category** | Tooling and gates |
| **Symptom** | A live run failed at the first step with a file not found error |
| **Root cause** | The runner passed a shell style path. The query engine is a native Windows binary and cannot resolve it |
| **Resolution** | The runner converts the path where a converter exists, and passes it through unchanged elsewhere |
| **Found by** | Live rehearsal |
| **Fixed in** | `9ecced1` |

### DEF-09. The page load id landed as a UUID column, not a text column

| Field | Detail |
|---|---|
| **Severity** | High |
| **Category** | Data contract and schema |
| **Symptom** | The typed layer could not combine the recorded id with a derived one |
| **Root cause** | The recorder mints the id with a UUID generator where the browser context allows it. The JSON reader infers UUID for such a value. The recorder falls back to a plain string elsewhere, so the same column could arrive with two different types |
| **Resolution** | The raw layer casts the id to text. Two tests cover it: one with a real UUID, one mixing both id shapes in a single load |
| **Found by** | Live rehearsal |
| **Fixed in** | `9ecced1` |

**Note.** The failure was visible. The damage was not. Two captures taken in
different browser contexts write two different types for one column. A read
across those partitions then fails later, far from the cause.

### DEF-10. A four line problem was fixed by deleting a hundred and thirty eight lines

| Field | Detail |
|---|---|
| **Severity** | High |
| **Category** | Process |
| **Symptom** | A coordination file was removed from version control to remove four lines of local paths |
| **Root cause** | The fix addressed the file rather than the four lines. Version control was that file's distribution mechanism, so removing it also stopped it reaching a second clone and any new working copy |
| **Resolution** | The removal is reverted. The four lines are generic, and the file stays in the tree. Every operational note it carries is unchanged |
| **Found by** | Peer review |
| **Fixed in** | `02547c0`, in the game repository |

**Note.** No test could have caught this. The change was valid, passed every
gate, and would have deleted a working file from another copy of the repository
on merge. A second reader caught it.

### DEF-11. Test data was unrealistic, so a defect passed through

| Field | Detail |
|---|---|
| **Severity** | Medium |
| **Category** | Process |
| **Symptom** | The schema tests passed while DEF-09 was present |
| **Root cause** | The tests used a short placeholder id. A placeholder does not look like a UUID, so the reader inferred text and the tests never exercised the real type |
| **Resolution** | The tests now use a real UUID, and a second test mixes both id shapes |
| **Found by** | The live rehearsal that found DEF-09 |
| **Fixed in** | `9ecced1` |

**Note.** The test suite was green and wrong. Sample data that does not resemble
production data tests the harness, not the system.

### DEF-12. A live capture reached the output unsanitized

| Field | Detail |
|---|---|
| **Severity** | Medium |
| **Category** | Tooling and gates |
| **Symptom** | The exporter payload carried a full user agent string, including the browser build |
| **Root cause** | The sanitizer ran only when preparing fixtures. The live capture path read the log directly, so a live run bypassed it |
| **Resolution** | The live path sanitizes into a working directory first. Live and fixture inputs now take the same route |
| **Found by** | Manual check of a live run |
| **Fixed in** | this commit |

**Note.** The fixture path was clean and stayed clean, which is why no test
caught this. The defect lived only on the path that skipped the step.

## What the log says

Three patterns come out of twelve entries.

1. **Controls that always pass are invisible.** DEF-03 and DEF-11 both produced
   a green result over a broken check. Both needed something outside the check
   to notice.
2. **Some defects need the real path.** DEF-08 and DEF-09 survived a full test
   suite and appeared within minutes of a live capture.
3. **Some defects need a second reader.** DEF-10 passed every automated gate.
   Review caught it.

The pipeline this repository builds applies the same three ideas to telemetry.
It reconciles its counts in public, it quarantines with a reason rather than
dropping, and it reports the sample size beside every percentile.
