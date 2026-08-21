-- Kết quả chấm điểm nhánh Bitcoin (Elliptic++) đưa lên tầng vận hành.
--
-- Vì sao cần
-- ----------
-- Nhánh Bitcoin (Random Forest trên Elliptic++) trước đây chỉ tồn tại ở dạng
-- model + API POST /aml/bitcoin/predict + hai trang phân tích (Đánh giá chuẩn,
-- Mô hình). Không có gì bơm kết quả lên giao diện vận hành, nên Trung tâm cảnh
-- báo, Đồ thị và trang Truy vết tài sản mã hoá đều KHÔNG hiện gì cho Bitcoin —
-- người dùng tưởng nhánh này chưa chạy.
--
-- Bảng này giữ điểm của TẬP TEST Elliptic++ (chấm một lần bằng script, không
-- chấm lúc khởi động), để trang Truy vết đọc thẳng thành một hàng đợi giao dịch
-- bị nghi ngờ, kèm giải thích đời thường.
--
-- Vì sao KHÔNG dùng bảng alert/transaction chung
-- ----------------------------------------------
-- Elliptic++ ẩn danh: chỉ có mã giao dịch và 183 đặc trưng che tên — không địa
-- chỉ ví, không tài khoản, không nhãn dịch vụ. Bảng alert cần nối account →
-- customer; đồ thị cần cạnh tài khoản↔tài khoản. Ép Bitcoin vào đó thì hoặc
-- rỗng, hoặc phải bịa danh tính. Nên nó có bảng riêng, tách bạch với hai nhánh
-- ngân hàng.
--
-- Nhãn thật (true_label) LÀ nhãn công khai của Elliptic++ (illicit/licit), không
-- phải nhãn bịa: đây là bộ benchmark có nhãn, giữ lại để đối chiếu dự đoán của
-- model với sự thật trên chính tập test. Giao dịch 'unknown' đã bị loại từ tầng
-- dữ liệu nên không xuất hiện ở đây.

CREATE TABLE IF NOT EXISTS bitcoin_scored_tx (
    tx_id            TEXT PRIMARY KEY,
    release_id       TEXT NOT NULL,
    timestep         INTEGER,
    -- P(illicit) lấy thẳng từ predict_proba của Random Forest. KHÔNG cộng gộp
    -- với điểm nhánh IBM hay SAML-D — mỗi nhánh chấm trên vùng riêng.
    illicit_prob     NUMERIC(8, 6) NOT NULL,
    predicted_label  TEXT NOT NULL,      -- 'illicit' | 'licit'
    true_label       TEXT,               -- nhãn công khai Elliptic++: 'illicit' | 'licit'
    risk_level       TEXT NOT NULL,      -- LOW | MEDIUM | HIGH | CRITICAL
    requires_review  BOOLEAN NOT NULL DEFAULT FALSE,
    -- Giải thích đời thường dựng sẵn lúc chấm (tất định, không LLM), để endpoint
    -- không phải nạp lại vector đặc trưng chỉ để sinh câu chữ.
    headline         TEXT NOT NULL,
    reasons          JSONB NOT NULL DEFAULT '[]'::jsonb,
    caveat           TEXT NOT NULL,
    scored_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Xếp hàng đợi theo mức nghi ngờ giảm dần là truy vấn chính của trang.
CREATE INDEX IF NOT EXISTS bitcoin_scored_prob_idx
    ON bitcoin_scored_tx (illicit_prob DESC);
-- Lọc nhanh nhóm "cần rà soát".
CREATE INDEX IF NOT EXISTS bitcoin_scored_review_idx
    ON bitcoin_scored_tx (requires_review, illicit_prob DESC);

COMMENT ON TABLE bitcoin_scored_tx IS
    'Điểm Random Forest trên tập test Elliptic++ (nhánh Bitcoin). Một dòng mỗi '
    'giao dịch đã gán nhãn của tập test. Chấm bằng scripts/build_bitcoin_scored.py, '
    'không chấm lúc khởi động.';
COMMENT ON COLUMN bitcoin_scored_tx.true_label IS
    'Nhãn công khai của Elliptic++ (không bịa). Giữ để đối chiếu dự đoán với sự '
    'thật trên tập benchmark; không dùng làm căn cứ điều tra vì đây là đáp án.';
