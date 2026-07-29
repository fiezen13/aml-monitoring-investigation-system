-- =====================================================================
-- FIN-07 — Bất biến hoá nhật ký kiểm toán
--
-- QD6: "Quy ước trong mã nguồn có thể bị vi phạm do sơ suất; ràng buộc ở
-- tầng dữ liệu thì không." NT4: nhật ký chỉ ghi thêm.
--
-- Ba bảng dưới đây là bằng chứng pháp lý, không phải trạng thái ứng dụng:
--   audit_log — diễn tiến vụ việc
--   approval  — quyết định của người có thẩm quyền
--   evidence  — dữ liệu mà mọi khẳng định trong hồ sơ neo vào
--
-- approval là ngoại lệ có kiểm soát: một dòng đang ở trạng thái `pending`
-- được phép chuyển sang quyết định cuối một lần duy nhất. Sau đó khoá.
-- =====================================================================

SET client_min_messages TO WARNING;

CREATE OR REPLACE FUNCTION deny_mutation() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'Bảng % chỉ cho phép ghi thêm: thao tác % bị chặn ở tầng cơ sở dữ liệu (QD6, NT4)',
        TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;

-- --- audit_log: chặn tuyệt đối ---------------------------------------

CREATE TRIGGER audit_log_no_update
    BEFORE UPDATE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION deny_mutation();

CREATE TRIGGER audit_log_no_delete
    BEFORE DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION deny_mutation();

CREATE TRIGGER audit_log_no_truncate
    BEFORE TRUNCATE ON audit_log
    EXECUTE FUNCTION deny_mutation();

-- --- evidence: chặn tuyệt đối ----------------------------------------

CREATE TRIGGER evidence_no_update
    BEFORE UPDATE ON evidence
    FOR EACH ROW EXECUTE FUNCTION deny_mutation();

CREATE TRIGGER evidence_no_delete
    BEFORE DELETE ON evidence
    FOR EACH ROW EXECUTE FUNCTION deny_mutation();

CREATE TRIGGER evidence_no_truncate
    BEFORE TRUNCATE ON evidence
    EXECUTE FUNCTION deny_mutation();

-- --- approval: một lần chuyển từ pending sang quyết định cuối ---------

CREATE OR REPLACE FUNCTION approval_write_once() RETURNS TRIGGER AS $$
BEGIN
    IF OLD.decision <> 'pending' THEN
        RAISE EXCEPTION
            'Phê duyệt % đã ở trạng thái %; quyết định đã ghi không sửa được (NT4)',
            OLD.approval_id, OLD.decision
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.approval_id <> OLD.approval_id OR NEW.case_id <> OLD.case_id THEN
        RAISE EXCEPTION 'Không được đổi approval_id hoặc case_id của một phê duyệt đã tồn tại'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER approval_write_once_update
    BEFORE UPDATE ON approval
    FOR EACH ROW EXECUTE FUNCTION approval_write_once();

CREATE TRIGGER approval_no_delete
    BEFORE DELETE ON approval
    FOR EACH ROW EXECUTE FUNCTION deny_mutation();

CREATE TRIGGER approval_no_truncate
    BEFORE TRUNCATE ON approval
    EXECUTE FUNCTION deny_mutation();
