-- Model artifact provenance for Behaviour batch releases. Existing rows (if
-- any) remain readable with NULL; every run through the current repository
-- writes a SHA-256 and rejects reuse of a model_version with different bytes.

ALTER TABLE behavior_batch
    ADD COLUMN IF NOT EXISTS model_sha256 CHAR(64);

COMMENT ON COLUMN behavior_batch.model_sha256 IS
    'SHA-256 of the exact joblib artifact used for inference; NULL only for legacy rows created before migration 009.';
