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
    -- cid is text, always, whatever it looks like.
    --
    -- crypto.randomUUID gives a value the JSON reader infers as UUID. The
    -- recorder's fallback id, used where the context is not secure, is a plain
    -- string. Without this cast the two produce Parquet partitions with
    -- different types for the same column, and a read across them fails.
    CAST(cid AS VARCHAR)                                         AS cid,
    * EXCLUDE (filename, cid)
FROM (
        SELECT * FROM read_json(
            getvariable('raw_glob'),
            format = 'newline_delimited',
            union_by_name = true,
            filename = true,
            maximum_object_size = 20000000
        )
        -- A stable schema, whatever the source happened to contain.
        --
        -- Two problems, one fix. A log with no alarm and no error carries no
        -- class, blockers, trace, msg or stack column at all, and the typed
        -- layer would fail to bind against a perfectly healthy session. And a
        -- log recorded before the recorder minted a per page client id has no
        -- cid column.
        --
        -- contracts/wire_schema.jsonl holds one fully populated record of every
        -- kind. Reading zero rows from it and unioning by name materializes
        -- every documented column, typed, whether or not this particular source
        -- exercised it. Columns the source does carry are untouched, and a
        -- field the schema does not know about is still admitted, because
        -- union_by_name adds it rather than dropping it.
        UNION ALL BY NAME
        SELECT *, NULL::VARCHAR AS filename
        FROM read_json('contracts/wire_schema.jsonl',
                       format = 'newline_delimited', union_by_name = true)
        WHERE false
     );

COPY (
    SELECT * FROM raw_landed ORDER BY session_id, srv
)
TO 'warehouse/raw'
    (FORMAT PARQUET,
     PARTITION_BY (session_date, session_id),
     OVERWRITE_OR_IGNORE,
     COMPRESSION ZSTD);
