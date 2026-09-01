-- FIN-07 Behaviour supports only the reviewed 1d and 7d model windows.
-- Fail closed if an older environment contains 14d rows: silently deleting
-- model provenance would break auditability.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM behavior_batch WHERE feature_window = '14d') THEN
        RAISE EXCEPTION 'Cannot remove Behaviour 14d contract: behavior_batch contains 14d rows';
    END IF;
    IF EXISTS (SELECT 1 FROM behavior_feature_snapshot WHERE feature_window = '14d') THEN
        RAISE EXCEPTION 'Cannot remove Behaviour 14d contract: behavior_feature_snapshot contains 14d rows';
    END IF;
END
$$;

ALTER TABLE behavior_batch
    DROP CONSTRAINT IF EXISTS behavior_batch_feature_window_check;
ALTER TABLE behavior_batch
    ADD CONSTRAINT behavior_batch_feature_window_check
    CHECK (feature_window IN ('1d', '7d'));

ALTER TABLE behavior_feature_snapshot
    DROP CONSTRAINT IF EXISTS behavior_feature_snapshot_feature_window_check;
ALTER TABLE behavior_feature_snapshot
    ADD CONSTRAINT behavior_feature_snapshot_feature_window_check
    CHECK (feature_window IN ('1d', '7d'));
