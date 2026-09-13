-- Gold layer: the game domain, derived from the telemetry.
--
-- Silver answers "is the data sound". Gold answers "what happened in the game".
-- Those are different questions at different grains, which is why this is a
-- separate layer and not more views in 20_curated.sql.
--
-- Three ideas carry this layer.
--
-- 1. A run is not a page load. A page load opens on hello and closes on bye. A
--    run starts when the player enters gameplay and ends when they leave it.
--    One page load holds up to four runs in the fixtures. session_summary has a
--    CTE named `run` that groups by page load, so its `kills` means "the best
--    of up to four runs", not "kills in the run". Gold fixes that grain.
--
-- 2. The reference data decides what a run is, not this file. app_states.csv
--    carries two flags. `in_run` says the state occurs while a run is in
--    progress. `is_run_state` says the simulation clock advances. They differ:
--    `talents` and `stage_intro` sit inside a run with the clock stopped, so
--    wall time and play time are different numbers and both are published.
--
-- 3. No defeat event exists. The wire format records no boss result, and `win`
--    never occurs in the fixtures. So a boss encounter carries the state that
--    followed it, and nothing here claims a kill. See the outcome CASE below.
--
-- Slowly changing dimensions. Two kinds live here, and the split is deliberate.
--
-- A dimension whose value decided something keeps its history. A quarantine
-- decision taken under events_per_beat = 400 cannot be reproduced once that
-- number moves, and a run labelled "archer, fast glass cannon" cannot be read
-- back once the playbook rewrites that line. Those are Type 2.
--
-- app_states and modes are rebuilt from source, Type 1. Nothing published names
-- a mode, and app_states carries two flags rather than a description, so it
-- needs its own table and its own decision. Both are noted in docs/hlad.md.
--
-- valid_from here is transaction time: the moment this pipeline first saw the
-- value, not the moment it became true in the game. The reference CSVs carry no
-- dates, so no other reading is available from them. One consequence is worth
-- stating plainly rather than discovering later. An as-of join against a fact's
-- own timestamp is not supported, because every version starts after every fact
-- in this warehouse. Facts join the current version, which is what dim_character
-- and dim_boss already hand them.

--------------------------------------------------------------------------------
-- Type 1 dimensions. Straight from the second source, overwritten every run.
--------------------------------------------------------------------------------
CREATE OR REPLACE TABLE dim_mode AS
SELECT mode AS mode_key, note AS description FROM ref_modes;

CREATE OR REPLACE TABLE dim_app_state AS
SELECT state AS state_key, is_run_state, in_run, note AS description FROM ref_states;

--------------------------------------------------------------------------------
-- dim_member. Type 2, every versioned reference member in one table.
--
-- Characters and bosses have the same shape, a key and a description, so they
-- share one table and the dimension name is a column. Three passes written once
-- beat the same three passes written twice. Nothing downstream reads this table:
-- each dimension keeps its own view below, so a join stays a join against
-- dim_character rather than a filter a caller has to remember.
--
-- CREATE TABLE IF NOT EXISTS, never CREATE OR REPLACE. Replacing it every run
-- would delete the history it exists to hold. demo.sh removes warehouse/raw and
-- leaves the database file, so the rows survive a normal rebuild. Deleting
-- flightdeck.duckdb by hand still resets the history, which no design here can
-- prevent.
--
-- Type 2 needs two passes at least. One statement cannot both close the old row
-- and open the new one for the same key, because WHEN MATCHED updates the row it
-- matched. Anything that looks like one statement is hiding the second.
--------------------------------------------------------------------------------
CREATE OR REPLACE VIEW ref_members AS
SELECT 'character' AS dimension, "char" AS member_key, note AS description FROM ref_chars
UNION ALL
SELECT 'boss', boss, note FROM ref_bosses;

CREATE TABLE IF NOT EXISTS dim_member (
    dimension   VARCHAR,
    member_key  VARCHAR,
    description VARCHAR,
    version_seq INTEGER,
    valid_from  TIMESTAMP WITH TIME ZONE,
    valid_to    TIMESTAMP WITH TIME ZONE,
    is_current  BOOLEAN
);

-- Pass 1. Close the current row of any member whose description moved.
MERGE INTO dim_member AS t
USING ref_members AS s
   ON t.dimension = s.dimension AND t.member_key = s.member_key AND t.is_current
WHEN MATCHED AND t.description IS DISTINCT FROM s.description
  THEN UPDATE SET valid_to = now(), is_current = false;

-- Pass 2. Close any member the playbook no longer lists. A character that was
-- withdrawn still described the runs it was played in.
UPDATE dim_member AS t
   SET valid_to = now(), is_current = false
 WHERE t.is_current
   AND NOT EXISTS (
       SELECT 1 FROM ref_members s
        WHERE s.dimension = t.dimension AND s.member_key = t.member_key
   );

-- Pass 3. Open a row for every member without a current one. That covers a new
-- member and a member pass 1 just closed, in the same statement. version_seq
-- counts from the whole history of that member, so a reopened key continues its
-- numbering instead of restarting at one.
INSERT INTO dim_member
SELECT s.dimension,
       s.member_key,
       s.description,
       1 + coalesce((SELECT max(h.version_seq) FROM dim_member h
                      WHERE h.dimension = s.dimension
                        AND h.member_key = s.member_key), 0),
       now(),
       NULL,
       true
FROM ref_members s
WHERE NOT EXISTS (
    SELECT 1 FROM dim_member t
     WHERE t.dimension = s.dimension AND t.member_key = s.member_key AND t.is_current
);

-- The current version of each dimension, with the columns every consumer here
-- already reads. The version columns are deliberately absent: a join that wants
-- one row per character must not have to filter for it.
--
-- Tables and not views, so that a database built before dim_member existed is
-- replaced rather than refused. CREATE OR REPLACE cannot turn a table into a
-- view, and these two were tables.
CREATE OR REPLACE TABLE dim_character AS
SELECT member_key AS character_key, description
FROM dim_member WHERE dimension = 'character' AND is_current;

CREATE OR REPLACE TABLE dim_boss AS
SELECT member_key AS boss_key, description
FROM dim_member WHERE dimension = 'boss' AND is_current;

-- One change log across both dimensions, published as one file. A reader asking
-- "what did the playbook say about archer before" reads this and nothing else.
CREATE OR REPLACE VIEW reference_history AS
SELECT dimension,
       member_key,
       version_seq,
       description,
       valid_from,
       valid_to,
       is_current,
       CASE WHEN is_current THEN 'in force' ELSE 'superseded' END AS status
FROM dim_member
ORDER BY dimension, member_key, version_seq;

--------------------------------------------------------------------------------
-- dim_contract_cap. Type 2, on its own, for one reason.
--
-- A cap is a number and a member is a description, so folding the cap into
-- dim_member would mean storing 400 as text. The passes below are the same three
-- passes, kept separate to keep the column a BIGINT. Two implementations is the
-- price of that, and the second one is where any third belongs.
--
-- The history matters because the cap decided something. A record moved to
-- quarantine because a cap said so, and once that cap changes the decision
-- becomes unreproducible unless the old value survives somewhere.
--------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_contract_cap (
    cap_key    VARCHAR,
    cap_value  BIGINT,
    valid_from TIMESTAMP WITH TIME ZONE,
    valid_to   TIMESTAMP WITH TIME ZONE,
    is_current BOOLEAN
);

-- Pass 1. Close the current row of any cap whose value moved.
MERGE INTO dim_contract_cap AS t
USING contract_caps AS s
   ON t.cap_key = s.name AND t.is_current
WHEN MATCHED AND t.cap_value IS DISTINCT FROM s.value
  THEN UPDATE SET valid_to = now(), is_current = false;

-- Pass 2. Close any cap the contract no longer declares. A rule that was
-- withdrawn still governed the records it judged while it stood.
UPDATE dim_contract_cap
   SET valid_to = now(), is_current = false
 WHERE is_current
   AND cap_key NOT IN (SELECT name FROM contract_caps);

-- Pass 3. Open a row for every cap without a current one. That covers a brand
-- new cap and a cap pass 1 just closed, in the same statement.
INSERT INTO dim_contract_cap
SELECT s.name, s.value, now(), NULL, true
FROM contract_caps s
WHERE NOT EXISTS (
    SELECT 1 FROM dim_contract_cap t WHERE t.cap_key = s.name AND t.is_current
);

CREATE OR REPLACE VIEW contract_cap_history AS
SELECT cap_key,
       cap_value,
       valid_from,
       valid_to,
       is_current,
       CASE WHEN is_current THEN 'in force' ELSE 'superseded' END AS status
FROM dim_contract_cap
ORDER BY cap_key, valid_from;

-- reference_governance. One row per versioned dimension, plus a total row.
--
-- The governance page shows these as cards, and a page may select and format
-- but may not aggregate. So the totals live here. GROUPING SETS gives the per
-- dimension rows and the total from one scan, which keeps the two from ever
-- disagreeing.
--
-- dim_contract_cap joins in through a window rather than a stored column. It
-- predates version_seq and adding the column would rewrite its history.
CREATE OR REPLACE VIEW reference_governance AS
WITH versioned AS (
    SELECT dimension, member_key, version_seq, valid_from, is_current
    FROM dim_member
    UNION ALL
    SELECT 'contract cap' AS dimension,
           cap_key        AS member_key,
           CAST(row_number() OVER (PARTITION BY cap_key ORDER BY valid_from) AS INTEGER)
                          AS version_seq,
           valid_from,
           is_current
    FROM dim_contract_cap
),
rolled AS (
    SELECT dimension,
           CAST(grouping(dimension) AS INTEGER)                 AS is_total,
           CAST(count(DISTINCT member_key) AS INTEGER)          AS members,
           CAST(count(DISTINCT member_key) FILTER (WHERE is_current) AS INTEGER)
                                                                AS members_in_force,
           CAST(count(*) AS INTEGER)                            AS versions,
           CAST(count(*) FILTER (WHERE NOT is_current) AS INTEGER) AS superseded,
           max(version_seq)                                     AS deepest_history,
           min(valid_from)                                      AS first_seen,
           max(valid_from)                                      AS last_change
    FROM versioned
    GROUP BY GROUPING SETS ((dimension), ())
)
SELECT coalesce(dimension, 'every dimension') AS dimension,
       members,
       members_in_force,
       versions,
       superseded,
       deepest_history,
       first_seen,
       last_change
FROM rolled
ORDER BY is_total, dimension;

--------------------------------------------------------------------------------
-- Run segmentation. One home for the window logic, because both facts need it.
--
-- run_seq counts run starts within a page load. A run starts on the first
-- in_run state after a state that was not in_run, which is exactly the
-- charselect -> playing and menu -> playing transitions the fixtures show.
--
-- The cast to INTEGER is not cosmetic. A window sum returns HUGEINT, and a
-- HUGEINT lands as DOUBLE in Parquet, so every consumer downstream would have
-- to cast it back.
--------------------------------------------------------------------------------
CREATE OR REPLACE TABLE run_pulse AS
WITH labelled AS (
    SELECT p.session_id,
           p.page_load_seq,
           p.client_id,
           p.srv,
           p.state,
           p."char"                                       AS character_key,
           p.mode                                         AS mode_key,
           p.map,
           p.boss                                         AS boss_key,
           p.kills,
           p.hp,
           d.in_run,
           d.is_run_state,
           lag(d.in_run) OVER w                           AS prev_in_run,
           -- The wall time this pulse covers, measured to the next pulse in the
           -- same page load. The last pulse of a page load covers nothing.
           coalesce(lead(p.srv) OVER w - p.srv, 0) / 1000.0 AS held_s
    FROM pulses p
    JOIN dim_app_state d ON d.state_key = p.state
    WINDOW w AS (PARTITION BY p.session_id, p.page_load_seq ORDER BY p.srv)
),
numbered AS (
    SELECT *,
           CAST(sum(CASE WHEN in_run AND (prev_in_run IS NULL OR NOT prev_in_run)
                         THEN 1 ELSE 0 END)
               OVER (PARTITION BY session_id, page_load_seq
                     ORDER BY srv ROWS UNBOUNDED PRECEDING) AS INTEGER) AS run_seq
    FROM labelled
)
SELECT session_id || '#' || page_load_seq || '/' || run_seq AS run_id,
       session_id, page_load_seq, run_seq, client_id, srv, state,
       character_key, mode_key, map, boss_key, kills, hp,
       in_run, is_run_state, held_s
FROM numbered
WHERE in_run AND run_seq >= 1;

--------------------------------------------------------------------------------
-- fact_run. One row per run.
--
-- kills is max(), not max() - min(), because the counter resets to zero at every
-- run start. All six fixture runs open on kills = 0, which the tests pin.
--------------------------------------------------------------------------------
CREATE OR REPLACE TABLE fact_run AS
WITH bounds AS (
    SELECT run_id, any_value(session_id) AS session_id,
           any_value(page_load_seq) AS page_load_seq, max(srv) AS last_srv
    FROM run_pulse GROUP BY run_id
),
ended AS (
    -- The first state after the run, which is how a run reports its ending.
    SELECT b.run_id, (
        SELECT arg_min(p.state, p.srv) FROM pulses p
        WHERE p.session_id = b.session_id
          AND p.page_load_seq = b.page_load_seq
          AND p.srv > b.last_srv
    ) AS ended_on
    FROM bounds b
)
SELECT r.run_id,
       r.session_id,
       r.page_load_seq,
       r.run_seq,
       r.client_id,
       -- The character and mode a run opens with. Both are stable for the whole
       -- run in the fixtures, and a test pins that. arg_min is deterministic
       -- where any_value is not, so a re-run cannot quietly pick differently.
       arg_min(r.character_key, r.srv)                         AS character_key,
       arg_min(r.mode_key, r.srv)                              AS mode_key,
       -- map is NOT a run attribute. One fixture run walks castle, maze and
       -- forest as it progresses stages, so a single map column would report
       -- whichever row won a race. The grain below a run is a stage, and no
       -- stage fact exists yet, so a run reports its span of maps instead.
       count(DISTINCT r.map)                                   AS maps_visited,
       arg_min(r.map, r.srv)                                   AS first_map,
       arg_max(r.map, r.srv)                                   AS last_map,
       min(r.srv)                                              AS started_srv,
       max(r.srv)                                              AS ended_srv,
       round((max(r.srv) - min(r.srv)) / 1000.0, 1)            AS duration_s,
       round(sum(CASE WHEN r.is_run_state THEN r.held_s ELSE 0 END), 1) AS sim_active_s,
       max(r.kills)                                            AS kills,
       arg_min(r.hp, r.srv)                                    AS hp_first,
       min(r.hp)                                               AS hp_min,
       arg_max(r.hp, r.srv)                                    AS hp_last,
       count(DISTINCT r.state)                                 AS states_visited,
       count(DISTINCT r.boss_key)                              AS bosses_faced,
       coalesce(any_value(e.ended_on), 'no further state')     AS ended_on,
       CASE coalesce(any_value(e.ended_on), 'none')
           WHEN 'gameover' THEN 'died'
           WHEN 'win'      THEN 'won'
           WHEN 'menu'     THEN 'left to menu'
           ELSE 'unresolved, page load ended first'
       END                                                     AS outcome
FROM run_pulse r
LEFT JOIN ended e USING (run_id)
GROUP BY r.run_id, r.session_id, r.page_load_seq, r.run_seq, r.client_id;

--------------------------------------------------------------------------------
-- fact_boss_encounter. One row per contiguous block of pulses naming a boss.
--
-- outcome is deliberately not "killed". The recorder emits no boss result, so
-- this column reports the state that followed the fight and nothing more.
-- `progressed` means the player reached a reward screen, which is the closest
-- available proxy for a defeat. It is a proxy, not evidence.
--------------------------------------------------------------------------------
CREATE OR REPLACE TABLE fact_boss_encounter AS
WITH boss_pulses AS (
    SELECT *,
           lag(boss_key) OVER (PARTITION BY run_id ORDER BY srv) AS prev_boss
    FROM run_pulse
    WHERE boss_key IS NOT NULL
),
blocked AS (
    SELECT *,
           CAST(sum(CASE WHEN prev_boss IS DISTINCT FROM boss_key THEN 1 ELSE 0 END)
               OVER (PARTITION BY run_id ORDER BY srv ROWS UNBOUNDED PRECEDING)
               AS INTEGER) AS encounter_seq
    FROM boss_pulses
),
bounds AS (
    SELECT run_id, encounter_seq,
           any_value(session_id)                        AS session_id,
           any_value(page_load_seq)                     AS page_load_seq,
           any_value(boss_key)                          AS boss_key,
           any_value(character_key)                     AS character_key,
           min(srv)                                     AS started_srv,
           max(srv)                                     AS ended_srv,
           round((max(srv) - min(srv)) / 1000.0, 1)     AS duration_s,
           round(sum(CASE WHEN is_run_state THEN held_s ELSE 0 END), 1) AS sim_active_s,
           max(kills) - min(kills)                      AS kills_during,
           min(hp)                                      AS hp_min
    FROM blocked GROUP BY run_id, encounter_seq
),
followed AS (
    SELECT b.*, (
        SELECT arg_min(p.state, p.srv)
        FROM pulses p
        WHERE p.session_id = b.session_id
          AND p.page_load_seq = b.page_load_seq
          AND p.srv > b.ended_srv
    ) AS next_state
    FROM bounds b
)
SELECT run_id || '/b' || encounter_seq AS encounter_id,
       run_id, session_id, page_load_seq, boss_key, character_key,
       started_srv, ended_srv, duration_s, sim_active_s, kills_during, hp_min,
       coalesce(next_state, 'no further state') AS next_state,
       CASE
           WHEN next_state IN ('talents', 'chooser', 'stage_intro') THEN 'progressed'
           WHEN next_state = 'gameover'                             THEN 'died'
           WHEN next_state = 'win'                                  THEN 'won'
           ELSE 'unresolved'
       END AS outcome
FROM followed;

--------------------------------------------------------------------------------
-- Metric views. The site reads these and computes nothing of its own.
--------------------------------------------------------------------------------
CREATE OR REPLACE VIEW game_summary AS
SELECT count(*)                              AS runs,
       count(DISTINCT character_key)         AS characters_played,
       (SELECT count(DISTINCT map) FROM run_pulse) AS maps_played,
       round(sum(duration_s), 1)             AS total_wall_s,
       round(sum(sim_active_s), 1)           AS total_sim_s,
       round(avg(duration_s), 1)             AS avg_run_wall_s,
       round(avg(sim_active_s), 1)           AS avg_run_sim_s,
       max(duration_s)                       AS max_run_wall_s,
       min(kills)                            AS min_kills,
       max(kills)                            AS max_kills,
       round(avg(kills), 1)                  AS avg_kills
FROM fact_run;

CREATE OR REPLACE VIEW character_usage AS
SELECT d.character_key,
       d.description,
       count(r.run_id)                            AS runs,
       round(coalesce(sum(r.sim_active_s), 0), 1) AS sim_active_s,
       coalesce(max(r.kills), 0)                  AS best_kills,
       round(coalesce(avg(r.kills), 0), 1)        AS avg_kills
FROM dim_character d
LEFT JOIN fact_run r ON r.character_key = d.character_key
GROUP BY ALL
ORDER BY runs DESC, d.character_key;

CREATE OR REPLACE VIEW boss_encounters_by_kind AS
SELECT d.boss_key,
       d.description,
       count(e.encounter_id)                                        AS encounters,
       count(*) FILTER (WHERE e.outcome = 'progressed')             AS progressed,
       count(*) FILTER (WHERE e.outcome = 'died')                   AS died,
       count(*) FILTER (WHERE e.outcome = 'won')                    AS won,
       count(*) FILTER (WHERE e.outcome = 'unresolved')             AS unresolved,
       round(coalesce(sum(e.sim_active_s), 0), 1)                   AS sim_active_s
FROM dim_boss d
LEFT JOIN fact_boss_encounter e ON e.boss_key = d.boss_key
GROUP BY ALL
ORDER BY encounters DESC, d.boss_key;

CREATE OR REPLACE VIEW run_outcomes AS
SELECT outcome,
       count(*)                    AS runs,
       round(avg(duration_s), 1)   AS avg_wall_s,
       round(avg(sim_active_s), 1) AS avg_sim_s,
       max(kills)                  AS best_kills
FROM fact_run
GROUP BY ALL
ORDER BY runs DESC, outcome;
