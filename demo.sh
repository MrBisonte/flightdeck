#!/usr/bin/env bash
# The whole pipeline, end to end, on the committed fixtures.
#
#   ./demo.sh              every step, timed
#   ./demo.sh build        raw, typed, curated, gold, publish. No load, no exporter
#   ./demo.sh <step>       one step: check raw typed curated gold publish load export
#   ./demo.sh --live DIR   read DIR instead of the fixtures, latest filename wins
#
# Live play falls back to fixtures by simply omitting --live. That is the whole
# kill switch: there is no live-only state to unwind.
set -euo pipefail

cd "$(dirname "$0")"

DB=warehouse/flightdeck.duckdb
SOURCE_GLOB='fixtures/raw/*.jsonl'
SOURCE_LABEL='committed fixtures'

# Only emit terminal codes to a real terminal. Piped or recorded output would
# otherwise carry raw escape sequences into the transcript.
if [ -t 1 ]; then
  bold=$(tput bold 2>/dev/null || true)
  dim=$(tput dim 2>/dev/null || true)
  off=$(tput sgr0 2>/dev/null || true)
else
  bold=''; dim=''; off=''
fi

step_start=0
banner () {
  step_start=$SECONDS
  printf '\n%s== %s ==%s\n' "$bold" "$1" "$off"
}
done_in () {
  printf '%s   (%ss)%s\n' "$dim" "$((SECONDS - step_start))" "$off"
}

require () {
  command -v "$1" >/dev/null 2>&1 || {
    echo "FAIL: $1 is not on PATH." >&2
    echo "Hint: $2" >&2
    exit 1
  }
}

# ---------------------------------------------------------------- arguments
if [ "${1:-}" = "--live" ]; then
  live_dir="${2:?--live needs a directory}"
  # The sink names every file session-<ISO 8601>.jsonl, so the newest capture
  # is the last one in plain lexical order. Sorting on the modification time
  # instead put a copied or restored directory in the wrong order, and two
  # files written in the same instant tied and broke the tie arbitrarily.
  newest=$(ls -1 "$live_dir"/*.jsonl 2>/dev/null | tail -1 || true)
  [ -n "$newest" ] || { echo "FAIL: no *.jsonl under $live_dir" >&2; exit 1; }
  # DuckDB is a native Windows binary. It cannot read a Git Bash path such as
  # /c/Users/..., so convert to C:/Users/... where cygpath exists. On Linux and
  # macOS there is no cygpath and the path passes through unchanged.
  # Sanitize a live capture the same way a fixture is sanitized. Without this
  # the raw user agent reaches the curated layer and the exporter payload, and
  # a live demo puts the browser build on screen.
  mkdir -p warehouse/live
  python scripts/sanitize_flightlog.py "$live_dir" warehouse/live >/dev/null
  newest="warehouse/live/$(basename "$newest")"
  if command -v cygpath >/dev/null 2>&1; then
    newest=$(cygpath -m "$newest")
  fi
  SOURCE_GLOB="$newest"
  SOURCE_LABEL="live capture, $(basename "$newest")"
  shift 2
fi
what="${1:-all}"

require duckdb "https://duckdb.org/docs/installation/"
require python "install Python 3.9 or newer"

mkdir -p warehouse/curated

run_check () {
  banner "Contract, sanitization gate"
  python scripts/sanitize_flightlog.py --check fixtures/raw
  python scripts/check_ste.py README.md docs/*.md fixtures/SANITIZATION.md fixtures/reference/README.md
  python -m pytest tests/ -q
  done_in
}

run_raw () {
  banner "Raw, JSONL to Hive partitioned Parquet, keyed on the server clock"
  echo "  source: $SOURCE_LABEL"
  rm -rf warehouse/raw
  duckdb "$DB" -c "SET variable raw_glob = '$SOURCE_GLOB';" -f pipeline/00_raw.sql
  find warehouse/raw -name '*.parquet' | sed 's/^/  /'
  duckdb "$DB" -c "SELECT count(*) AS records_landed FROM read_parquet('warehouse/raw/**/*.parquet');"
  done_in
}

run_typed () {
  banner "Typed, the documented model, with the contract enforced"
  duckdb "$DB" -f pipeline/10_typed.sql
  duckdb "$DB" -c "SELECT * FROM contract_reconciliation;"
  duckdb "$DB" -c "SELECT relation, reason, count(*) AS n FROM quarantine GROUP BY ALL ORDER BY n DESC;"
  done_in
}

run_curated () {
  banner "Curated, the questions worth asking"
  duckdb "$DB" -f pipeline/20_curated.sql
  echo "  -- four clocks: does the page agree with the server --"
  duckdb "$DB" -c "SELECT * FROM clock_skew;"
  echo "  -- and where did it go quiet --"
  duckdb "$DB" -c "SELECT * FROM gap_explained;"
  echo "  -- frame time per section --"
  duckdb "$DB" -c "SELECT * FROM frame_time_by_span;"
  echo "  -- nothing lost, and proven, not assumed --"
  duckdb "$DB" -c "SELECT * FROM loss_accounting;"
  echo "  -- documented domain versus what was actually played --"
  duckdb "$DB" -c "SELECT dimension, documented, exercised, never_seen FROM dimension_coverage;"
  done_in
}

run_gold () {
  banner "Gold, the game domain at the run grain"
  duckdb "$DB" -f pipeline/22_gold.sql
  echo "  -- what happened in the game --"
  duckdb "$DB" -c "SELECT runs, characters_played, avg_run_sim_s, max_kills FROM game_summary;"
  echo "  -- and how the boss fights ended --"
  duckdb "$DB" -c "SELECT boss_key, encounters, progressed, died FROM boss_encounters_by_kind;"
  done_in
}

run_publish () {
  banner "Publish, curated relations as open Parquet"
  duckdb "$DB" -f pipeline/25_publish.sql
  ls -1 warehouse/curated/*.parquet | sed 's/^/  /'
  done_in
}

run_load () {
  banner "Load, curated Parquet into PostgreSQL"
  python pipeline/30_load_postgres.py
  done_in
}

run_export () {
  banner "Export, the same files in three wire formats. Dry run"
  python pipeline/40_export.py
  done_in
}

total_start=$SECONDS
case "$what" in
  check)   run_check ;;
  raw)     run_raw ;;
  typed)   run_typed ;;
  curated) run_curated ;;
  gold)    run_gold ;;
  publish) run_publish ;;
  load)    run_load ;;
  export)  run_export ;;
  build)   run_raw; run_typed; run_curated; run_gold; run_publish ;;
  all)     run_check; run_raw; run_typed; run_curated; run_gold; run_publish; run_load; run_export ;;
  *)       echo "unknown step: $what" >&2; sed -n '2,9p' "$0" >&2; exit 2 ;;
esac

printf '\n%stotal %ss%s\n' "$bold" "$((SECONDS - total_start))" "$off"
