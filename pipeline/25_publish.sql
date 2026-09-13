-- Publish the curated layer as Parquet.
--
-- The load step reads these files, not the DuckDB database. That is deliberate:
-- the same open files feed PostgreSQL, the PostHog exporter, and a Snowflake
-- COPY INTO, with no engine in the middle claiming ownership of the data.

COPY (SELECT * FROM session_summary)    TO 'warehouse/curated/session_summary.parquet'    (FORMAT PARQUET, COMPRESSION ZSTD);
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
