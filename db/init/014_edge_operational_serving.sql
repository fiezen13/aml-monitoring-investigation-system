-- Currency-native serving rollups for the active HI-Medium edge release.

CREATE TABLE IF NOT EXISTS edge_country_hub (
    release_id    TEXT NOT NULL REFERENCES edge_model_release (release_id) ON DELETE CASCADE,
    country_code  CHAR(2) NOT NULL REFERENCES country_geo (country_code) ON DELETE RESTRICT,
    entities      BIGINT NOT NULL CHECK (entities >= 0),
    inbound       BIGINT NOT NULL CHECK (inbound >= 0),
    outbound      BIGINT NOT NULL CHECK (outbound >= 0),
    alerts        BIGINT NOT NULL CHECK (alerts >= 0),
    risk_score    NUMERIC(5,2) NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
    refreshed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (release_id, country_code)
);

CREATE TABLE IF NOT EXISTS edge_country_flow (
    release_id            TEXT NOT NULL REFERENCES edge_model_release (release_id) ON DELETE CASCADE,
    source_country_code   CHAR(2) NOT NULL REFERENCES country_geo (country_code) ON DELETE RESTRICT,
    target_country_code   CHAR(2) NOT NULL REFERENCES country_geo (country_code) ON DELETE RESTRICT,
    currency              TEXT NOT NULL,
    channel               TEXT NOT NULL,
    txn_count             BIGINT NOT NULL CHECK (txn_count > 0),
    amount_native         NUMERIC(38,18) NOT NULL CHECK (amount_native > 0),
    first_seen            TIMESTAMPTZ NOT NULL,
    last_seen             TIMESTAMPTZ NOT NULL,
    alert_count           BIGINT NOT NULL CHECK (alert_count >= 0),
    risk_score            NUMERIC(5,2) NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
    refreshed_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (
        release_id, source_country_code, target_country_code, currency, channel
    ),
    CHECK (source_country_code <> target_country_code),
    CHECK (last_seen >= first_seen)
);

CREATE INDEX IF NOT EXISTS edge_country_flow_release_priority_idx
    ON edge_country_flow (release_id, alert_count DESC, txn_count DESC);

COMMENT ON TABLE edge_country_flow IS
    'Cross-border HI-Medium rollup. amount_native is only summed within one currency; it is not USD.';
