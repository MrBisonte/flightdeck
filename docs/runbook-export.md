# Export runbook

Human setup for sending curated telemetry to an observability backend.

> **Warning.** The posting path is not built. `pipeline/40_export.py` prints
> payloads and writes files. It opens no socket, and `tests/test_export.py`
> asserts that it imports nothing that could. Sections 1 to 4 describe what runs
> today. Section 5 describes what a person must do before anything is sent, and
> section 6 lists what is still missing.

---

## 1. What runs today

```bash
./demo.sh export
```

That prints every payload and exits. To write the payloads to disk instead:

```bash
python pipeline/40_export.py --format otlp --out /tmp/payloads
```

| Flag | Values | Default |
|---|---|---|
| `--format` | `otlp`, `cloudevents`, `posthog` | `otlp` |
| `--signal` | `logs`, `traces`, `metrics`, `all` | `all` |
| `--out` | a directory | none, print only |
| `--limit` | how many records to print per payload | 2 |

`--signal` applies to `otlp` only. The other two formats carry one payload each.

---

## 2. The formats

| Format | Spec | Media type | Path |
|---|---|---|---|
| `cloudevents` | CloudEvents 1.0, JSON batch | `application/cloudevents-batch+json` | whatever the backend documents |
| `otlp` | OTLP/HTTP, JSON encoding | `application/json` | `/v1/logs`, `/v1/traces`, `/v1/metrics` |
| `posthog` | vendor capture shape | `application/json` | `/batch/` |

OTLP defaults to port 4318 for HTTP. A backend usually publishes its own host
and path prefix, so treat the paths above as suffixes.

> **Note.** OTLP defines two other transports, HTTP with protobuf and gRPC.
> Neither is built here. Both need a dependency, and JSON reaches the same
> endpoints without one.

---

## 3. What each payload carries

| Payload | Source relations | Records |
|---|---|---|
| `otlp-logs` | `error_report`, `incident_timeline`, `quarantine` | 9 |
| `otlp-traces` | `spans` | 4666 |
| `otlp-metrics` | `loss_accounting`, `contract_reconciliation`, `alarms_by_class`, `frame_time_by_span` | 8 |
| `cloudevents` | `session_summary`, `error_report`, `alarms_by_class` | 21 |
| `posthog` | the same three | 21 |

Record counts come from the three committed fixture sessions. Run
`./demo.sh build` first, or the exporter exits 1 and says so.

---

## 4. Size limits

`otlp-traces.json` is 5.1 MB for the fixtures alone. Ingest endpoints commonly
cap a request at 5 MB, so this payload already exceeds a common limit on a
three session sample.

A person setting this up must batch traces before posting. The other four
payloads sit under 11 KB each and need no batching.

> **Warning.** Batch size is not implemented. Nothing in this repository splits
> a payload, so the first real trace post will fail on size unless somebody adds
> that first.

---

## 5. Human setup, before anything is posted

Do these in order. Steps 1 to 4 need a person, and no script here performs them.

1. **Get an endpoint and a token from the backend owner.** The token needs
   ingest permission and nothing else. Read scopes are not required.
2. **Confirm the retention and deletion policy in writing.** This payload
   carries a browser user agent string and a session identifier. Decide how long
   that lives before you send the first record.
3. **Put both values in the environment.** Never a file, never a command line
   argument, because argv lands in shell history.

   ```bash
   export FLIGHTDECK_EXPORT_ENDPOINT='https://<host>/<path>'
   export FLIGHTDECK_EXPORT_TOKEN='<token>'
   ```

4. **Confirm the values are set, without printing them.**

   ```bash
   test -n "$FLIGHTDECK_EXPORT_TOKEN" && echo "token is set"
   ```

5. **Write the payload and read it before sending it.**

   ```bash
   python pipeline/40_export.py --format cloudevents --out ./payloads
   ```

   Start with `cloudevents`. It is 21 records and 11 KB, so a person can read
   the whole thing.

6. **Post one payload by hand, once.** Use the backend's own documented example
   command. Confirm the records arrive and look right before automating it.

> **Warning.** No script in this repository reads either variable yet. They are
> named here so the name is settled before the code exists.

### On Windows

The environment steps differ. PowerShell sets a variable for the session with:

```powershell
$env:FLIGHTDECK_EXPORT_ENDPOINT = 'https://<host>/<path>'
```

Do not use `setx`. It writes the value to the registry, which is the disk this
runbook tells you to avoid.

---

## 6. What is not built

| Item | Blocks |
|---|---|
| The HTTP post itself | Everything in section 5 past step 5 |
| Batching by size | Any trace post, see section 4 |
| Backoff on 429 and 5xx | A retry that does not make things worse |
| A high water mark on `srv` | Re-runs double count without it |
| Round trip test, post then read back | Proving a few tuples survive both ways |
| The span id collision fix | 18 of 4002 rows share an id, `docs/hlad.md` section 6 item 1 |

The span id collision matters most. OTLP requires a unique span id per trace.
One beat can drain two trace summaries, and `spans` carries no column that tells
them apart. The exporter counts the collisions and prints a warning, so the
defect stays visible until somebody fixes the pipeline.

---

## 7. Related pages

| Page | Content |
|---|---|
| [hlad.md](hlad.md) | The relational model, units, keys, worked records |
| [architecture.md](architecture.md) | End to end, data flows, topology |
| [flight_log.yml](../contracts/flight_log.yml) | The contract itself |
