-- Pre-aggregated serving layer for the LI-Small World Monitor.  The raw
-- transaction ledger stays canonical; these rows are rebuilt after bank
-- geography is loaded so the UI never aggregates millions of transactions
-- on a request path.

CREATE TABLE operational_country_hub (
    batch_id      TEXT          NOT NULL REFERENCES behavior_batch (batch_id) ON DELETE CASCADE,
    country_code  CHAR(2)       NOT NULL REFERENCES country_geo (country_code) ON DELETE RESTRICT,
    entities      BIGINT        NOT NULL CHECK (entities >= 0),
    inbound       BIGINT        NOT NULL CHECK (inbound >= 0),
    outbound      BIGINT        NOT NULL CHECK (outbound >= 0),
    volume_usd    NUMERIC(30, 2) NOT NULL CHECK (volume_usd >= 0),
    alerts        BIGINT        NOT NULL CHECK (alerts >= 0),
    risk_score    NUMERIC(5, 2) NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
    refreshed_at  TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (batch_id, country_code)
);

CREATE TABLE operational_country_flow (
    batch_id            TEXT           NOT NULL REFERENCES behavior_batch (batch_id) ON DELETE CASCADE,
    source_country_code CHAR(2)        NOT NULL REFERENCES country_geo (country_code) ON DELETE RESTRICT,
    target_country_code CHAR(2)        NOT NULL REFERENCES country_geo (country_code) ON DELETE RESTRICT,
    currency            CHAR(3)        NOT NULL,
    channel             TEXT           NOT NULL,
    txn_count           BIGINT         NOT NULL CHECK (txn_count > 0),
    volume_usd          NUMERIC(30, 2) NOT NULL CHECK (volume_usd >= 0),
    first_seen          TIMESTAMPTZ    NOT NULL,
    last_seen           TIMESTAMPTZ    NOT NULL,
    alert_count         BIGINT         NOT NULL CHECK (alert_count >= 0),
    risk_score          NUMERIC(5, 2)  NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
    refreshed_at        TIMESTAMPTZ    NOT NULL DEFAULT now(),
    PRIMARY KEY (batch_id, source_country_code, target_country_code, currency),
    CHECK (source_country_code <> target_country_code),
    CHECK (last_seen >= first_seen)
);

CREATE INDEX operational_country_flow_batch_count_idx
    ON operational_country_flow (batch_id, txn_count DESC);

COMMENT ON TABLE operational_country_hub IS
    'Rebuildable World Monitor serving rollup; source of truth remains transaction/account/bank.';
COMMENT ON TABLE operational_country_flow IS
    'Rebuildable cross-border corridor rollup for the latest completed Behaviour batch.';
