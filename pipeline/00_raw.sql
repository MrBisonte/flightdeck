-- Raw layer: land the flight logs as Hive partitioned Parquet, unaltered.
--
-- Nothing is cleaned, filtered or reshaped here. The only additions are the
-- partition keys, both derived from srv.
--
-- Why srv. The log carries four clocks. wall, perf and the event timestamps are
-- all written by the page, so a stalled, throttled or clock-skewed browser
-- reports whatever it believes. srv is stamped by the dev server on arrival and
-- is the one clock the page cannot influence. It is therefore the partition key
-- and the ordering key, the same reason a warehouse orders on ingestion time
-- rather than on a timestamp supplied by the client.

CREATE OR REPLACE VIEW raw_landed AS
SELECT
    -- Session identity comes from the file the sink wrote, which is one file
    -- per dev server run. regexp_extract is anchored on the sink's own naming.
    regexp_extract(filename, 'session-([0-9TZ:.-]+)\.jsonl$', 1) AS session_id,
    CAST(to_timestamp(srv / 1000.0) AS DATE)                     AS session_date,
    * EXCLUDE (filename)
FROM (
        SELECT * FROM read_json(
            getvariable('raw_glob'),
            format = 'newline_delimited',
            union_by_name = true,
            filename = true,
            maximum_object_size = 20000000
        )
        -- Forward compatibility across wire format generations. The recorder
        -- gained a per page client id (cid) after these sessions were recorded.
        -- Unioning a zero-row template by name materializes the column as NULL
        -- when the source predates it, and leaves it untouched when the source
        -- carries it. The typed layer then handles both generations with one
        -- coalesce instead of two code paths.
        UNION ALL BY NAME
        SELECT NULL::VARCHAR AS cid, NULL::VARCHAR AS filename WHERE false
     );

COPY (
    SELECT * FROM raw_landed ORDER BY session_id, srv
)
TO 'warehouse/raw'
    (FORMAT PARQUET,
     PARTITION_BY (session_date, session_id),
     OVERWRITE_OR_IGNORE,
     COMPRESSION ZSTD);
