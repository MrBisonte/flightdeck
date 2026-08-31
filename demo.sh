#!/usr/bin/env bash
# The whole pipeline, end to end, on the committed fixtures.
#
#   ./demo.sh              every step, timed
#   ./demo.sh build        raw, typed, curated, publish. No load, no exporter
#   ./demo.sh <step>       one step: check raw typed curated publish load posthog
#   ./demo.sh --live DIR   read DIR instead of the fixtures, newest file wins
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
  newest=$(ls -1t "$live_dir"/*.jsonl 2>/dev/null | head -1 || true)
  [ -n "$newest" ] || { echo "FAIL: no *.jsonl under $live_dir" >&2; exit 1; }
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

run_posthog () {
  banner "PostHog, the second consumer of the same files. Dry run"
  python pipeline/40_posthog_export.py
  done_in
}

total_start=$SECONDS
case "$what" in
  check)   run_check ;;
  raw)     run_raw ;;
  typed)   run_typed ;;
  curated) run_curated ;;
  publish) run_publish ;;
  load)    run_load ;;
  posthog) run_posthog ;;
  build)   run_raw; run_typed; run_curated; run_publish ;;
  all)     run_check; run_raw; run_typed; run_curated; run_publish; run_load; run_posthog ;;
  *)       echo "unknown step: $what" >&2; sed -n '2,9p' "$0" >&2; exit 2 ;;
esac

printf '\n%stotal %ss%s\n' "$bold" "$((SECONDS - total_start))" "$off"
