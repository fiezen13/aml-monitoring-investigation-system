-- Interpretable Investigation Evidence Layer (nhánh Bitcoin/Elliptic++).
-- Bằng chứng đồ thị tính SAU suy luận Random Forest — TÁCH khỏi điểm rủi ro
-- model. Nạp bằng scripts/build_bitcoin_scored.py (module src/bitcoin_aml/evidence.py).
--
-- * evidence_strength: NONE/WEAK/MODERATE/STRONG — sức mạnh bằng chứng điều tra,
--   quy tắc tất định, KHÔNG cộng thành xác suất AML.
-- * graph_evidence: object có cấu trúc (direct_context, ground_truth_exposure,
--   model_risk_context, neighborhood 1/2-hop, topology + observed_patterns).
-- * evidence_reasons: lý do tất định kèm badge nguồn (GROUND_TRUTH/GRAPH/MODEL/…).
-- * recommended_steps: gợi ý điều tra sinh từ bằng chứng thật.
ALTER TABLE bitcoin_scored_tx
    ADD COLUMN IF NOT EXISTS evidence_strength text
        CHECK (evidence_strength IN ('NONE', 'WEAK', 'MODERATE', 'STRONG')),
    ADD COLUMN IF NOT EXISTS graph_evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS evidence_reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS recommended_steps jsonb NOT NULL DEFAULT '[]'::jsonb;
