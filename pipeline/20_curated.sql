-- Curated layer: the questions worth asking of a recorded play session.
--
-- Everything here reads the typed relations, never the raw files.

--------------------------------------------------------------------------------
-- One row per page load. What happened, how long, and how it ended.
--------------------------------------------------------------------------------
CREATE OR REPLACE VIEW session_summary AS
WITH run AS (
    SELECT session_id, page_load_seq,
           max(kills)                                  AS kills,
           min(hp)                                     AS hp_min,
           max(hp)                                     AS hp_max,
           arg_min(hp, srv)                            AS hp_first,
           arg_max(hp, srv)                            AS hp_last,
           arg_max(state, srv)                         AS final_state,
           count(DISTINCT state)                       AS states_visited,
           count(DISTINCT "char")                      AS chars_played
    FROM pulses GROUP BY ALL
)
SELECT s.session_id,
       s.page_load_seq,
       s.client_id,
       s.has_native_client_id,
       s.ua,
       round(s.duration_s, 1)                          AS duration_s,
       s.beats,
       s.alarms,
       s.errors,
       r.kills,
       r.hp_first, r.hp_min, r.hp_last,
       r.final_state,
       r.states_visited,
       CASE
           WHEN s.ended_cleanly AND s.errors = 0 AND s.alarms = 0 THEN 'clean'
           WHEN s.ended_cleanly                                   THEN 'clean bye, with incidents'
           ELSE 'abnormal end, no bye'
       END                                             AS outcome
FROM sessions s
LEFT JOIN run r USING (session_id, page_load_seq)
ORDER BY s.session_id, s.page_load_seq;

--------------------------------------------------------------------------------
-- Frame time per section.
--
-- Percentiles come from the beat_trace origin only. The alarm origin carries
-- structurally cleaner data but there are four alarms in the entire fixture set,
-- and a p95 over four samples is not a p95. The sample count is reported next to
-- the numbers so the reader can judge them.
--------------------------------------------------------------------------------
CREATE OR REPLACE VIEW frame_time_by_span AS
SELECT span,
       count(*)                                          AS samples,
       round(median(ms), 3)                              AS p50_ms,
       round(quantile_cont(ms, 0.95), 3)                 AS p95_ms,
       round(max(ms), 3)                                 AS max_mean_ms,
       round(max(ms_max), 3)                             AS worst_single_frame_ms
FROM spans
WHERE origin = 'beat_trace'
GROUP BY ALL
ORDER BY p95_ms DESC;

--------------------------------------------------------------------------------
-- Alarms by class.
--------------------------------------------------------------------------------
CREATE OR REPLACE VIEW alarms_by_class AS
SELECT a.class,
       count(*)                                          AS n,
       count(DISTINCT a.session_id || '#' || a.page_load_seq) AS page_loads,
       any_value(b.held_key_count)                       AS held_keys_seen,
       list(DISTINCT p.state)                            AS states_when_raised
FROM alarms a
LEFT JOIN blockers b USING (session_id, page_load_seq, srv)
LEFT JOIN pulses   p USING (session_id, page_load_seq, srv)
GROUP BY ALL
ORDER BY n DESC;

--------------------------------------------------------------------------------
-- The four clocks.
--
-- wall, perf and each event timestamp are written by the page. srv is stamped by
-- the server when the record arrives. Comparing them is the only way to tell a
-- page that went quiet from a page that lied about the time.
--------------------------------------------------------------------------------
CREATE OR REPLACE VIEW clock_skew AS
SELECT count(*)                       AS records,
       min(srv - wall)                AS skew_min_ms,
       round(avg(srv - wall), 2)      AS skew_mean_ms,
       max(srv - wall)                AS skew_max_ms,
       round(stddev_pop(srv - wall), 3) AS skew_stddev_ms
FROM clean WHERE wall IS NOT NULL;

-- Consecutive arrivals, on the clock the page cannot influence.
CREATE OR REPLACE VIEW srv_gaps AS
WITH ordered AS (
    SELECT session_id, page_load_seq, srv, kind, vis,
           lag(srv) OVER (PARTITION BY session_id ORDER BY srv) AS prev_srv,
           lag(vis) OVER (PARTITION BY session_id ORDER BY srv) AS prev_vis
    FROM clean
)
SELECT session_id, page_load_seq, prev_srv, srv,
       (srv - prev_srv) / 1000.0 AS gap_s,
       prev_vis, vis
FROM ordered
WHERE prev_srv IS NOT NULL AND srv - prev_srv > 3000;   -- 3x the 1s beat interval

-- Why each gap happened. A hidden tab has its 1s timer clamped by the browser,
-- which is expected. A gap while the tab was visible is not explained by
-- throttling and is the one worth looking at.
CREATE OR REPLACE VIEW gap_explained AS
SELECT CASE
           WHEN prev_vis = 'hidden' AND vis = 'hidden' AND gap_s BETWEEN 30 AND 70
               THEN 'background tab, timer clamped to ~60s'
           WHEN prev_vis = 'hidden' OR vis = 'hidden'
               THEN 'tab hidden, machine likely asleep'
           ELSE 'VISIBLE THROUGHOUT, not explained by throttling'
       END                             AS explanation,
       count(*)                        AS gaps,
       round(min(gap_s), 1)            AS shortest_s,
       round(max(gap_s), 1)            AS longest_s,
       round(sum(gap_s), 1)            AS total_s
FROM srv_gaps
GROUP BY ALL
ORDER BY gaps DESC;

--------------------------------------------------------------------------------
-- Loss accounting.
--
-- The recorder drains a 500 entry ring by watermark and caps each beat at 400
-- events, setting a dropped counter when it has to discard. Two independent
-- checks: the counter the recorder reports, and the gaps in the event id
-- sequence, which the recorder cannot hide because ids are assigned at the
-- source and are contiguous per page load.
--------------------------------------------------------------------------------
CREATE OR REPLACE VIEW loss_accounting AS
WITH per_load AS (
    SELECT session_id, page_load_seq,
           count(*)                      AS events_received,
           count(DISTINCT id)            AS distinct_ids,
           min(id)                       AS first_id,
           max(id)                       AS last_id,
           max(id) - min(id) + 1         AS ids_expected
    FROM events GROUP BY ALL
)
SELECT sum(events_received)                        AS events_received,
       sum(ids_expected)                           AS ids_expected,
       sum(ids_expected) - sum(distinct_ids)       AS events_lost_by_id_gap,
       max(events_per_beat_peak)                   AS peak_events_in_one_beat,
       cap('events_per_beat')          AS cap_events_per_beat,
       round(100.0 * max(events_per_beat_peak) / cap('events_per_beat'), 1)
                                                   AS peak_pct_of_cap
FROM per_load, (SELECT max(event_count) AS events_per_beat_peak FROM beats);

--------------------------------------------------------------------------------
-- Dimension coverage. The join that telemetry alone cannot produce.
--------------------------------------------------------------------------------
CREATE OR REPLACE VIEW dimension_coverage AS
SELECT 'state' AS dimension,
       (SELECT count(*) FROM ref_states)                       AS documented,
       (SELECT count(DISTINCT state) FROM pulses)              AS exercised,
       (SELECT list(state ORDER BY state) FROM ref_states
         WHERE state NOT IN (SELECT DISTINCT state FROM pulses)) AS never_seen
UNION ALL
SELECT 'mode', (SELECT count(*) FROM ref_modes),
       (SELECT count(DISTINCT mode) FROM pulses),
       (SELECT list(mode ORDER BY mode) FROM ref_modes
         WHERE mode NOT IN (SELECT DISTINCT mode FROM pulses))
UNION ALL
SELECT 'char', (SELECT count(*) FROM ref_chars),
       (SELECT count(DISTINCT "char") FROM pulses),
       (SELECT list("char" ORDER BY "char") FROM ref_chars
         WHERE "char" NOT IN (SELECT DISTINCT "char" FROM pulses))
UNION ALL
SELECT 'boss', (SELECT count(*) FROM ref_bosses),
       (SELECT count(DISTINCT boss) FROM pulses WHERE boss IS NOT NULL),
       (SELECT list(boss ORDER BY boss) FROM ref_bosses
         WHERE boss NOT IN (SELECT DISTINCT boss FROM pulses WHERE boss IS NOT NULL));

--------------------------------------------------------------------------------
-- Errors, with the frame that raised them.
--------------------------------------------------------------------------------
CREATE OR REPLACE VIEW error_report AS
SELECT session_id, page_load_seq, to_timestamp(srv / 1000.0) AS arrived,
       msg, top_frame, top_location
FROM errors ORDER BY srv;

--------------------------------------------------------------------------------
-- One compact typed row per page load.
--
-- This is the shape a downstream consumer reads without bespoke glue: the
-- session, its outcome, and its incidents in a single record. Nothing more is
-- claimed for it than that.
--------------------------------------------------------------------------------
CREATE OR REPLACE VIEW session_context AS
SELECT s.client_id,
       s.duration_s,
       s.outcome,
       s.final_state,
       s.kills,
       s.hp_first, s.hp_last,
       s.alarms, s.errors,
       (SELECT list(DISTINCT class) FROM alarms a
         WHERE a.session_id = s.session_id AND a.page_load_seq = s.page_load_seq) AS alarm_classes,
       (SELECT list(msg) FROM errors e
         WHERE e.session_id = s.session_id AND e.page_load_seq = s.page_load_seq) AS error_messages
FROM session_summary s
ORDER BY s.alarms + s.errors DESC, s.duration_s DESC;

--------------------------------------------------------------------------------
-- Incident timeline.
--
-- An uncaught exception and a watchdog alarm are two different record kinds
-- written by two different code paths, so on their own they read as unrelated
-- events. Ordering them on the server clock shows the causal chain: the
-- exception unhooks the frame loop, and the watchdog notices a moment later.
-- That gap, error to alarm, is the recorder's time to detection.
--------------------------------------------------------------------------------
CREATE OR REPLACE VIEW incident_timeline AS
WITH incidents AS (
    SELECT session_id, page_load_seq, srv, 'error' AS event,
           msg AS detail
    FROM clean WHERE kind = 'err'
    UNION ALL
    SELECT session_id, page_load_seq, srv, 'alarm', 'class=' || class
    FROM clean WHERE kind = 'alarm'
)
SELECT session_id,
       page_load_seq,
       to_timestamp(srv / 1000.0) AS occurred_at,
       event,
       detail,
       round((srv - lag(srv) OVER (PARTITION BY session_id ORDER BY srv)) / 1000.0, 3)
           AS s_since_previous
FROM incidents
ORDER BY session_id, srv;
