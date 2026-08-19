-- Tách vũ trụ tài khoản theo bộ dữ liệu, và nhận cảnh báo từ nhánh luật địa lý.
--
-- Vì sao cần
-- ----------
-- Hệ thống nay phục vụ nhiều hơn một bộ dữ liệu. Tài khoản ngân hàng của IBM
-- AML và tài khoản của SAML-D là hai vũ trụ tách biệt: khoá trùng nhau về hình
-- thức nhưng không cùng một thực thể, và không có giao dịch nào nối chúng.
--
-- Thiếu cột này thì hàng đợi cảnh báo trộn cả hai, chuyên viên mở một cảnh báo
-- SAML-D ra sẽ không thấy hồ sơ khách hàng nào, và tưởng hệ thống hỏng. Nó cũng
-- làm mọi con số thống kê trên bảng điều khiển thành tổng của hai thứ không
-- cộng được với nhau.
--
-- Vì sao là một CỘT chứ không phải tiền tố trong account_key
-- ---------------------------------------------------------
-- account_key đã mang nghĩa `mã_ngân_hàng:số_tài_khoản` và được tách chuỗi ở
-- nhiều nơi. Nhét thêm một đoạn nữa là phá hợp đồng ấy ở mọi chỗ đang tách.
-- Một cột riêng thì lọc được, đánh chỉ mục được, và không đụng vào khoá.
--
-- Mặc định là 'ibm_hi_medium' để toàn bộ dữ liệu đang có tự nhận đúng nguồn mà
-- không cần backfill riêng.

ALTER TABLE account ADD COLUMN IF NOT EXISTS dataset TEXT NOT NULL DEFAULT 'ibm_hi_medium';
ALTER TABLE alert   ADD COLUMN IF NOT EXISTS dataset TEXT NOT NULL DEFAULT 'ibm_hi_medium';

COMMENT ON COLUMN account.dataset IS
    'Bộ dữ liệu mà tài khoản này thuộc về. Tài khoản của hai bộ khác nhau không '
    'bao giờ giao dịch với nhau; đừng gộp thống kê giữa chúng.';
COMMENT ON COLUMN alert.dataset IS
    'Bộ dữ liệu của cảnh báo, sao chép từ tài khoản lúc sinh cảnh báo. Có ở đây '
    'để hàng đợi lọc được mà không phải join sang account.';

CREATE INDEX IF NOT EXISTS account_dataset_idx ON account (dataset);
CREATE INDEX IF NOT EXISTS alert_dataset_idx   ON alert   (dataset, status);

-- Nhánh luật địa lý (World Monitor) chạy trên SAML-D. Nó KHÔNG dùng lại mã
-- 'rule': mã ấy đang là bộ luật nghiệp vụ trên dữ liệu IBM, có bộ tham số và
-- bảng lý do riêng. Trộn hai nhánh vào một mã là mất khả năng nói cảnh báo này
-- đến từ đâu, đúng như lý do đã ghi ở 022 khi tách mega_pna khỏi ml.
DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    SELECT conname INTO constraint_name
      FROM pg_constraint
     WHERE conrelid = 'alert'::regclass
       AND contype = 'c'
       AND pg_get_constraintdef(oid) LIKE '%detector%';

    IF constraint_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE alert DROP CONSTRAINT %I', constraint_name);
    END IF;

    ALTER TABLE alert
        ADD CONSTRAINT alert_detector_check
        CHECK (detector IN ('rule', 'ml', 'graph', 'mega_pna', 'geo_rule'));
END
$$;

COMMENT ON COLUMN alert.detector IS
    'Nhánh phát hiện đã mở cảnh báo: rule (luật nghiệp vụ IBM), ml (Isolation '
    'Forest), graph (bộ dò mẫu hình), mega_pna (mô hình đồ thị MEGA-PNA), '
    'geo_rule (bộ luật địa lý trên SAML-D).';

-- Quốc gia của giao dịch, cho nhánh địa lý.
--
-- Bảng `bank` đã có quốc gia, nhưng nó gắn theo NGÂN HÀNG. SAML-D không có mã
-- ngân hàng — nó cho thẳng vị trí của bên gửi và bên nhận trên từng giao dịch,
-- và một tài khoản có thể xuất hiện ở nhiều vị trí. Ghi thẳng lên giao dịch là
-- cách duy nhất giữ đúng dữ liệu gốc mà không bịa ra một cây ngân hàng không
-- tồn tại.
ALTER TABLE transaction ADD COLUMN IF NOT EXISTS from_country TEXT;
ALTER TABLE transaction ADD COLUMN IF NOT EXISTS to_country   TEXT;

COMMENT ON COLUMN transaction.from_country IS
    'Quốc gia của ngân hàng bên gửi. Chỉ có với bộ dữ liệu mang sẵn thông tin '
    'này (SAML-D); để NULL với bộ không có, không suy đoán.';
COMMENT ON COLUMN transaction.to_country IS
    'Quốc gia của ngân hàng bên nhận. Xem ghi chú ở from_country.';

CREATE INDEX IF NOT EXISTS transaction_country_idx
    ON transaction (from_country, to_country)
    WHERE from_country IS NOT NULL;

-- Trạng thái 'reference' cho bản rollup không phải mô hình đang phục vụ.
--
-- `edge_country_hub` và `edge_country_flow` có khoá ngoại tới `edge_model_release`,
-- mà bảng ấy chỉ cho đúng MỘT bản ghi 'active'. Bản đồ địa lý dựng từ SAML-D
-- không chấm điểm cạnh và không thay thế release đang phục vụ, nên gán cho nó
-- 'active' là cướp chỗ, còn gán 'retired' là nói rằng nó từng phục vụ rồi bị
-- thay — cả hai đều sai. 'reference' nói đúng vai trò: nguồn tham chiếu.
DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    SELECT conname INTO constraint_name
      FROM pg_constraint
     WHERE conrelid = 'edge_model_release'::regclass
       AND contype = 'c'
       AND pg_get_constraintdef(oid) LIKE '%status%';

    IF constraint_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE edge_model_release DROP CONSTRAINT %I', constraint_name);
    END IF;

    ALTER TABLE edge_model_release
        ADD CONSTRAINT edge_model_release_status_check
        CHECK (status IN ('loading', 'active', 'retired', 'failed', 'reference'));
END
$$;
