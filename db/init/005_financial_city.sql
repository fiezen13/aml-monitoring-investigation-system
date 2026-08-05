-- =====================================================================
-- FIN-07 — "Thành phố tài chính Việt Nam": lược đồ ABM
--
-- Nguồn: docs/design/ABM-thanh-pho-tai-chinh-v2.0.pdf
--        chương 12 (đặc tả dữ liệu đầu ra), chương 13 (source registry),
--        chương 10 (năm gói kịch bản), phụ lục C và D.
--
-- Nguyên tắc chi phối toàn bộ file này là "hidden world - observable
-- evidence views" ở chương 4: thế giới mô phỏng biết mọi thứ, còn AI Agent
-- chỉ được nhìn phần mà vai trò của nó thực sự quan sát được trong đời thực.
-- Vì vậy dữ liệu chia làm hai schema tách bạch:
--
--   fc      — bằng chứng quan sát được. Model và agent đọc schema này.
--   fc_gt   — ground truth ẩn. CHỈ dùng để chấm điểm, không bao giờ làm
--             đặc trưng đầu vào. Phụ lục D yêu cầu quét rò rỉ theo đúng
--             ranh giới này.
--
-- Tách bằng schema chứ không bằng quy ước đặt tên cột là có lý do: quyền
-- đọc cấp được theo schema, nên "agent không được thấy ground truth" trở
-- thành một ràng buộc của cơ sở dữ liệu chứ không phải một lời hứa trong
-- tài liệu. Xem 003_agent_readonly_role.sh.
-- =====================================================================

SET client_min_messages TO WARNING;

CREATE SCHEMA fc;
CREATE SCHEMA fc_gt;

COMMENT ON SCHEMA fc IS 'Bằng chứng quan sát được theo từng view (bank/FIU/regulator/law-enforcement/public). An toàn để huấn luyện.';
COMMENT ON SCHEMA fc_gt IS 'Hidden ground truth của simulator. CHỈ dùng chấm điểm — mọi cột ở đây bị cấm trong feature store (v2.0 chương 4, phụ lục D).';

-- ---------------------------------------------------------------------
-- 1. Lần chạy mô phỏng và source registry
-- ---------------------------------------------------------------------

-- Mọi bản ghi sinh ra đều trỏ về một lần chạy, để tái lập và so sánh
-- counterfactual (chương 12.2: simulation_id / scenario_run_id).
CREATE TABLE fc.simulation_run (
    simulation_id     TEXT        PRIMARY KEY,
    scenario_package  TEXT        NOT NULL CHECK (scenario_package ~ '^VN-CA-0[1-5]$'),
    -- Cùng seed phải cho ra cùng dữ liệu — điều kiện để kiểm chứng lại kết quả.
    seed              BIGINT      NOT NULL,
    schema_version    TEXT        NOT NULL,
    parameter_set_id  TEXT        NOT NULL,
    generator_version TEXT        NOT NULL,
    world_from        TIMESTAMPTZ NOT NULL,
    world_to          TIMESTAMPTZ NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    notes             TEXT        NOT NULL DEFAULT ''
);

COMMENT ON TABLE fc.simulation_run IS 'Một lần sinh dữ liệu ABM. seed + parameter_set_id + generator_version xác định lại được toàn bộ đầu ra.';

-- Chương 13.1. Mỗi tham số hoặc template phải truy được về nguồn; không có
-- source_id thì tham số đó là giả định chuyên gia và phải ghi rõ như vậy.
CREATE TABLE fc.source_registry (
    source_id       TEXT        PRIMARY KEY,
    source_type     TEXT        NOT NULL CHECK (source_type IN (
                        'official_case', 'legal_text', 'public_blockchain',
                        'partner_aggregate', 'benchmark', 'expert_assumption')),
    scope           TEXT        NOT NULL,
    period          TEXT        NOT NULL,
    jurisdiction    TEXT        NOT NULL,
    fields_supported TEXT       NOT NULL,
    transformation  TEXT        NOT NULL,
    confidence      NUMERIC(3, 2) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    rationale       TEXT        NOT NULL,
    access_level    TEXT        NOT NULL CHECK (access_level IN ('public', 'restricted', 'internal')),
    owner           TEXT        NOT NULL,
    reviewer        TEXT        NOT NULL,
    valid_from      DATE        NOT NULL,
    valid_to        DATE,
    -- Chương 13.1 bắt buộc ghi điều cấm: ví dụ không suy ra tỷ lệ toàn quốc
    -- từ một tập vụ án, không tái nhận dạng cá nhân.
    prohibited_uses TEXT        NOT NULL
);

COMMENT ON COLUMN fc.source_registry.prohibited_uses IS 'Ràng buộc sử dụng bắt buộc công bố (v2.0 chương 13.1). Không để rỗng.';

-- ---------------------------------------------------------------------
-- 2. Thực thể của thế giới mô phỏng
-- ---------------------------------------------------------------------

-- Trung tâm tài chính — đơn vị địa lý của World Monitor. Toạ độ để vẽ cung
-- dòng tiền; không mang ý nghĩa nghiệp vụ nào khác.
CREATE TABLE fc.hub (
    hub_id       TEXT        PRIMARY KEY,
    name         TEXT        NOT NULL,
    country_code CHAR(2)     NOT NULL,
    lat          NUMERIC(6, 3) NOT NULL CHECK (lat BETWEEN -90 AND 90),
    lon          NUMERIC(7, 3) NOT NULL CHECK (lon BETWEEN -180 AND 180),
    -- Rủi ro pháp lý theo phiên bản: nhãn phải có thời điểm hiệu lực, không
    -- được gán cứng (chương 10.2 — "generic VASP với jurisdiction risk version hoá").
    jurisdiction_risk TEXT   NOT NULL CHECK (jurisdiction_risk IN ('low', 'medium', 'high')),
    known_from   DATE        NOT NULL
);

-- Thực thể chung của đồ thị: người, tổ chức, tài khoản, ví, thiết bị, VASP,
-- dự án token, hợp đồng. Một bảng thay vì tám bảng vì mọi màn hình đều truy
-- vấn chúng như các đỉnh cùng loại của một đồ thị.
CREATE TABLE fc.entity (
    entity_id     TEXT        PRIMARY KEY,
    simulation_id TEXT        NOT NULL REFERENCES fc.simulation_run (simulation_id) ON DELETE CASCADE,
    entity_type   TEXT        NOT NULL CHECK (entity_type IN (
                      'person', 'organisation', 'account', 'wallet', 'device',
                      'vasp', 'platform', 'project', 'contract', 'token')),
    label         TEXT        NOT NULL,
    subtitle      TEXT        NOT NULL DEFAULT '',
    hub_id        TEXT        REFERENCES fc.hub (hub_id) ON DELETE SET NULL,
    -- Điểm rủi ro do hệ thống chấm, KHÔNG phải nhãn. Suy từ đặc trưng quan sát được.
    risk_score    SMALLINT    NOT NULL DEFAULT 0 CHECK (risk_score BETWEEN 0 AND 100),
    first_seen    TIMESTAMPTZ NOT NULL,
    last_seen     TIMESTAMPTZ NOT NULL,
    attributes    JSONB       NOT NULL DEFAULT '{}'::jsonb,
    -- Hard negative: thực thể hợp pháp trông giống đối tượng nghi vấn, cố ý
    -- đưa vào để đo tỷ lệ dương tính giả (chương 10.2).
    is_hard_negative BOOLEAN  NOT NULL DEFAULT false,
    access_tier   TEXT        NOT NULL DEFAULT 'BANK' CHECK (access_tier IN (
                      'PUBLIC', 'BANK', 'FIU', 'REGULATOR', 'LAW_ENFORCEMENT')),
    CONSTRAINT entity_seen_order CHECK (last_seen >= first_seen)
);

CREATE INDEX entity_sim_type_idx ON fc.entity (simulation_id, entity_type);
CREATE INDEX entity_hub_idx      ON fc.entity (hub_id);
CREATE INDEX entity_risk_idx     ON fc.entity (risk_score DESC);

COMMENT ON COLUMN fc.entity.risk_score IS 'Điểm do mô hình chấm từ đặc trưng quan sát được. Không bao giờ suy từ fc_gt (ND1).';

-- Quan hệ giữa hai thực thể. `is_inferred` là cột quan trọng nhất: nó phân
-- biệt việc đã quan sát được với việc do mô hình suy ra — đúng câu hỏi đầu
-- tiên trong phụ lục E mà agent phải trả lời được.
CREATE TABLE fc.relationship (
    relationship_id TEXT        PRIMARY KEY,
    simulation_id   TEXT        NOT NULL REFERENCES fc.simulation_run (simulation_id) ON DELETE CASCADE,
    source_id       TEXT        NOT NULL REFERENCES fc.entity (entity_id) ON DELETE CASCADE,
    target_id       TEXT        NOT NULL REFERENCES fc.entity (entity_id) ON DELETE CASCADE,
    kind            TEXT        NOT NULL CHECK (kind IN (
                        'transfer', 'owns', 'device', 'swap', 'bridge', 'control', 'promotes')),
    label           TEXT        NOT NULL DEFAULT '',
    amount_usd      NUMERIC(18, 2),
    is_inferred     BOOLEAN     NOT NULL DEFAULT false,
    confidence      NUMERIC(3, 2) CHECK (confidence BETWEEN 0 AND 1),
    -- Diễn giải vì sao suy ra được quan hệ này. Bắt buộc khi is_inferred.
    inference_logic TEXT,
    known_from      TIMESTAMPTZ NOT NULL,
    valid_to        TIMESTAMPTZ,
    CONSTRAINT relationship_no_self_loop CHECK (source_id <> target_id),
    -- Một cạnh suy luận không có độ tin cậy và diễn giải thì analyst không
    -- thể phản biện nó — chặn ngay ở tầng dữ liệu.
    CONSTRAINT relationship_inferred_needs_reason CHECK (
        NOT is_inferred OR (confidence IS NOT NULL AND inference_logic IS NOT NULL))
);

CREATE INDEX relationship_source_idx ON fc.relationship (source_id);
CREATE INDEX relationship_target_idx ON fc.relationship (target_id);
CREATE INDEX relationship_sim_idx    ON fc.relationship (simulation_id, kind);

-- ---------------------------------------------------------------------
-- 3. Dòng tiền theo hành lang — nguồn dữ liệu của World Monitor
-- ---------------------------------------------------------------------

CREATE TABLE fc.corridor_flow (
    corridor_id     TEXT        PRIMARY KEY,
    simulation_id   TEXT        NOT NULL REFERENCES fc.simulation_run (simulation_id) ON DELETE CASCADE,
    source_hub_id   TEXT        NOT NULL REFERENCES fc.hub (hub_id) ON DELETE RESTRICT,
    target_hub_id   TEXT        NOT NULL REFERENCES fc.hub (hub_id) ON DELETE RESTRICT,
    channel         TEXT        NOT NULL CHECK (channel IN ('bank', 'p2p', 'vasp', 'chain', 'gamb', 'proj')),
    currency        TEXT        NOT NULL,
    volume_usd      NUMERIC(18, 2) NOT NULL CHECK (volume_usd >= 0),
    txn_count       INTEGER     NOT NULL CHECK (txn_count >= 0),
    risk_score      SMALLINT    NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
    -- Nhãn typology ứng viên, không phải kết luận. NULL = chưa khớp typology nào.
    typology_hint   TEXT,
    alert_count     INTEGER     NOT NULL DEFAULT 0 CHECK (alert_count >= 0),
    first_seen      TIMESTAMPTZ NOT NULL,
    last_seen       TIMESTAMPTZ NOT NULL,
    CONSTRAINT corridor_distinct_hubs CHECK (source_hub_id <> target_hub_id)
);

CREATE INDEX corridor_sim_idx  ON fc.corridor_flow (simulation_id, risk_score DESC);

-- ---------------------------------------------------------------------
-- 4. Miền tài sản mã hoá (chương 12.1 gói CRYPTO_DOMAIN)
-- ---------------------------------------------------------------------

CREATE TABLE fc.crypto_transfer (
    transfer_id    TEXT        PRIMARY KEY,
    simulation_id  TEXT        NOT NULL REFERENCES fc.simulation_run (simulation_id) ON DELETE CASCADE,
    chain          TEXT        NOT NULL,
    tx_hash        TEXT        NOT NULL,
    log_index      INTEGER     NOT NULL DEFAULT 0,
    from_address   TEXT        NOT NULL,
    to_address     TEXT        NOT NULL,
    asset          TEXT        NOT NULL,
    amount         NUMERIC(38, 8) NOT NULL CHECK (amount > 0),
    amount_usd     NUMERIC(18, 2) NOT NULL CHECK (amount_usd >= 0),
    block_time     TIMESTAMPTZ NOT NULL,
    -- swap/bridge/mixer là *ứng viên*: on-chain không tự nói nó là gì.
    transfer_kind  TEXT        NOT NULL DEFAULT 'transfer'
                       CHECK (transfer_kind IN ('transfer', 'swap', 'bridge', 'mixer', 'dex')),
    -- Liên kết qua bridge/mixer luôn kèm độ tin cậy. Chương 10.4 nói rõ agent
    -- chỉ được kết luận "mức độ phơi nhiễm", không được tuyên bố đã phá ẩn danh.
    link_confidence NUMERIC(3, 2) CHECK (link_confidence BETWEEN 0 AND 1),
    UNIQUE (chain, tx_hash, log_index)
);

CREATE INDEX crypto_transfer_from_idx ON fc.crypto_transfer (from_address, block_time DESC);
CREATE INDEX crypto_transfer_to_idx   ON fc.crypto_transfer (to_address, block_time DESC);

-- Nhãn phơi nhiễm dịch vụ, có hiệu lực theo thời gian (chương 10.4).
CREATE TABLE fc.exposure_label (
    exposure_id   TEXT        PRIMARY KEY,
    address       TEXT        NOT NULL,
    service_id    TEXT        NOT NULL,
    service_type  TEXT        NOT NULL CHECK (service_type IN (
                      'exchange', 'mixer', 'bridge', 'gambling', 'darknet', 'p2p', 'sanctioned')),
    -- direct = chính địa chỉ đó; indirect = cách vài hop.
    exposure_kind TEXT        NOT NULL CHECK (exposure_kind IN ('direct', 'indirect')),
    hops          SMALLINT    NOT NULL DEFAULT 0 CHECK (hops >= 0),
    confidence    NUMERIC(3, 2) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    source_id     TEXT        NOT NULL REFERENCES fc.source_registry (source_id) ON DELETE RESTRICT,
    -- Phụ lục D: nhãn chỉ được dùng nếu known_from <= thời điểm ra quyết định.
    known_from    TIMESTAMPTZ NOT NULL,
    valid_to      TIMESTAMPTZ
);

CREATE INDEX exposure_address_idx ON fc.exposure_label (address, known_from);

-- Dự án token — màn hình Project Risk (kịch bản VN-CA-01).
CREATE TABLE fc.token_project (
    project_id      TEXT        PRIMARY KEY,
    simulation_id   TEXT        NOT NULL REFERENCES fc.simulation_run (simulation_id) ON DELETE CASCADE,
    name            TEXT        NOT NULL,
    symbol          TEXT        NOT NULL,
    chain           TEXT        NOT NULL,
    contract_address TEXT       NOT NULL,
    deployer_address TEXT       NOT NULL,
    launched_at     TIMESTAMPTZ NOT NULL,
    -- Các đặc trưng quan sát được từ chương 10.1, không phải kết luận.
    holder_gini     NUMERIC(4, 3) CHECK (holder_gini BETWEEN 0 AND 1),
    liquidity_usd   NUMERIC(18, 2) NOT NULL DEFAULT 0,
    liquidity_removed_pct NUMERIC(5, 2) CHECK (liquidity_removed_pct BETWEEN 0 AND 100),
    privileged_functions TEXT[] NOT NULL DEFAULT '{}',
    kol_channels    SMALLINT    NOT NULL DEFAULT 0 CHECK (kol_channels >= 0),
    domain_age_days INTEGER     CHECK (domain_age_days >= 0),
    risk_score      SMALLINT    NOT NULL DEFAULT 0 CHECK (risk_score BETWEEN 0 AND 100),
    status          TEXT        NOT NULL DEFAULT 'monitoring'
                        CHECK (status IN ('monitoring', 'flagged', 'investigating', 'cleared'))
);

-- ---------------------------------------------------------------------
-- 5. Observation engine (chương 12.3)
-- ---------------------------------------------------------------------

-- Bằng chứng chỉ tồn tại trong view của một vai trò *sau* thời điểm được mở
-- quyền. Trước đó, truy vấn của agent phải không thấy gì — đây là cơ chế
-- chống rò rỉ chính của toàn bộ thiết kế.
CREATE TABLE fc.observation_event (
    observation_event_id TEXT   PRIMARY KEY,
    simulation_id   TEXT        NOT NULL REFERENCES fc.simulation_run (simulation_id) ON DELETE CASCADE,
    evidence_item_id TEXT       NOT NULL,
    observer_role   TEXT        NOT NULL CHECK (observer_role IN (
                        'BANK', 'FIU', 'REGULATOR', 'LAW_ENFORCEMENT', 'PUBLIC')),
    available_from  TIMESTAMPTZ NOT NULL,
    acquisition_type TEXT       NOT NULL CHECK (acquisition_type IN (
                        'native_system', 'report', 'request', 'seizure', 'cooperation', 'public')),
    legal_basis_id  TEXT,
    redaction_profile TEXT      NOT NULL DEFAULT 'none',
    source_confidence NUMERIC(3, 2) NOT NULL CHECK (source_confidence BETWEEN 0 AND 1),
    chain_of_custody_id TEXT,
    -- Cổng kiểm tra rò rỉ. Đặt false nghĩa là bản ghi tồn tại trong thế giới
    -- mô phỏng nhưng model không được nhìn thấy.
    is_visible_to_model BOOLEAN NOT NULL DEFAULT true,
    summary         TEXT        NOT NULL DEFAULT ''
);

CREATE INDEX observation_role_time_idx ON fc.observation_event (observer_role, available_from);
CREATE INDEX observation_evidence_idx  ON fc.observation_event (evidence_item_id);

COMMENT ON COLUMN fc.observation_event.available_from IS 'Trước mốc này, bằng chứng phải không tồn tại trong view của agent (chương 4.1).';
COMMENT ON COLUMN fc.observation_event.is_visible_to_model IS 'Cổng leakage. Phụ lục D kiểm tra cột này trong mọi lần tạo feature.';

-- ---------------------------------------------------------------------
-- 6. Vận hành AI Agent (gói AML_WORKFLOW)
-- ---------------------------------------------------------------------

CREATE TABLE fc.agent_run (
    run_id        TEXT        PRIMARY KEY,
    simulation_id TEXT        REFERENCES fc.simulation_run (simulation_id) ON DELETE SET NULL,
    case_id       TEXT        REFERENCES aml_case (case_id) ON DELETE SET NULL,
    alert_id      TEXT        REFERENCES alert (alert_id) ON DELETE SET NULL,
    -- Ba tầng năng lực của chương 11.
    agent_tier    TEXT        NOT NULL CHECK (agent_tier IN ('A_INSTITUTION', 'B_REGULATOR', 'C_INVESTIGATION')),
    started_at    TIMESTAMPTZ NOT NULL,
    finished_at   TIMESTAMPTZ,
    status        TEXT        NOT NULL CHECK (status IN ('running', 'succeeded', 'failed', 'needs_human')),
    model_version TEXT        NOT NULL,
    -- Kết luận và độ tin cậy do agent tự khai báo; luôn phải qua người duyệt.
    conclusion    TEXT        NOT NULL DEFAULT '',
    confidence    NUMERIC(3, 2) CHECK (confidence BETWEEN 0 AND 1),
    token_cost    INTEGER     NOT NULL DEFAULT 0 CHECK (token_cost >= 0),
    CONSTRAINT agent_run_time_order CHECK (finished_at IS NULL OR finished_at >= started_at)
);

CREATE INDEX agent_run_case_idx ON fc.agent_run (case_id, started_at DESC);

-- Từng bước trong một lần chạy. Chương 11.4 yêu cầu mọi lần gọi công cụ đều
-- kiểm toán được: vào gì, ra gì, mất bao lâu.
CREATE TABLE fc.agent_step (
    step_id      TEXT        PRIMARY KEY,
    run_id       TEXT        NOT NULL REFERENCES fc.agent_run (run_id) ON DELETE CASCADE,
    step_index   SMALLINT    NOT NULL CHECK (step_index >= 0),
    tool_name    TEXT        NOT NULL,
    input_summary TEXT       NOT NULL DEFAULT '',
    output_summary TEXT      NOT NULL DEFAULT '',
    status       TEXT        NOT NULL CHECK (status IN ('ok', 'error', 'skipped', 'blocked')),
    started_at   TIMESTAMPTZ NOT NULL,
    duration_ms  INTEGER     NOT NULL DEFAULT 0 CHECK (duration_ms >= 0),
    -- Bằng chứng mà bước này viện dẫn. Kết luận không có evidence_refs là
    -- kết luận không kiểm chứng được.
    evidence_refs TEXT[]     NOT NULL DEFAULT '{}',
    UNIQUE (run_id, step_index)
);

-- ---------------------------------------------------------------------
-- 7. Kiểm định và giám sát mô hình (chương 15, gói BENCHMARK)
-- ---------------------------------------------------------------------

-- Chương 15.1 nói thẳng: không dùng accuracy làm chỉ số chính. Bảng này lưu
-- các chỉ số có ý nghĩa vận hành — precision@k, thời gian phát hiện sớm,
-- tỷ lệ dương tính giả trên hard negative.
CREATE TABLE fc.benchmark_result (
    result_id     TEXT        PRIMARY KEY,
    simulation_id TEXT        REFERENCES fc.simulation_run (simulation_id) ON DELETE SET NULL,
    task_id       TEXT        NOT NULL,
    scenario_package TEXT     NOT NULL,
    model_version TEXT        NOT NULL,
    split         TEXT        NOT NULL CHECK (split IN ('train', 'validation', 'test')),
    metric_name   TEXT        NOT NULL,
    metric_value  NUMERIC(10, 4) NOT NULL,
    -- Ngưỡng đạt do nhóm kiểm định đặt trước, không phải chỉnh sau khi có kết quả.
    target_value  NUMERIC(10, 4),
    evaluated_at  TIMESTAMPTZ NOT NULL,
    UNIQUE (task_id, model_version, split, metric_name)
);

CREATE TABLE fc.model_monitor (
    monitor_id    TEXT        PRIMARY KEY,
    model_version TEXT        NOT NULL,
    observed_at   TIMESTAMPTZ NOT NULL,
    metric_name   TEXT        NOT NULL,
    metric_value  NUMERIC(10, 4) NOT NULL,
    -- PSI/KL cho trôi phân phối; NULL nếu chỉ số không phải loại trôi.
    drift_score   NUMERIC(10, 4),
    status        TEXT        NOT NULL CHECK (status IN ('ok', 'watch', 'breach')),
    UNIQUE (model_version, metric_name, observed_at)
);

CREATE INDEX model_monitor_version_idx ON fc.model_monitor (model_version, observed_at DESC);

-- Chất lượng dữ liệu — chương 12.1 gói OBSERVATION (missingness, latency).
CREATE TABLE fc.data_quality_check (
    check_id      TEXT        PRIMARY KEY,
    simulation_id TEXT        REFERENCES fc.simulation_run (simulation_id) ON DELETE SET NULL,
    dataset       TEXT        NOT NULL,
    check_name    TEXT        NOT NULL,
    dimension     TEXT        NOT NULL CHECK (dimension IN (
                      'completeness', 'timeliness', 'validity', 'consistency', 'uniqueness')),
    observed_at   TIMESTAMPTZ NOT NULL,
    pass_rate     NUMERIC(5, 2) NOT NULL CHECK (pass_rate BETWEEN 0 AND 100),
    threshold     NUMERIC(5, 2) NOT NULL CHECK (threshold BETWEEN 0 AND 100),
    rows_checked  BIGINT      NOT NULL CHECK (rows_checked >= 0),
    rows_failed   BIGINT      NOT NULL CHECK (rows_failed >= 0),
    status        TEXT        NOT NULL CHECK (status IN ('ok', 'warn', 'fail')),
    detail        TEXT        NOT NULL DEFAULT ''
);

CREATE INDEX dq_dataset_time_idx ON fc.data_quality_check (dataset, observed_at DESC);

-- ---------------------------------------------------------------------
-- 8. Hidden ground truth — schema riêng, cấm dùng cho inference
-- ---------------------------------------------------------------------

-- Chương 12.4. Đây là câu trả lời đúng của simulator, dùng để chấm điểm agent.
CREATE TABLE fc_gt.case_ground_truth (
    case_id          TEXT        PRIMARY KEY,
    simulation_id    TEXT        NOT NULL REFERENCES fc.simulation_run (simulation_id) ON DELETE CASCADE,
    scenario_type    TEXT        NOT NULL CHECK (scenario_type ~ '^VN-CA-0[1-5]$'),
    network_id       TEXT        NOT NULL,
    predicate_offence TEXT       NOT NULL CHECK (predicate_offence IN (
                         'fraud', 'gambling', 'cybercrime', 'tax_evasion', 'drug_trafficking', 'other')),
    -- Thời điểm hành vi bắt đầu, so với thời điểm tín hiệu đầu tiên quan sát
    -- được: hiệu số giữa hai mốc chính là "phát hiện sớm được bao lâu".
    first_illicit_event_time TIMESTAMPTZ NOT NULL,
    confirmation_time TIMESTAMPTZ,
    true_value_flow_usd NUMERIC(18, 2) NOT NULL CHECK (true_value_flow_usd >= 0),
    -- Bằng chứng agent ĐƯỢC phép viện dẫn khi lập luận.
    observable_evidence_refs TEXT[] NOT NULL DEFAULT '{}',
    -- Bằng chứng CẤM dùng khi suy luận; chỉ để chấm điểm.
    hidden_only_refs TEXT[]     NOT NULL DEFAULT '{}',
    counterfactual_run_ids TEXT[] NOT NULL DEFAULT '{}'
);

COMMENT ON TABLE fc_gt.case_ground_truth IS 'Đáp án của simulator. Dùng trong inference là rò rỉ nhãn (chương 12.4).';

-- Vai trò thật của từng thực thể trong mạng lưới.
CREATE TABLE fc_gt.hidden_role (
    simulation_id TEXT NOT NULL REFERENCES fc.simulation_run (simulation_id) ON DELETE CASCADE,
    entity_id     TEXT NOT NULL REFERENCES fc.entity (entity_id) ON DELETE CASCADE,
    case_id       TEXT NOT NULL REFERENCES fc_gt.case_ground_truth (case_id) ON DELETE CASCADE,
    true_role     TEXT NOT NULL CHECK (true_role IN (
                      'coordinator', 'mule', 'victim', 'broker', 'project_founder',
                      'service', 'operator', 'agent', 'player', 'innocent')),
    PRIMARY KEY (simulation_id, entity_id, case_id)
);

-- Tín hiệu sớm nhất mà mỗi vai trò quan sát được — mẫu số của mọi phép đo
-- "phát hiện sớm" (chương 12.4, chương 15).
CREATE TABLE fc_gt.first_observable_signal (
    case_id       TEXT NOT NULL REFERENCES fc_gt.case_ground_truth (case_id) ON DELETE CASCADE,
    observer_role TEXT NOT NULL CHECK (observer_role IN (
                      'BANK', 'FIU', 'REGULATOR', 'LAW_ENFORCEMENT', 'PUBLIC')),
    signal_time   TIMESTAMPTZ NOT NULL,
    signal_desc   TEXT NOT NULL,
    PRIMARY KEY (case_id, observer_role)
);

-- Ledger đánh bạc — ví dụ trung tâm của chương 10.3. Nó tồn tại trong thế
-- giới thật (trên server đối tượng) nhưng ngân hàng không nhìn thấy trước khi
-- điều tra, nên benchmark phát hiện sớm KHÔNG được phụ thuộc vào bảng này.
CREATE TABLE fc_gt.hidden_gambling_ledger (
    ledger_id     TEXT        PRIMARY KEY,
    simulation_id TEXT        NOT NULL REFERENCES fc.simulation_run (simulation_id) ON DELETE CASCADE,
    case_id       TEXT        NOT NULL REFERENCES fc_gt.case_ground_truth (case_id) ON DELETE CASCADE,
    operator_id   TEXT        NOT NULL,
    player_id     TEXT        NOT NULL,
    agent_id      TEXT,
    event_kind    TEXT        NOT NULL CHECK (event_kind IN ('deposit', 'chip_convert', 'bet', 'payout', 'settlement')),
    event_time    TIMESTAMPTZ NOT NULL,
    true_value_usd NUMERIC(18, 2) NOT NULL
);

COMMENT ON TABLE fc_gt.hidden_gambling_ledger IS 'Chương 10.3: tồn tại thật nhưng ngân hàng không quan sát được trước điều tra. Không được là feature của detector ngân hàng.';
