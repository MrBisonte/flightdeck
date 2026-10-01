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
-- back once the playbook rewrites that line. A run's play time is the sum of
-- the pulses whose state advances the clock, so reclassifying a state would
-- rewrite every past run. Those are Type 2.
--
-- modes are rebuilt from source, Type 1. Nothing published names a mode.
--
-- valid_from here is valid time: when the value became true in its own source,
-- declared in the file that holds it. A member dates from the first crow-archer
-- commit that names it, and a cap from the commit that put it in the contract.
-- Every member predates every fact, so a fact can join the version in force at
-- its own timestamp. The dates live in committed files, so a rebuild from
-- nothing produces the same history.

--------------------------------------------------------------------------------
-- Type 1 dimensions. Straight from the second source, overwritten every run.
--------------------------------------------------------------------------------
CREATE OR REPLACE TABLE dim_mode AS
SELECT mode AS mode_key, note AS description FROM ref_modes;

--------------------------------------------------------------------------------
-- dim_app_state. Type 2, and the one dimension a fact joins as-of.
--
-- is_run_state is arithmetic, not description: fact_run.sim_active_s sums the
-- pulses it flags. run_pulse below joins the version in force when each pulse
-- arrived, so a state reclassified from a later date changes the runs after
-- that date and leaves every earlier run as it was.
--------------------------------------------------------------------------------
CREATE OR REPLACE TABLE dim_app_state AS
SELECT state AS state_key,
       is_run_state,
       in_run,
       note AS description,
       CAST(row_number() OVER (PARTITION BY state ORDER BY valid_from) AS INTEGER)
            AS version_seq,
       valid_from,
       valid_to,
       valid_to IS NULL AS is_current
FROM ref_state_versions;

-- Its own file rather than rows in reference_history, because a state carries
-- two flags and a member carries a description. Folding them together would
-- hide a change to a flag behind an unchanged description.
CREATE OR REPLACE VIEW app_state_history AS
SELECT state_key,
       version_seq,
       is_run_state,
       in_run,
       description,
       valid_from,
       valid_to,
       is_current,
       CASE WHEN is_current THEN 'in force' ELSE 'superseded' END AS status
FROM dim_app_state
ORDER BY state_key, version_seq;

--------------------------------------------------------------------------------
-- dim_member. Type 2, every versioned reference member in one table.
--
-- Characters and bosses have the same shape, a key and a description, so they
-- share one table and the dimension name is a column. Nothing downstream reads
-- this table: each dimension keeps its own table below, so a join stays a join
-- against dim_character rather than a filter a caller has to remember.
--
-- The reference files declare every version with its dates, so this is a plain
-- rebuild. No pass compares the file to what an earlier run stored, and
-- deleting flightdeck.duckdb loses nothing.
--------------------------------------------------------------------------------
CREATE OR REPLACE VIEW ref_members AS
SELECT 'character' AS dimension, "char" AS member_key, note AS description, valid_from, valid_to
FROM ref_char_versions
UNION ALL
SELECT 'boss', boss, note, valid_from, valid_to FROM ref_boss_versions;

CREATE OR REPLACE TABLE dim_member AS
SELECT dimension,
       member_key,
       description,
       CAST(row_number() OVER (PARTITION BY dimension, member_key ORDER BY valid_from)
            AS INTEGER) AS version_seq,
       valid_from,
       valid_to,
       valid_to IS NULL AS is_current
FROM ref_members;

-- The current version of each dimension, with the columns every consumer here
-- already reads. The version columns are deliberately absent: a join that wants
-- one row per character must not have to filter for it.
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
-- dim_member would mean storing 400 as text. The versions come from
-- contract_caps, which 10_typed.sql fills from the contract.
--
-- The history matters because the cap decided something. A record moved to
-- quarantine because a cap said so, and the old value has to survive the change
-- for that decision to stay explainable.
--------------------------------------------------------------------------------
CREATE OR REPLACE TABLE dim_contract_cap AS
SELECT name  AS cap_key,
       value AS cap_value,
       CAST(row_number() OVER (PARTITION BY name ORDER BY valid_from) AS INTEGER)
             AS version_seq,
       valid_from,
       valid_to,
       valid_to IS NULL AS is_current
FROM contract_caps;

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
CREATE OR REPLACE VIEW reference_governance AS
WITH versioned AS (
    SELECT dimension, member_key, version_seq, valid_from, is_current
    FROM dim_member
    UNION ALL
    SELECT 'app state', state_key, version_seq, valid_from, is_current
    FROM dim_app_state
    UNION ALL
    SELECT 'contract cap', cap_key, version_seq, valid_from, is_current
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
           min(valid_from)                                      AS first_valid_from,
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
       first_valid_from,
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
    -- The version in force when the pulse arrived. Every state predates every
    -- pulse, and tests/test_versioned_dimensions.py fails if one does not.
    JOIN dim_app_state d
      ON d.state_key = p.state
     AND srv_time(p.srv) >= d.valid_from
     AND srv_time(p.srv) <  coalesce(d.valid_to, 'infinity'::TIMESTAMPTZ)
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
-- run_events. The event ring, placed inside the run it belongs to.
--
-- pulses carry srv, the server clock. The event ring carries only the page
-- clock, so the two cannot be compared directly. A 1.5 s tolerance either side
-- of the run's srv bounds absorbs the skew: clock_skew measures 0 to 9 ms on
-- localhost and 473 to 593 ms on the published build, so 1500 ms clears the
-- worst case by more than double and still cannot reach the next run, because
-- no two runs in the fixtures start within three seconds of each other. A test
-- pins that no event lands in two runs.
--
-- This sits above fact_run rather than with the other event views below,
-- because fact_run counts kill events and cannot read a relation defined after
-- it. One bridge, one home: run_kill_events and character_combat both read it
-- rather than each repeating the join.
--------------------------------------------------------------------------------
CREATE OR REPLACE VIEW run_events AS
WITH runs AS (
    SELECT run_id, session_id, page_load_seq, character_key,
           min(srv) AS s0, max(srv) AS s1
    FROM run_pulse
    GROUP BY run_id, session_id, page_load_seq, character_key
)
SELECT r.run_id, r.character_key, e.message, e."timestamp" AS ts
FROM events e
JOIN runs r ON e.session_id = r.session_id
           AND e.page_load_seq = r.page_load_seq
           AND e."timestamp" BETWEEN r.s0 - 1500 AND r.s1 + 1500;

-- The kill events alone. Every event-grain view below stands on this.
CREATE OR REPLACE VIEW run_kill_events AS
SELECT run_id, character_key, message, ts
FROM run_events
WHERE message IN ('CROW_KILLED', 'SKELETON_KILLED');

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
),
counted AS (
    SELECT run_id, count(*) AS kill_events FROM run_kill_events GROUP BY run_id
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
       -- Two claims about the same fact, both published. kills is the HUD
       -- counter, which the game writes onto every pulse. kill_events counts
       -- CROW_KILLED and SKELETON_KILLED in the ring. They disagree on the two
       -- runs that walked into a second map, because the counter stops at the
       -- first stage. kill_reconciliation publishes the difference, and
       -- docs/defect-log.md records it as a game defect.
       max(r.kills)                                            AS kills,
       CAST(coalesce(any_value(c.kill_events), 0) AS INTEGER)  AS kill_events,
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
LEFT JOIN counted c USING (run_id)
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
-- Metric views. The site reads these, and every number it shows comes from
-- here rather than from a query a page invented.
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

--------------------------------------------------------------------------------
-- Player-facing metric views.
--
-- The views above answer "what happened in the game". These answer what a
-- player would ask: who scored most, how fast, how many at once, how far did
-- the run get. Four of the six read the event ring through run_events, which
-- nothing published had touched before.
--------------------------------------------------------------------------------

-- One row per run, ranked. Every figure a leaderboard needs, at the run grain.
--
-- rank_by_kills ranks on the HUD counter, not on kill_events, so the ranking
-- and the number beside it come from the same claim. kill_events travels in the
-- same row, and kill_reconciliation is where the two are put side by side.
CREATE OR REPLACE VIEW run_scorecard AS
WITH timed AS (
    SELECT run_id, srv, state, kills, hp,
           round((srv - min(srv) OVER (PARTITION BY run_id)) / 1000.0, 1)          AS t_s,
           kills - coalesce(lag(kills) OVER (PARTITION BY run_id ORDER BY srv), 0) AS kills_this_beat
    FROM run_pulse
),
marks AS (
    SELECT run_id,
           min(CASE WHEN kills >= 1  THEN t_s END)             AS t_first_kill_s,
           min(CASE WHEN kills >= 50 THEN t_s END)             AS t_50_kills_s,
           min(CASE WHEN state = 'boss_fight' THEN t_s END)    AS t_boss_s,
           max(kills_this_beat)                                AS max_kills_one_beat,
           max(hp) - min(hp)                                   AS hp_lost
    FROM timed
    GROUP BY run_id
)
SELECT CAST(rank() OVER (ORDER BY f.kills DESC, f.sim_active_s) AS INTEGER) AS rank_by_kills,
       f.run_id,
       f.character_key,
       f.first_map,
       f.maps_visited,
       f.outcome,
       f.kills,
       f.kill_events,
       f.duration_s,
       f.sim_active_s,
       round(f.kills * 60.0 / nullif(f.sim_active_s, 0), 1)    AS kills_per_min,
       m.t_first_kill_s,
       m.t_50_kills_s,
       m.t_boss_s,
       m.max_kills_one_beat,
       m.hp_lost
FROM fact_run f
JOIN marks m USING (run_id);

-- A burst is kills that land within 50 ms of each other: one hit, several
-- kills. A streak is kills chained within 1 s. Both are the same window over
-- the same stream, and the gap is the only thing that differs, so the window is
-- written once and the gap is a parameter.
CREATE OR REPLACE MACRO kill_groups(gap_ms) AS TABLE
WITH g AS (
    SELECT *,
           CASE WHEN ts - lag(ts) OVER w > gap_ms OR lag(ts) OVER w IS NULL
                THEN 1 ELSE 0 END AS opens
    FROM run_kill_events
    WINDOW w AS (PARTITION BY run_id ORDER BY ts)
),
n AS (
    SELECT *,
           CAST(sum(opens) OVER (PARTITION BY run_id ORDER BY ts ROWS UNBOUNDED PRECEDING)
                AS INTEGER) AS group_id
    FROM g
)
SELECT run_id,
       character_key,
       group_id,
       CAST(count(*) AS INTEGER) AS kills,
       max(ts) - min(ts)         AS span_ms,
       min(ts)                   AS started_ts
FROM n
GROUP BY run_id, character_key, group_id;

CREATE OR REPLACE VIEW kill_bursts  AS SELECT * FROM kill_groups(50);
CREATE OR REPLACE VIEW kill_streaks AS SELECT * FROM kill_groups(1000);

-- Two claims about the same fact. The HUD counter rides on every pulse, the
-- kill events ride on the event ring. Where they disagree, this says so and by
-- how much. It reads fact_run rather than recounting, so the number here and
-- the number on the leaderboard cannot drift apart.
CREATE OR REPLACE VIEW kill_reconciliation AS
SELECT run_id,
       character_key,
       maps_visited,
       kills                      AS counter_kills,
       kill_events                AS event_kills,
       kill_events - kills        AS events_minus_counter,
       kill_events = kills        AS agrees
FROM fact_run;

-- How far each run got, as a funnel over states the reference dimension
-- documents. A renamed state shows up in app_state_history before it breaks
-- this chart.
CREATE OR REPLACE VIEW run_funnel AS
SELECT 'started a run'             AS step, 1 AS step_seq, CAST(count(DISTINCT run_id) AS INTEGER) AS runs FROM run_pulse
UNION ALL SELECT 'reached the boss entrance', 2, CAST(count(DISTINCT run_id) AS INTEGER) FROM run_pulse WHERE state = 'boss_entrance'
UNION ALL SELECT 'fought the boss',           3, CAST(count(DISTINCT run_id) AS INTEGER) FROM run_pulse WHERE state = 'boss_fight'
UNION ALL SELECT 'reached a reward screen',   4, CAST(count(DISTINCT run_id) AS INTEGER) FROM run_pulse WHERE state IN ('chooser', 'talents')
UNION ALL SELECT 'entered a second stage',    5, CAST(count(DISTINCT run_id) AS INTEGER) FROM run_pulse WHERE state = 'stage_intro'
UNION ALL SELECT 'won',                       6, CAST(count(DISTINCT run_id) AS INTEGER) FROM run_pulse WHERE state = 'win'
ORDER BY step_seq;

-- Combat profile per character from the event ring, normalised by seconds with
-- the clock running. kills counts events, not the HUD counter, which is the
-- rule kill_reconciliation exists to justify.
CREATE OR REPLACE VIEW character_combat AS
WITH agg AS (
    SELECT character_key,
           CAST(sum(message IN ('WEAPON_FIRED', 'ICE_BOLT_FIRED')) AS INTEGER) AS shots,
           CAST(sum(message = 'ARROW_MISS')                        AS INTEGER) AS misses,
           CAST(sum(message IN ('CROW_KILLED', 'SKELETON_KILLED'))  AS INTEGER) AS kills,
           CAST(sum(message = 'PLAYER_HIT')                        AS INTEGER) AS hits_taken,
           CAST(sum(message = 'PICKUP_TAKEN')                      AS INTEGER) AS pickups,
           CAST(sum(message = 'BOSS_HIT')                          AS INTEGER) AS boss_hits
    FROM run_events
    GROUP BY character_key
),
sim AS (
    SELECT character_key,
           sum(sim_active_s)          AS sim_s,
           CAST(count(*) AS INTEGER)  AS runs
    FROM fact_run
    GROUP BY character_key
)
SELECT a.character_key,
       s.runs,
       s.sim_s,
       a.shots,
       a.misses,
       a.kills,
       round(a.kills / nullif(a.shots, 0), 2)     AS kills_per_shot,
       round(a.kills * 60.0 / s.sim_s, 1)         AS kills_per_min,
       a.hits_taken,
       round(a.hits_taken * 60.0 / s.sim_s, 2)    AS hits_taken_per_min,
       a.pickups,
       a.boss_hits
FROM agg a
JOIN sim s USING (character_key)
ORDER BY a.character_key;
