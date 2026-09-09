-- Typed layer: the relational model the playbook documents, plus the contract.
--
-- Two ideas carry this layer.
--
-- 1. A session file is not a page load. The sink writes one file per dev server
--    run, and a single file holds every page load that happened during it. The
--    fixtures hold 16 hello records across 3 files. Event ids restart at 1 on
--    every page load, so the file name alone cannot key anything. page_load_seq
--    segments the file on hello; client_id prefers the recorder own cid when
--    the wire format carries it.
--
-- 2. Nothing is dropped. A row that violates the contract is written to
--    quarantine with a reason and excluded from the clean relations, so the
--    counts always reconcile: clean + quarantined = landed.

CREATE OR REPLACE VIEW raw AS
SELECT * FROM read_parquet('warehouse/raw/**/*.parquet', hive_partitioning = true);

-- Reference dimensions, the second source. Documented domain, not observed values.
CREATE OR REPLACE VIEW ref_states AS SELECT * FROM read_csv('fixtures/reference/app_states.csv');
CREATE OR REPLACE VIEW ref_modes  AS SELECT * FROM read_csv('fixtures/reference/modes.csv');
CREATE OR REPLACE VIEW ref_chars  AS SELECT * FROM read_csv('fixtures/reference/characters.csv');
CREATE OR REPLACE VIEW ref_bosses AS SELECT * FROM read_csv('fixtures/reference/boss_kinds.csv');

-- Contract caps, materialized as a table rather than session variables.
--
-- Session variables do not survive across connections, so a later layer opening
-- its own connection would silently read NULL and every cap check would pass.
-- As a table the contract is durable, queryable, and joinable, which is what
-- governance as code should mean in practice.
--
-- Mirrored from contracts/flight_log.yml, which is the source of truth.
-- tests/test_contract.py asserts these agree.
CREATE OR REPLACE TABLE contract_caps (name VARCHAR, value BIGINT);
INSERT INTO contract_caps VALUES
    ('events_per_beat', 400),
    ('events_per_bye',  100),
    ('trace_frames',    120);

CREATE OR REPLACE MACRO cap(n) AS (SELECT value FROM contract_caps WHERE name = n);

CREATE OR REPLACE VIEW landed AS
SELECT
    *,
    -- INTEGER, not the HUGEINT a window sum returns by default. A HUGEINT lands
    -- as DOUBLE in Parquet, so every consumer downstream has to cast it back.
    CAST(sum(CASE WHEN kind = 'hello' THEN 1 ELSE 0 END)
        OVER (PARTITION BY session_id ORDER BY srv ROWS UNBOUNDED PRECEDING) AS INTEGER)
        AS page_load_seq,
    coalesce(cid, session_id || '#' || CAST(
        sum(CASE WHEN kind = 'hello' THEN 1 ELSE 0 END)
            OVER (PARTITION BY session_id ORDER BY srv ROWS UNBOUNDED PRECEDING) AS VARCHAR))
        AS client_id,
    cid IS NOT NULL AS has_native_client_id
FROM raw;

--------------------------------------------------------------------------------
-- Quarantine. Built before the clean relations, because they are defined as
-- everything that is not in here.
--------------------------------------------------------------------------------
CREATE OR REPLACE TABLE quarantine AS
-- A record that arrives before the first hello of its file. The page was
-- already open when the dev server restarted, so its goodbye landed in a file
-- that never saw it say hello.
SELECT 'landed' AS relation, session_id, page_load_seq, srv, kind,
       'orphan_record_no_hello' AS reason,
       'record precedes the first hello in its session file' AS detail
FROM landed WHERE page_load_seq = 0
UNION ALL
SELECT 'pulses', session_id, page_load_seq, srv, kind, 'state_not_in_contract',
       'state=' || coalesce(pulse.state, '<null>')
FROM landed
WHERE pulse IS NOT NULL AND pulse.state NOT IN (SELECT state FROM ref_states)
UNION ALL
SELECT 'pulses', session_id, page_load_seq, srv, kind, 'mode_not_in_contract',
       'mode=' || coalesce(pulse.mode, '<null>')
FROM landed
WHERE pulse IS NOT NULL AND pulse.mode NOT IN (SELECT mode FROM ref_modes)
UNION ALL
SELECT 'pulses', session_id, page_load_seq, srv, kind, 'char_not_in_contract',
       'char=' || coalesce(pulse."char", '<null>')
FROM landed
WHERE pulse IS NOT NULL AND pulse."char" NOT IN (SELECT "char" FROM ref_chars)
UNION ALL
SELECT 'pulses', session_id, page_load_seq, srv, kind, 'boss_not_in_contract',
       'boss=' || pulse.boss
FROM landed
WHERE pulse IS NOT NULL AND pulse.boss IS NOT NULL
  AND pulse.boss NOT IN (SELECT boss FROM ref_bosses)
UNION ALL
SELECT 'alarms', session_id, page_load_seq, srv, kind, 'alarm_class_not_in_contract',
       'class=' || coalesce(class, '<null>')
FROM landed
WHERE kind = 'alarm' AND class NOT IN ('loop-dead', 'logic-freeze', 'no-frames')
UNION ALL
SELECT 'beats', session_id, page_load_seq, srv, kind, 'events_per_beat_over_cap',
       'events=' || CAST(len(events) AS VARCHAR)
FROM landed
WHERE kind = 'beat' AND len(events) > cap('events_per_beat')
UNION ALL
SELECT 'sessions', session_id, page_load_seq, srv, kind, 'events_per_bye_over_cap',
       'events=' || CAST(len(events) AS VARCHAR)
FROM landed
WHERE kind = 'bye' AND len(events) > cap('events_per_bye')
UNION ALL
SELECT 'spans', session_id, page_load_seq, srv, kind, 'trace_frames_over_cap',
       'frames=' || CAST(trace.frames AS VARCHAR)
FROM landed
WHERE trace IS NOT NULL AND trace.frames > cap('trace_frames')
UNION ALL
SELECT 'landed', session_id, page_load_seq, srv, kind, 'srv_missing', 'srv IS NULL'
FROM landed WHERE srv IS NULL;

-- Everything downstream reads this, never landed directly.
CREATE OR REPLACE VIEW clean AS
SELECT * FROM landed
WHERE page_load_seq > 0 AND srv IS NOT NULL;

--------------------------------------------------------------------------------
-- The documented relations.
--------------------------------------------------------------------------------

-- One row per page load, not per file.
CREATE OR REPLACE TABLE sessions AS
WITH hello AS (
    SELECT session_id, session_date, page_load_seq, client_id, has_native_client_id,
           srv AS hello_srv, wall AS hello_wall, href, ua, dpr
    FROM clean WHERE kind = 'hello'
),
farewell AS (
    SELECT session_id, page_load_seq, min(srv) AS bye_srv, count(*) AS bye_count
    FROM clean WHERE kind = 'bye' GROUP BY ALL
),
activity AS (
    SELECT session_id, page_load_seq,
           max(srv) AS last_srv,
           count(*) FILTER (kind = 'beat')  AS beats,
           count(*) FILTER (kind = 'alarm') AS alarms,
           count(*) FILTER (kind = 'err')   AS errors
    FROM clean GROUP BY ALL
)
SELECT h.*,
       f.bye_srv,
       a.last_srv, a.beats, a.alarms, a.errors,
       f.bye_srv IS NOT NULL                                    AS ended_cleanly,
       (coalesce(f.bye_srv, a.last_srv) - h.hello_srv) / 1000.0 AS duration_s
FROM hello h
LEFT JOIN farewell f USING (session_id, page_load_seq)
LEFT JOIN activity a USING (session_id, page_load_seq);

CREATE OR REPLACE TABLE beats AS
SELECT session_id, session_date, page_load_seq, client_id,
       srv, wall, perf, raf, vis, len(events) AS event_count
FROM clean WHERE kind = 'beat';

-- pulse rides on both beat and alarm.
CREATE OR REPLACE TABLE pulses AS
SELECT session_id, page_load_seq, client_id, srv, kind,
       pulse.state, pulse.mode, pulse."char", pulse."map",
       pulse.t, pulse.lastTs, pulse.live, pulse.held, pulse.hp, pulse.kills,
       pulse.crows, pulse.skels, pulse.soldiers, pulse.arrows, pulse.boss
FROM clean WHERE pulse IS NOT NULL;

-- The LogEvent ring, drained. Event id is unique per page load, not per file.
CREATE OR REPLACE TABLE events AS
SELECT session_id, page_load_seq, client_id, drained_srv, drained_by,
       e.id, e.level, e."timestamp", e.source, e.message, e.code
FROM (
    SELECT session_id, page_load_seq, client_id, srv AS drained_srv, kind AS drained_by,
           unnest(events) AS e
    FROM clean WHERE events IS NOT NULL AND len(events) > 0
);

CREATE OR REPLACE TABLE alarms AS
SELECT session_id, page_load_seq, client_id, srv, wall, perf, class,
       trace.level AS trace_level, trace.frames AS trace_frames
FROM clean WHERE kind = 'alarm';

CREATE OR REPLACE TABLE blockers AS
SELECT session_id, page_load_seq, client_id, srv, class,
       blockers.frozen, blockers.charging, blockers.dashing, blockers.buried,
       blockers.snipeKeyHeld, blockers.snipeKeyName,
       len(blockers.heldKeys) AS held_key_count,
       blockers.x, blockers.y
FROM clean WHERE blockers IS NOT NULL;

CREATE OR REPLACE TABLE errors AS
SELECT session_id, page_load_seq, client_id, srv, wall, msg, stack,
       regexp_extract(stack, 'at ([A-Za-z0-9_.$]+) \(', 1)                    AS top_frame,
       regexp_extract(stack, '([A-Za-z0-9_.-]+\.(?:ts|js):\d+:\d+)', 1)       AS top_location
FROM clean WHERE kind = 'err';

--------------------------------------------------------------------------------
-- Frame spans, from two places.
--
-- alarm records carry trace.spans as a typed struct, but there are only four
-- alarms in the whole fixture set, far too few for a percentile. The recorder
-- also writes a trace summary into the log ring roughly once a second, and that
-- summary survives in the beat drain as formatted text. Parsing it is what makes
-- a real distribution possible: 663 summaries, six sections each.
--------------------------------------------------------------------------------
CREATE OR REPLACE TABLE spans AS
SELECT session_id, page_load_seq, client_id, srv, 'alarm_trace' AS origin,
       s.name AS span, s.ms, s.ms_max, frames
FROM (
    SELECT session_id, page_load_seq, client_id, srv, trace.frames AS frames,
           unnest([
               {'name': 'sim',      'ms': trace.spans.sim.ms,      'ms_max': trace.spans.sim.msMax},
               {'name': 'tiles',    'ms': trace.spans.tiles.ms,    'ms_max': trace.spans.tiles.msMax},
               {'name': 'fog',      'ms': trace.spans.fog.ms,      'ms_max': trace.spans.fog.msMax},
               {'name': 'bodies',   'ms': trace.spans.bodies.ms,   'ms_max': trace.spans.bodies.msMax},
               {'name': 'vignette', 'ms': trace.spans.vignette.ms, 'ms_max': trace.spans.vignette.msMax},
               {'name': 'hud',      'ms': trace.spans.hud.ms,      'ms_max': trace.spans.hud.msMax}
           ]) AS s
    FROM clean WHERE trace IS NOT NULL
)
UNION ALL
SELECT session_id, page_load_seq, client_id, srv, 'beat_trace' AS origin,
       p.span, CAST(p.ms AS DOUBLE), CAST(p.ms_max AS DOUBLE), frames
FROM (
    SELECT session_id, page_load_seq, client_id, srv, frames,
           regexp_extract(
               row_text,
               '^(\w+)\s+([0-9.]+)ms\s+max\s+([0-9.]+)\s+(\d+) fill\s+(\d+) img\s+([0-9.]+)Mpx',
               ['span', 'ms', 'ms_max', 'fill', 'img', 'mpx']
           ) AS p
    FROM (
        SELECT session_id, page_load_seq, client_id, srv,
               CAST(regexp_extract(message, '^(\d+) frames', 1) AS INTEGER) AS frames,
               unnest(from_json(row_json, '["VARCHAR"]')) AS row_text
        FROM (
            SELECT session_id, page_load_seq, client_id, srv,
                   e.message AS message, e.data['rows'] AS row_json
            FROM (
                SELECT session_id, page_load_seq, client_id, srv, unnest(events) AS e
                FROM clean WHERE events IS NOT NULL AND len(events) > 0
            )
            WHERE e.source = 'trace' AND e.data['rows'] IS NOT NULL
        )
    )
)
WHERE p.span <> '';

--------------------------------------------------------------------------------
-- Reconciliation, so the counts are visible rather than claimed.
--------------------------------------------------------------------------------
CREATE OR REPLACE VIEW contract_reconciliation AS
SELECT (SELECT count(*) FROM landed)                               AS landed_records,
       (SELECT count(*) FROM clean)                                AS clean_records,
       (SELECT count(*) FROM quarantine WHERE relation = 'landed') AS quarantined_records,
       (SELECT count(*) FROM quarantine)                           AS quarantine_rows_all,
       (SELECT count(*) FROM clean) + (SELECT count(*) FROM quarantine WHERE relation = 'landed')
         = (SELECT count(*) FROM landed)                           AS reconciles;

--------------------------------------------------------------------------------
-- Warehouse manifest, so a reader can tell fresh data from a fresh build.
--
-- A site can always report when it was built. Without this, it cannot report
-- when the data last arrived, and a stale warehouse behind a new build looks
-- current. srv is the server receive time, the only clock the page cannot write.
--
-- sessions counts page loads, not files, which is the grain session_summary
-- uses. Two grains on one site would print two different session counts.
--------------------------------------------------------------------------------
CREATE OR REPLACE VIEW warehouse_manifest AS
SELECT count(*)                                           AS records,
       count(DISTINCT session_id || '#' || page_load_seq) AS sessions,
       min(srv)                                           AS first_srv,
       max(srv)                                           AS last_srv
FROM clean;
