-- =====================================================================
-- FIN-07 — Behaviour ML batch PoC
--
-- Adds provenance for externally supplied transactions and durable storage
-- for point-in-time feature snapshots + detector results.  The existing
-- BIGSERIAL transaction_id remains the internal FK used by the console;
-- source_transaction_id is the idempotency key from the source system.
-- =====================================================================

CREATE TABLE behavior_batch (
    batch_id             TEXT        PRIMARY KEY,
    source_name          TEXT        NOT NULL,
    source_sha256        CHAR(64)    NOT NULL,
    status               TEXT        NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    feature_window       TEXT        NOT NULL CHECK (feature_window IN ('1d', '7d', '14d')),
    model_version        TEXT        NOT NULL,
    threshold            NUMERIC(7, 6) NOT NULL CHECK (threshold BETWEEN 0 AND 1),
    rows_read            BIGINT      NOT NULL DEFAULT 0 CHECK (rows_read >= 0),
    rows_rejected        BIGINT      NOT NULL DEFAULT 0 CHECK (rows_rejected >= 0),
    transactions_inserted BIGINT     NOT NULL DEFAULT 0 CHECK (transactions_inserted >= 0),
    transactions_existing BIGINT     NOT NULL DEFAULT 0 CHECK (transactions_existing >= 0),
    detections_written   BIGINT      NOT NULL DEFAULT 0 CHECK (detections_written >= 0),
    alerts_created       BIGINT      NOT NULL DEFAULT 0 CHECK (alerts_created >= 0),
    started_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at         TIMESTAMPTZ,
    failure_reason       TEXT,
    UNIQUE (source_sha256, feature_window, model_version)
);

ALTER TABLE transaction
    ADD COLUMN IF NOT EXISTS source_transaction_id TEXT,
    ADD COLUMN IF NOT EXISTS source_dataset TEXT,
    ADD COLUMN IF NOT EXISTS source_file TEXT,
    ADD COLUMN IF NOT EXISTS source_line_number BIGINT,
    ADD COLUMN IF NOT EXISTS ingested_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS behavior_batch_id TEXT REFERENCES behavior_batch (batch_id) ON DELETE SET NULL;

CREATE UNIQUE INDEX IF NOT EXISTS transaction_source_id_uq
    ON transaction (source_transaction_id)
    WHERE source_transaction_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS transaction_behavior_batch_idx
    ON transaction (behavior_batch_id, occurred_at);

CREATE TABLE behavior_feature_snapshot (
    snapshot_id          TEXT        PRIMARY KEY,
    batch_id             TEXT        NOT NULL REFERENCES behavior_batch (batch_id) ON DELETE RESTRICT,
    account_key          TEXT        NOT NULL REFERENCES account (account_key) ON DELETE RESTRICT,
    as_of_time           TIMESTAMPTZ NOT NULL,
    feature_window       TEXT        NOT NULL CHECK (feature_window IN ('1d', '7d', '14d')),
    definition_version   TEXT        NOT NULL,
    model_version        TEXT        NOT NULL,
    features             JSONB       NOT NULL CHECK (jsonb_typeof(features) = 'object'),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_key, as_of_time, feature_window, definition_version, model_version)
);

CREATE INDEX behavior_feature_account_time_idx
    ON behavior_feature_snapshot (account_key, as_of_time DESC);

CREATE TABLE detection_result (
    result_id            TEXT        PRIMARY KEY,
    batch_id             TEXT        NOT NULL REFERENCES behavior_batch (batch_id) ON DELETE RESTRICT,
    snapshot_id          TEXT        NOT NULL REFERENCES behavior_feature_snapshot (snapshot_id) ON DELETE RESTRICT,
    alert_id             TEXT        REFERENCES alert (alert_id) ON DELETE SET NULL,
    account_key          TEXT        NOT NULL REFERENCES account (account_key) ON DELETE RESTRICT,
    detector_id          TEXT        NOT NULL,
    detector_type        TEXT        NOT NULL,
    detector_version     TEXT        NOT NULL,
    evaluated_at         TIMESTAMPTZ NOT NULL,
    as_of_time           TIMESTAMPTZ NOT NULL,
    score                NUMERIC(7, 6) NOT NULL CHECK (score BETWEEN 0 AND 1),
    confidence           NUMERIC(7, 6) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    triggered            BOOLEAN     NOT NULL,
    threshold            NUMERIC(7, 6) NOT NULL CHECK (threshold BETWEEN 0 AND 1),
    reason_codes         JSONB       NOT NULL CHECK (jsonb_typeof(reason_codes) = 'array'),
    typology_candidates  JSONB       NOT NULL CHECK (jsonb_typeof(typology_candidates) = 'array'),
    feature_refs         JSONB       NOT NULL CHECK (jsonb_typeof(feature_refs) = 'array'),
    payload              JSONB       NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX detection_result_queue_idx
    ON detection_result (triggered, score DESC, evaluated_at DESC);

CREATE INDEX detection_result_account_time_idx
    ON detection_result (account_key, as_of_time DESC);

COMMENT ON TABLE behavior_batch IS
    'Auditable run metadata for the local Behaviour ML batch PoC; input data is never copied into source control.';
COMMENT ON COLUMN transaction.source_transaction_id IS
    'Stable identifier supplied by the source system (or deterministically derived by the batch loader).';
COMMENT ON TABLE detection_result IS
    'Every Behaviour detector result, including triggered=false; alert is only the analyst-facing triggered subset.';
