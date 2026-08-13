-- Google Gemini execution metadata for explainable AML agents.
-- Prompts and payloads are intentionally excluded; only version/model/usage
-- metadata is retained for audit and cost monitoring.

ALTER TABLE investigation_agent_run
    ADD COLUMN IF NOT EXISTS prompt_version TEXT NOT NULL DEFAULT 'unversioned',
    ADD COLUMN IF NOT EXISTS request_timestamp TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS duration_ms INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
    ADD COLUMN IF NOT EXISTS attempt_count INTEGER CHECK (attempt_count IS NULL OR attempt_count >= 1),
    ADD COLUMN IF NOT EXISTS input_token_count INTEGER CHECK (input_token_count IS NULL OR input_token_count >= 0),
    ADD COLUMN IF NOT EXISTS output_token_count INTEGER CHECK (output_token_count IS NULL OR output_token_count >= 0),
    ADD COLUMN IF NOT EXISTS total_token_count INTEGER CHECK (total_token_count IS NULL OR total_token_count >= 0),
    ADD COLUMN IF NOT EXISTS provider_response_id TEXT;

ALTER TABLE investigation_trace
    ADD COLUMN IF NOT EXISTS model_name TEXT,
    ADD COLUMN IF NOT EXISTS prompt_version TEXT;

ALTER TABLE investigation_trace
    DROP CONSTRAINT IF EXISTS investigation_trace_event_type_check;

ALTER TABLE investigation_trace
    ADD CONSTRAINT investigation_trace_event_type_check CHECK (event_type IN (
        'INVESTIGATION_STARTED', 'AGENT_DECISION', 'TOOL_CALL', 'TOOL_RESULT',
        'EVIDENCE_ADDED', 'EXPLANATION_GENERATED', 'VALIDATION_PASS',
        'VALIDATION_FAIL', 'INVESTIGATION_COMPLETED', 'INVESTIGATION_FAILED',
        'HUMAN_REVIEW_REQUIRED', 'GEMINI_REQUEST', 'GEMINI_RESPONSE',
        'GEMINI_ERROR', 'INVALID_TOOL_REQUEST'
    ));

COMMENT ON COLUMN investigation_agent_run.prompt_version IS
    'Version identifier only; full prompts and hidden reasoning are never persisted.';
COMMENT ON COLUMN investigation_agent_run.provider_response_id IS
    'Opaque Google response identifier for operational correlation; never an API key.';
