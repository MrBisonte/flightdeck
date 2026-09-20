-- Publish the curated layer as Parquet.
--
-- The load step reads these files, not the DuckDB database. That is deliberate:
-- the same open files feed PostgreSQL, the PostHog exporter, and a Snowflake
-- COPY INTO, with no engine in the middle claiming ownership of the data.

-- The publish decision on the origin, and the only place it is taken.
--
-- This directory is the public boundary. Everything to the left of it sits on
-- one disk, so the typed layer holds the origin a session really came from.
-- Here the reference decides: an origin publishes only when origins.csv says
-- it may. origin_kind and origin_may_publish always publish, because a class
-- names no host and the decision is evidence a reader can check.
--
-- REPLACE rather than a column list. Listing the other sixteen columns here
-- would be a second copy of session_summary, and a copy drifts.
COPY (SELECT * REPLACE (CASE WHEN origin_may_publish THEN origin END AS origin)
        FROM session_summary)           TO 'warehouse/curated/session_summary.parquet'    (FORMAT PARQUET, COMPRESSION ZSTD);
-- sessions is the page load grain session_summary aggregates, published so a
-- reader can check the origin join clock_skew rests on. It takes the same
-- origin decision as the line above, and it drops href: the full URL is the
-- thing that decision exists to gate, and no published relation has ever
-- carried it.
COPY (SELECT * EXCLUDE (href)
             REPLACE (CASE WHEN origin_may_publish THEN origin END AS origin)
        FROM sessions)                  TO 'warehouse/curated/sessions.parquet'            (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM frame_time_by_span) TO 'warehouse/curated/frame_time_by_span.parquet' (FORMAT PARQUET, COMPRESSION ZSTD);
-- spans is the per sample detail behind frame_time_by_span, from the typed
-- layer. Published so a reader can see the distribution, not only p50 and p95.
COPY (SELECT * FROM spans)              TO 'warehouse/curated/spans.parquet'              (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM alarms_by_class)    TO 'warehouse/curated/alarms_by_class.parquet'    (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM clock_skew)         TO 'warehouse/curated/clock_skew.parquet'         (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM srv_gaps)           TO 'warehouse/curated/srv_gaps.parquet'           (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM gap_explained)      TO 'warehouse/curated/gap_explained.parquet'      (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM loss_accounting)    TO 'warehouse/curated/loss_accounting.parquet'    (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM dimension_coverage) TO 'warehouse/curated/dimension_coverage.parquet' (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM error_report)       TO 'warehouse/curated/error_report.parquet'       (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM session_context)    TO 'warehouse/curated/session_context.parquet'    (FORMAT PARQUET, COMPRESSION ZSTD);

-- Quarantine ships with the curated layer on purpose. A consumer that reads the
-- clean data without being able to see what was held back has no way to judge
-- how complete it is.
COPY (SELECT * FROM quarantine)         TO 'warehouse/curated/quarantine.parquet'         (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM incident_timeline)  TO 'warehouse/curated/incident_timeline.parquet'  (FORMAT PARQUET, COMPRESSION ZSTD);

-- Metadata about the warehouse itself, not analytics over it. The site reads
-- only this directory, so a number it must show has to be published here first.
-- Reconciliation proves clean + quarantined = landed. The manifest says when
-- the data last arrived.
COPY (SELECT * FROM contract_reconciliation) TO 'warehouse/curated/contract_reconciliation.parquet' (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM warehouse_manifest)      TO 'warehouse/curated/warehouse_manifest.parquet'      (FORMAT PARQUET, COMPRESSION ZSTD);

-- Gold. The game domain at the run grain, plus the four metric views the site
-- reads. fact_run and fact_boss_encounter ship too, so a reader can recompute
-- every metric above them rather than take the view on trust.
COPY (SELECT * FROM fact_run)                TO 'warehouse/curated/fact_run.parquet'                (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM fact_boss_encounter)     TO 'warehouse/curated/fact_boss_encounter.parquet'     (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM game_summary)            TO 'warehouse/curated/game_summary.parquet'            (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM character_usage)         TO 'warehouse/curated/character_usage.parquet'         (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM boss_encounters_by_kind) TO 'warehouse/curated/boss_encounters_by_kind.parquet' (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM run_outcomes)            TO 'warehouse/curated/run_outcomes.parquet'            (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM contract_cap_history)    TO 'warehouse/curated/contract_cap_history.parquet'    (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM reference_history)       TO 'warehouse/curated/reference_history.parquet'       (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM reference_governance)    TO 'warehouse/curated/reference_governance.parquet'    (FORMAT PARQUET, COMPRESSION ZSTD);

-- Player-facing gold. run_pulse ships whole: it is the second grain replay the
-- Players page draws, and 897 rows is small enough to send. run_kill_events
-- ships so a reader can rebuild every burst and streak below it rather than
-- take the grouping on trust.
COPY (SELECT * FROM run_pulse)               TO 'warehouse/curated/run_pulse.parquet'               (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM run_scorecard)           TO 'warehouse/curated/run_scorecard.parquet'           (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM run_kill_events)         TO 'warehouse/curated/run_kill_events.parquet'         (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM kill_bursts)             TO 'warehouse/curated/kill_bursts.parquet'             (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM kill_streaks)            TO 'warehouse/curated/kill_streaks.parquet'            (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM kill_reconciliation)     TO 'warehouse/curated/kill_reconciliation.parquet'     (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM run_funnel)              TO 'warehouse/curated/run_funnel.parquet'              (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM character_combat)        TO 'warehouse/curated/character_combat.parquet'        (FORMAT PARQUET, COMPRESSION ZSTD);
