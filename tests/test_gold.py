"""The gold layer rests on assumptions the fixtures happen to satisfy.

Each test below pins one of them. If a future capture breaks an assumption, the
metric built on it becomes quietly wrong, which is the failure mode that costs
most: a dashboard that still renders.

The assumptions:

  - The kill counter resets to zero at the start of every run, so max(kills) is
    that run's kills rather than a running total across the page load.
  - Character and mode hold still for a whole run. Map does not, which is why
    fact_run reports a span of maps and not one map.
  - run_seq is an INTEGER in Parquet. A window sum returns HUGEINT, and HUGEINT
    lands as DOUBLE, so a consumer would have to cast it back.
  - No column anywhere claims a boss was killed. The recorder emits no defeat
    event, so the strongest word available is "progressed".
"""
import pathlib

import duckdb
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CURATED = ROOT / "warehouse" / "curated"

pytestmark = pytest.mark.skipif(
    not (CURATED / "fact_run.parquet").exists(),
    reason="gold Parquet is missing, run ./demo.sh build first",
)


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect()
    for name in ("fact_run", "fact_boss_encounter", "game_summary",
                 "character_usage", "boss_encounters_by_kind", "run_outcomes"):
        path = (CURATED / f"{name}.parquet").as_posix()
        c.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{path}')")
    return c


def one(con, sql):
    return con.execute(sql).fetchone()


# --------------------------------------------------------------------------
# Grain
# --------------------------------------------------------------------------
def test_run_id_is_unique(con):
    rows, distinct = one(con, "SELECT count(*), count(DISTINCT run_id) FROM fact_run")
    assert rows == distinct


def test_encounter_id_is_unique(con):
    rows, distinct = one(
        con, "SELECT count(*), count(DISTINCT encounter_id) FROM fact_boss_encounter")
    assert rows == distinct


def test_a_run_is_finer_than_a_page_load(con):
    """The whole reason gold exists. If these were equal, it would not."""
    runs, page_loads = one(
        con, "SELECT count(*), count(DISTINCT (session_id, page_load_seq)) FROM fact_run")
    assert runs > page_loads


def test_every_encounter_belongs_to_a_run(con):
    orphans, = one(con, """
        SELECT count(*) FROM fact_boss_encounter e
        WHERE NOT EXISTS (SELECT 1 FROM fact_run r WHERE r.run_id = e.run_id)
    """)
    assert orphans == 0


# --------------------------------------------------------------------------
# Typing
# --------------------------------------------------------------------------
@pytest.mark.parametrize("column, expected", [
    ("run_seq", "INTEGER"),
    ("page_load_seq", "INTEGER"),
])
def test_sequence_columns_are_integers_in_parquet(con, column, expected):
    """A HUGEINT window sum lands as DOUBLE. This is trap 3, again."""
    path = (CURATED / "fact_run.parquet").as_posix()
    types = dict(con.execute(
        f"SELECT column_name, column_type FROM (DESCRIBE SELECT * FROM read_parquet('{path}'))"
    ).fetchall())
    assert types[column] == expected


# --------------------------------------------------------------------------
# The assumptions the metrics rest on
# --------------------------------------------------------------------------
def test_hp_and_kills_are_never_negative(con):
    bad, = one(con, "SELECT count(*) FROM fact_run WHERE kills < 0 OR hp_min < 0")
    assert bad == 0


def test_a_run_never_ends_before_it_starts(con):
    bad, = one(con, "SELECT count(*) FROM fact_run WHERE ended_srv < started_srv")
    assert bad == 0


def test_play_time_never_exceeds_wall_time(con):
    """sim_active_s counts only states where the clock advances."""
    bad, = one(con, """
        SELECT count(*) FROM fact_run
        WHERE sim_active_s > duration_s + 0.05
    """)
    assert bad == 0


def test_map_is_reported_as_a_span_not_a_single_value(con):
    """One fixture run walks three maps. A single map column would lie."""
    path = (CURATED / "fact_run.parquet").as_posix()
    columns = {r[0] for r in con.execute(
        f"SELECT column_name FROM (DESCRIBE SELECT * FROM read_parquet('{path}'))"
    ).fetchall()}
    assert {"maps_visited", "first_map", "last_map"} <= columns
    assert "map" not in columns
    multi, = one(con, "SELECT count(*) FROM fact_run WHERE maps_visited > 1")
    assert multi > 0, "no multi-map run left to prove the point"


# --------------------------------------------------------------------------
# The metric views must agree with the facts under them
# --------------------------------------------------------------------------
def test_game_summary_agrees_with_fact_run(con):
    summary = con.execute("SELECT runs, max_kills, min_kills FROM game_summary").fetchone()
    facts = one(con, "SELECT count(*), max(kills), min(kills) FROM fact_run")
    assert summary == facts


def test_run_outcomes_cover_every_run(con):
    total, = one(con, "SELECT sum(runs) FROM run_outcomes")
    runs, = one(con, "SELECT count(*) FROM fact_run")
    assert total == runs


def test_character_usage_lists_every_documented_character(con):
    """A LEFT JOIN from the dimension. A character nobody played still shows."""
    listed, played = one(con, """
        SELECT count(*), count(*) FILTER (WHERE runs > 0) FROM character_usage
    """)
    assert listed == 5, "characters.csv documents five"
    assert played < listed, "the unplayed character is the point of the view"


def test_boss_counts_add_up(con):
    bad, = one(con, """
        SELECT count(*) FROM boss_encounters_by_kind
        WHERE encounters <> progressed + died + won + unresolved
    """)
    assert bad == 0


# --------------------------------------------------------------------------
# Honesty
# --------------------------------------------------------------------------
def test_nothing_claims_a_boss_was_killed(con):
    """No defeat event exists in the wire format, so no column may say so."""
    outcomes = {r[0] for r in con.execute(
        "SELECT DISTINCT outcome FROM fact_boss_encounter").fetchall()}
    for word in ("killed", "kill", "defeated", "slain"):
        assert not any(word in o.lower() for o in outcomes), f"{outcomes} claims a defeat"


def test_the_gold_sql_says_progressed_is_a_proxy(con):
    """The comment is the only thing stopping a reader misreading the column."""
    sql = (ROOT / "pipeline" / "22_gold.sql").read_text(encoding="utf-8")
    assert "proxy" in sql.lower()


def test_the_reference_data_decides_what_a_run_is(con):
    """Run membership must come from app_states.csv, not a list in the SQL."""
    sql = (ROOT / "pipeline" / "22_gold.sql").read_text(encoding="utf-8")
    assert "dim_app_state" in sql
    states = (ROOT / "fixtures" / "reference" / "app_states.csv").read_text(encoding="utf-8")
    header = states.splitlines()[0].split(",")
    assert "in_run" in header and "is_run_state" in header
    # Every documented state carries a value for both flags.
    for line in states.splitlines()[1:]:
        if line.strip():
            assert line.split(",")[1] in ("true", "false")
            assert line.split(",")[2] in ("true", "false")


def test_contract_caps_are_type_two(con):
    """The only historised dimension. Every cap has exactly one current row."""
    path = (CURATED / "contract_cap_history.parquet").as_posix()
    con.execute(f"CREATE OR REPLACE VIEW cap_history AS SELECT * FROM read_parquet('{path}')")
    caps, current = one(con, """
        SELECT count(DISTINCT cap_key), count(*) FILTER (WHERE is_current) FROM cap_history
    """)
    assert caps == 5, "the contract declares five caps"
    assert current == caps, "each cap must have exactly one row in force"
    open_ended, = one(con,
        "SELECT count(*) FROM cap_history WHERE is_current AND valid_to IS NOT NULL")
    assert open_ended == 0, "a current row cannot already be closed"
    closed_open, = one(con,
        "SELECT count(*) FROM cap_history WHERE NOT is_current AND valid_to IS NULL")
    assert closed_open == 0, "a superseded row must carry a valid_to"
