"""Write one CSV of evidence for every relation the pipeline builds.

`./demo.sh all` prints its evidence and then the terminal scrolls. This script
reads the same run afterwards and records it, one row per relation, so a QA
reviewer can check the whole warehouse without re-running anything.

Three sinks answer for each relation, and the CSV keeps all three side by side:

  - the DuckDB warehouse, which every layer is built in
  - `warehouse/curated/*.parquet`, which the site reads
  - the PostgreSQL schema the load step writes, when its container answers

A relation whose three counts disagree is the failure this file exists to catch.
Publishing reads the database and PostgreSQL reads the Parquet, so a silent loss
at either hop shows up as a mismatch rather than as a plausible smaller number.

The sample row is real data, ordered by the first column so that two runs over
the same warehouse produce the same CSV.

    python scripts/qa_evidence.py [--out docs/qa/e2e-evidence.csv] [--no-postgres]

A `--live` run reads one capture instead of the committed fixtures, so pass
`--raw-glob` to match. Without it, `raw_landed` reports the fixtures while every
other relation reports the capture, and the two disagree for no reason.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import pathlib
import re
import sys

import duckdb

ROOT = pathlib.Path(__file__).resolve().parents[1]
DB = ROOT / "warehouse" / "flightdeck.duckdb"
CURATED = ROOT / "warehouse" / "curated"

#: The layer a relation belongs to is the file that creates it, not a list kept
#: here. A new relation therefore lands in the CSV with no edit to this script.
LAYERS = {
    "00_raw.sql": "1 raw",
    "10_typed.sql": "2 typed",
    "20_curated.sql": "3 curated",
    "22_gold.sql": "4 gold",
}

CREATE = re.compile(
    r"^CREATE\s+(?:OR\s+REPLACE\s+)?(?:TABLE|VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-z_0-9]+)",
    re.IGNORECASE | re.MULTILINE,
)

SAMPLE_CHARS = 300


def origins() -> dict[str, tuple[str, str]]:
    """Map every relation to the layer and file that creates it."""
    found: dict[str, tuple[str, str]] = {}
    for name, layer in LAYERS.items():
        text = (ROOT / "pipeline" / name).read_text(encoding="utf-8")
        for match in CREATE.finditer(text):
            found.setdefault(match.group(1).lower(), (layer, name))
    return found


def postgres_counts() -> dict[str, int]:
    """Row counts from the loaded PostgreSQL schema, or nothing if it is down.

    The DSN comes from the loader rather than from a second copy here, so the
    two can never drift apart.
    """
    path = ROOT / "pipeline" / "30_load_postgres.py"
    spec = importlib.util.spec_from_file_location("flightdeck_loader", path)
    loader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loader)

    con = duckdb.connect()
    try:
        con.execute(f"ATTACH '{loader.DSN}' AS pg (TYPE POSTGRES, READ_ONLY)")
        names = [r[0] for r in con.execute(
            "SELECT table_name FROM pg.information_schema.tables "
            "WHERE table_schema = ?", [loader.SCHEMA]).fetchall()]
        return {n: con.execute(
            f'SELECT count(*) FROM pg.{loader.SCHEMA}."{n}"').fetchone()[0]
            for n in names}
    except Exception as exc:                     # the container is not running
        print(f"  postgres not attached: {exc}", file=sys.stderr)
        return {}
    finally:
        con.close()


def source_glob() -> str:
    """demo.sh's default raw glob, read from demo.sh rather than repeated here.

    `raw_landed` and `raw` wrap `read_json` over a DuckDB variable that demo.sh
    sets. A fresh connection has no such variable, so both views refuse to run
    until this script sets it to the same value.
    """
    text = (ROOT / "demo.sh").read_text(encoding="utf-8")
    match = re.search(r"^SOURCE_GLOB='([^']+)'", text, re.MULTILINE)
    if match is None:
        raise SystemExit("demo.sh no longer declares SOURCE_GLOB")
    return match.group(1)


def count(con, relation: str):
    """Row count, or the reason the relation would not answer."""
    try:
        return con.execute(f'SELECT count(*) FROM "{relation}"').fetchone()[0]
    except duckdb.Error as exc:
        return str(exc).splitlines()[0]


def sample(con, relation: str) -> str:
    """One real row, ordered so the CSV is reproducible."""
    for order in ("ORDER BY 1", ""):
        try:
            row = con.execute(f'SELECT * FROM "{relation}" {order} LIMIT 1').fetchone()
            break
        except duckdb.Error:
            continue
    else:
        return "unreadable"
    if row is None:
        return ""
    text = ", ".join("" if v is None else str(v) for v in row)
    return text if len(text) <= SAMPLE_CHARS else text[:SAMPLE_CHARS] + " ..."


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="docs/qa/e2e-evidence.csv")
    ap.add_argument("--no-postgres", action="store_true")
    ap.add_argument("--raw-glob", default=None,
                    help="the glob 00_raw.sql read, when it was not demo.sh's default")
    args = ap.parse_args()

    if not DB.exists():
        print(f"no warehouse at {DB}, run ./demo.sh all first", file=sys.stderr)
        return 1

    where = origins()
    pg = {} if args.no_postgres else postgres_counts()

    glob = args.raw_glob or source_glob()
    print(f"  raw_glob: {glob}")
    con = duckdb.connect(DB.as_posix(), read_only=True)
    con.execute(f"SET variable raw_glob = '{glob}'")
    relations = con.execute(
        "SELECT table_name, CASE WHEN table_type = 'VIEW' THEN 'view' ELSE 'table' END "
        "FROM information_schema.tables WHERE table_schema = 'main' ORDER BY table_name"
    ).fetchall()

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, kind in relations:
        layer, defined_in = where.get(name, ("5 other", ""))
        columns = con.execute(
            "SELECT column_name, data_type FROM duckdb_columns() "
            "WHERE schema_name = 'main' AND table_name = ? ORDER BY column_index",
            [name]).fetchall()
        db_rows = count(con, name)

        parquet = CURATED / f"{name}.parquet"
        if parquet.exists():
            pq_rows = con.execute(
                "SELECT count(*) FROM read_parquet(?)", [parquet.as_posix()]).fetchone()[0]
            pq_bytes = parquet.stat().st_size
        else:
            pq_rows = pq_bytes = ""

        pg_rows = pg.get(name, "")

        # An empty relation is a property of the input, not a defect. A single
        # live capture holds no alarm and no error, so six relations land empty
        # and every count still agrees. Only disagreement is a defect, so it
        # gets the verdict column and emptiness gets its own.
        problems = []
        if not isinstance(db_rows, int):
            problems.append(db_rows)
        if pq_rows != "" and pq_rows != db_rows:
            problems.append(f"parquet {pq_rows} against database {db_rows}")
        if pg_rows != "" and pg_rows != db_rows:
            problems.append(f"postgres {pg_rows} against database {db_rows}")

        rows.append({
            "layer": layer,
            "object": name,
            "kind": kind,
            "defined_in": defined_in,
            "db_rows": db_rows,
            "columns": len(columns),
            "column_names": " ".join(c for c, _ in columns),
            "column_types": " ".join(t for _, t in columns),
            "published": "yes" if parquet.exists() else "no",
            "parquet_rows": pq_rows,
            "parquet_bytes": pq_bytes,
            "postgres_rows": pg_rows,
            "empty": "yes" if db_rows == 0 else "no",
            "sample_row": sample(con, name),
            "verdict": "ok" if not problems else "; ".join(problems),
        })
    con.close()

    rows.sort(key=lambda r: (r["layer"], r["object"]))
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    failed = [r for r in rows if r["verdict"] != "ok"]
    empty = [r["object"] for r in rows if r["empty"] == "yes"]
    print(f"  {out.relative_to(ROOT).as_posix()}: {len(rows)} relations, "
          f"{len(rows) - len(failed)} counts agree, {len(failed)} to review, "
          f"{len(empty)} empty")
    for r in failed:
        print(f"    {r['object']}: {r['verdict']}")
    if empty:
        print("    empty, which the input decides: " + ", ".join(empty))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
