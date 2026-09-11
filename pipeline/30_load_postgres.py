#!/usr/bin/env python3
"""Load the curated Parquet into PostgreSQL.

The source is always the Parquet files, never the DuckDB database, so the load
reads exactly what a Snowflake COPY INTO or any other consumer would read.

If the Docker daemon is not running, the load degrades to a local target with an
identical schema instead of failing. A live demo should not die because a daemon
was not started, and the fallback is announced loudly rather than hidden, so
nobody watching mistakes it for the real thing.
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys
import time

import duckdb

ROOT = pathlib.Path(__file__).resolve().parents[1]
CURATED = ROOT / "warehouse" / "curated"
FALLBACK_DB = ROOT / "warehouse" / "postgres_fallback.duckdb"

DSN = "host=localhost port=55432 dbname=flightdeck user=flightdeck password=flightdeck"
SCHEMA = "curated"
#: Pinned in docker-compose.yml, so it is the one name both files agree on.
CONTAINER = "flightdeck-pg"

#: Relation name -> Parquet file. Quarantine ships alongside the clean data so a
#: consumer can always see how much was held back.
RELATIONS = [
    "session_summary", "session_context", "frame_time_by_span", "alarms_by_class",
    "clock_skew", "srv_gaps", "gap_explained", "loss_accounting",
    "dimension_coverage", "error_report", "incident_timeline", "quarantine",
]


class LoadError(RuntimeError):
    """A load failure with an actionable hint."""


def docker_is_running() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        done = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True, text=True, timeout=15,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return done.returncode == 0 and bool(done.stdout.strip())


def container_health() -> str:
    """Docker's health state for the container, or "" when it does not exist."""
    done = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Health.Status}}", CONTAINER],
        capture_output=True, text=True,
    )
    return done.stdout.strip() if done.returncode == 0 else ""


def start_postgres() -> None:
    """Bring the container up, or adopt one that another checkout started.

    The container name and the port are both pinned, so two checkouts cannot
    each run their own PostgreSQL. A second checkout's `compose up` does not
    reuse the running container, it fails on the name, so a healthy one is
    adopted here instead.

    The failure used to raise CalledProcessError with the compose output
    captured and discarded, which told an operator that something failed and
    nothing about what.
    """
    if container_health() == "healthy":
        print(f"  {CONTAINER} is already healthy. Reusing it.")
        return

    done = subprocess.run(["docker", "compose", "up", "-d", "postgres"],
                          cwd=ROOT, capture_output=True, text=True)
    if done.returncode != 0:
        detail = (done.stderr or done.stdout).strip().splitlines()[-3:]
        raise LoadError("\n".join([
            "docker compose could not start postgres.",
            *(f"    {line.strip()}" for line in detail),
            f"Hint: docker rm -f {CONTAINER}, then rerun.",
        ]))

    for _ in range(30):
        if container_health() == "healthy":
            return
        time.sleep(2)
    raise LoadError(
        "postgres did not become healthy within 60s. "
        "Hint: docker compose logs postgres"
    )


def missing_parquet() -> list[str]:
    return [r for r in RELATIONS if not (CURATED / f"{r}.parquet").exists()]


def load(con: duckdb.DuckDBPyConnection, target: str, label: str) -> list[tuple[str, int]]:
    """Copy every curated relation into target. Returns (relation, rows)."""
    loaded = []
    for name in RELATIONS:
        source = (CURATED / f"{name}.parquet").as_posix()
        con.execute(f"DROP TABLE IF EXISTS {target}.{name}")
        con.execute(f"CREATE TABLE {target}.{name} AS SELECT * FROM read_parquet('{source}')")
        rows = con.execute(f"SELECT count(*) FROM {target}.{name}").fetchone()[0]
        loaded.append((name, rows))
        print(f"  {name:<22} {rows:>6} rows -> {label}")
    return loaded


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fallback", action="store_true",
                        help="skip Docker entirely and load the local target")
    args = parser.parse_args()

    absent = missing_parquet()
    if absent:
        print("FAIL: curated Parquet is missing: " + ", ".join(absent), file=sys.stderr)
        print("Hint: run the raw, typed, curated and publish steps first "
              "(./demo.sh build).", file=sys.stderr)
        return 1

    con = duckdb.connect()

    if args.fallback or not docker_is_running():
        why = "requested with --fallback" if args.fallback else "Docker daemon is not running"
        print()
        print(f"  FALLBACK TARGET, {why}.")
        print("  This is NOT PostgreSQL. Same schema, same Parquet source, local engine.")
        print("  To run the real load: start Docker Desktop, then rerun.")
        print()
        FALLBACK_DB.unlink(missing_ok=True)
        con.execute(f"ATTACH '{FALLBACK_DB.as_posix()}' AS pg_fallback")
        con.execute(f"CREATE SCHEMA IF NOT EXISTS pg_fallback.{SCHEMA}")
        load(con, f"pg_fallback.{SCHEMA}", "local fallback")
        print("\n  Loaded to the fallback target.")
        return 0

    print("  Docker is running. Starting PostgreSQL on port 55432.")
    start_postgres()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{DSN}' AS pg (TYPE POSTGRES)")
    con.execute(f"CREATE SCHEMA IF NOT EXISTS pg.{SCHEMA}")
    loaded = load(con, f"pg.{SCHEMA}", "postgres")
    print(f"\n  Loaded {len(loaded)} relations, {sum(n for _, n in loaded)} rows into PostgreSQL.")
    print(f"  psql \"{DSN}\" -c '\\dt {SCHEMA}.*'")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LoadError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
