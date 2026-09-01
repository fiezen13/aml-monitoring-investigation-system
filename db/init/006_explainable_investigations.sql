-- Explainable Multi-Agent AML Investigation runtime.
-- Existing alert/case/evidence/audit concepts stay authoritative; these
-- tables persist workflow state and append-only agent execution records.

CREATE TABLE investigation (
    investigation_id TEXT PRIMARY KEY,
    alert_id          TEXT NOT NULL REFERENCES alert(alert_id) ON DELETE RESTRICT,
    case_id           TEXT NOT NULL REFERENCES aml_case(case_id) ON DELETE RESTRICT,
    account_key       TEXT NOT NULL REFERENCES account(account_key) ON DELETE RESTRICT,
    status            TEXT NOT NULL CHECK (status IN (
                          'QUEUED', 'INVESTIGATING', 'COMPLETED',
                          'INSUFFICIENT_EVIDENCE', 'NEEDS_HUMAN_REVIEW', 'FAILED')),
    workflow_state    TEXT NOT NULL CHECK (workflow_state IN (
                          'INITIALIZED', 'COLLECTING_EVIDENCE', 'EXPLAINING',
                          'VALIDATING', 'COMPOSING_REPORT', 'COMPLETED', 'FAILED')),
    iteration         INTEGER NOT NULL DEFAULT 0 CHECK (iteration >= 0),
    tool_call_count   INTEGER NOT NULL DEFAULT 0 CHECK (tool_call_count >= 0),
    snapshot_time     TIMESTAMPTZ NOT NULL,
    risk_summary      JSONB NOT NULL DEFAULT '{}'::jsonb,
    accounts_expanded TEXT[] NOT NULL DEFAULT '{}',
    open_questions    JSONB NOT NULL DEFAULT '[]'::jsonb,
    validation        JSONB,
    config_snapshot   JSONB NOT NULL DEFAULT '{}'::jsonb,
    triggered_by      TEXT NOT NULL DEFAULT 'system',
    failure_reason    TEXT,
    human_review      JSONB,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at      TIMESTAMPTZ
);

CREATE INDEX investigation_alert_idx ON investigation(alert_id, created_at DESC);
CREATE INDEX investigation_case_idx ON investigation(case_id, created_at DESC);
CREATE INDEX investigation_status_idx ON investigation(status, updated_at DESC);

CREATE TABLE investigation_evidence (
    investigation_id TEXT NOT NULL REFERENCES investigation(investigation_id) ON DELETE CASCADE,
    evidence_id      TEXT NOT NULL REFERENCES evidence(evidence_id) ON DELETE RESTRICT,
    added_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (investigation_id, evidence_id)
);

CREATE TABLE investigation_agent_run (
    run_id            TEXT PRIMARY KEY,
    investigation_id  TEXT NOT NULL REFERENCES investigation(investigation_id) ON DELETE CASCADE,
    agent_name         TEXT NOT NULL CHECK (agent_name IN (
                           'investigation_supervisor', 'explanation_agent', 'evidence_critic')),
    iteration          INTEGER NOT NULL CHECK (iteration >= 1),
    status             TEXT NOT NULL CHECK (status IN ('RUNNING', 'SUCCEEDED', 'FAILED', 'TIMEOUT')),
    input_summary      JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_summary     JSONB NOT NULL DEFAULT '{}'::jsonb,
    model_provider     TEXT NOT NULL DEFAULT 'deterministic',
    model_name         TEXT NOT NULL DEFAULT 'deterministic-v1',
    started_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at       TIMESTAMPTZ,
    error_type         TEXT
);

CREATE INDEX investigation_agent_run_idx
    ON investigation_agent_run(investigation_id, iteration, started_at);

CREATE TABLE investigation_tool_call (
    tool_call_id       TEXT PRIMARY KEY,
    investigation_id  TEXT NOT NULL REFERENCES investigation(investigation_id) ON DELETE CASCADE,
    run_id             TEXT REFERENCES investigation_agent_run(run_id) ON DELETE SET NULL,
    tool_name          TEXT NOT NULL CHECK (tool_name IN (
                           'GetRiskBreakdown', 'GetAccountBehavior', 'GetTransactions',
                           'GetGraphEvidence', 'GetGraphNeighborhood', 'GetTypology',
                           'GetAnomalyExplanation')),
    arguments          JSONB NOT NULL,
    status             TEXT NOT NULL CHECK (status IN ('SUCCEEDED', 'FAILED', 'TIMEOUT', 'PARTIAL')),
    output_ref         TEXT,
    result_summary     JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at       TIMESTAMPTZ NOT NULL,
    duration_ms        INTEGER NOT NULL CHECK (duration_ms >= 0),
    error_type         TEXT
);

CREATE INDEX investigation_tool_call_idx
    ON investigation_tool_call(investigation_id, started_at);

CREATE TABLE investigation_validation (
    validation_id      TEXT PRIMARY KEY,
    investigation_id  TEXT NOT NULL REFERENCES investigation(investigation_id) ON DELETE CASCADE,
    run_id             TEXT REFERENCES investigation_agent_run(run_id) ON DELETE SET NULL,
    iteration          INTEGER NOT NULL CHECK (iteration >= 1),
    status             TEXT NOT NULL CHECK (status IN ('PASS', 'FAIL')),
    confidence         NUMERIC(4, 3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    result             JSONB NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE case_explanation (
    explanation_id     TEXT PRIMARY KEY,
    investigation_id  TEXT NOT NULL REFERENCES investigation(investigation_id) ON DELETE CASCADE,
    case_id             TEXT NOT NULL REFERENCES aml_case(case_id) ON DELETE RESTRICT,
    version             INTEGER NOT NULL CHECK (version >= 1),
    explanation         JSONB NOT NULL,
    validated           BOOLEAN NOT NULL DEFAULT false,
    requires_human_review BOOLEAN NOT NULL DEFAULT true,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (investigation_id, version)
);

CREATE TABLE investigation_trace (
    trace_id           TEXT PRIMARY KEY,
    investigation_id  TEXT NOT NULL REFERENCES investigation(investigation_id) ON DELETE CASCADE,
    agent              TEXT NOT NULL,
    event_type         TEXT NOT NULL CHECK (event_type IN (
                          'INVESTIGATION_STARTED', 'AGENT_DECISION', 'TOOL_CALL', 'TOOL_RESULT',
                          'EVIDENCE_ADDED', 'EXPLANATION_GENERATED', 'VALIDATION_PASS',
                          'VALIDATION_FAIL', 'INVESTIGATION_COMPLETED', 'INVESTIGATION_FAILED',
                          'HUMAN_REVIEW_REQUIRED')),
    tool               TEXT,
    input_summary      JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_ref         TEXT,
    short_rationale    TEXT NOT NULL DEFAULT '',
    occurred_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX investigation_trace_idx
    ON investigation_trace(investigation_id, occurred_at, trace_id);

-- Agent execution history and explanations are audit artifacts. Corrections
-- are new rows/versions; mutation would destroy replayability.
CREATE TRIGGER investigation_evidence_no_update
    BEFORE UPDATE ON investigation_evidence FOR EACH ROW EXECUTE FUNCTION deny_mutation();
CREATE TRIGGER investigation_evidence_no_delete
    BEFORE DELETE ON investigation_evidence FOR EACH ROW EXECUTE FUNCTION deny_mutation();
CREATE TRIGGER investigation_evidence_no_truncate
    BEFORE TRUNCATE ON investigation_evidence EXECUTE FUNCTION deny_mutation();
CREATE TRIGGER investigation_tool_call_no_update
    BEFORE UPDATE ON investigation_tool_call FOR EACH ROW EXECUTE FUNCTION deny_mutation();
CREATE TRIGGER investigation_tool_call_no_delete
    BEFORE DELETE ON investigation_tool_call FOR EACH ROW EXECUTE FUNCTION deny_mutation();
CREATE TRIGGER investigation_tool_call_no_truncate
    BEFORE TRUNCATE ON investigation_tool_call EXECUTE FUNCTION deny_mutation();
CREATE TRIGGER investigation_validation_no_update
    BEFORE UPDATE ON investigation_validation FOR EACH ROW EXECUTE FUNCTION deny_mutation();
CREATE TRIGGER investigation_validation_no_delete
    BEFORE DELETE ON investigation_validation FOR EACH ROW EXECUTE FUNCTION deny_mutation();
CREATE TRIGGER investigation_validation_no_truncate
    BEFORE TRUNCATE ON investigation_validation EXECUTE FUNCTION deny_mutation();
CREATE TRIGGER case_explanation_no_update
    BEFORE UPDATE ON case_explanation FOR EACH ROW EXECUTE FUNCTION deny_mutation();
CREATE TRIGGER case_explanation_no_delete
    BEFORE DELETE ON case_explanation FOR EACH ROW EXECUTE FUNCTION deny_mutation();
CREATE TRIGGER case_explanation_no_truncate
    BEFORE TRUNCATE ON case_explanation EXECUTE FUNCTION deny_mutation();
CREATE TRIGGER investigation_trace_no_update
    BEFORE UPDATE ON investigation_trace FOR EACH ROW EXECUTE FUNCTION deny_mutation();
CREATE TRIGGER investigation_trace_no_delete
    BEFORE DELETE ON investigation_trace FOR EACH ROW EXECUTE FUNCTION deny_mutation();
CREATE TRIGGER investigation_trace_no_truncate
    BEFORE TRUNCATE ON investigation_trace EXECUTE FUNCTION deny_mutation();

-- Operational audit keeps the high-level lifecycle; detailed payloads stay in
-- investigation_trace and never contain prompts or chain-of-thought.
ALTER TABLE audit_log DROP CONSTRAINT audit_log_event_type_check;
ALTER TABLE audit_log ADD CONSTRAINT audit_log_event_type_check CHECK (event_type IN (
    'agent_query', 'alert_raised', 'case_state_changed', 'submitted_for_approval',
    'approved', 'rejected', 'more_info_requested', 'file_exported', 'case_viewed',
    'user_login', 'setting_changed', 'user_changed', 'sar_updated', 'validation_run',
    'investigation_started', 'investigation_completed', 'investigation_failed',
    'investigation_reviewed'
));
