-- Publish the curated layer as Parquet.
--
-- The load step reads these files, not the DuckDB database. That is deliberate:
-- the same open files feed PostgreSQL, the PostHog exporter, and a Snowflake
-- COPY INTO, with no engine in the middle claiming ownership of the data.

COPY (SELECT * FROM session_summary)    TO 'warehouse/curated/session_summary.parquet'    (FORMAT PARQUET, COMPRESSION ZSTD);
COPY (SELECT * FROM frame_time_by_span) TO 'warehouse/curated/frame_time_by_span.parquet' (FORMAT PARQUET, COMPRESSION ZSTD);
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
