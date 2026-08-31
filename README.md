# flightdeck

A medallion pipeline over real browser game telemetry: JSONL flight logs to
Hive partitioned Parquet, to a typed relational model enforced by a data
contract, to curated analytics, to PostgreSQL.

The telemetry comes from the flight recorder in
[crow-archer](https://github.com/MrBisonte/crow-archer), a browser game. The
logs in `fixtures/` are real recorded play sessions, sanitized, not generated.

**Status: under construction.** The quickstart lands with the pipeline. Nothing
in this README claims a step that does not run.

## Layout

| Path | What |
|---|---|
| `contracts/` | The data contract: enums, caps, required fields |
| `fixtures/raw/` | Real recorded sessions, sanitized |
| `fixtures/reference/` | Reference dimensions extracted from the source docs |
| `pipeline/` | Raw, typed, curated, load |
| `scripts/` | Sanitizer and the contamination gate |
| `docs/` | Lineage and the evidence matrix |

## License

MIT, see [LICENSE](LICENSE).
