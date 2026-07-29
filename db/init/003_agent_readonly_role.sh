#!/bin/sh
# =====================================================================
# FIN-07 — Vai trò chỉ đọc cho agent (QD1, NT5)
#
# QD1: agent truy cập dữ liệu qua bộ công cụ chỉ đọc, không truy vấn trực
# tiếp. NT5: mỗi thành phần chỉ truy cập trường dữ liệu cần cho nhiệm vụ của
# nó, danh sách trường cho phép khai báo tường minh.
#
# Vì sao đây là script shell chứ không phải .sql như hai file kia: mật khẩu
# vai trò phải lấy từ biến môi trường, mà psql KHÔNG thay biến bên trong
# chuỗi trích dẫn kiểu $$...$$. Viết bằng .sql thì khối DO chứa :'biến' trở
# thành lỗi cú pháp, và — đây mới là phần khó chịu — container postgres vẫn
# khởi động với một cơ sở dữ liệu thiếu mất vai trò này. Ở đây biến được
# truyền vào psql bằng -v, psql tự trích dẫn đúng cách.
#
# Bài kiểm thử tự động khẳng định vai trò này bị cách ly:
#   tests/test_db/test_agent_role_isolation.py
# =====================================================================
set -eu

if [ -z "${FIN07_AGENT_DB_PASSWORD:-}" ]; then
    echo "LỖI: FIN07_AGENT_DB_PASSWORD chưa được đặt." >&2
    echo "      Tạo vai trò không mật khẩu là chuyện không được phép xảy ra," >&2
    echo "      nên khởi tạo cơ sở dữ liệu dừng ở đây. Xem docs/ENVIRONMENT.md." >&2
    exit 1
fi

psql -v ON_ERROR_STOP=1 \
     --username "${POSTGRES_USER}" \
     --dbname "${POSTGRES_DB}" \
     -v agent_password="${FIN07_AGENT_DB_PASSWORD}" <<'SQL'
SET client_min_messages TO WARNING;

CREATE ROLE fin07_agent LOGIN PASSWORD :'agent_password';

CREATE SCHEMA agent;

COMMENT ON SCHEMA agent IS 'Bề mặt dữ liệu duy nhất mà agent nhìn thấy. Thêm view ở đây là mở rộng phạm vi truy cập — phải qua pull request.';

-- --- Danh sách trường cho phép, khai báo tường minh --------------------

CREATE VIEW agent.transaction AS
SELECT transaction_id, occurred_at, from_account_key, to_account_key,
       amount, currency, amount_received, receiving_currency, channel, remarks
FROM public.transaction;

COMMENT ON VIEW agent.transaction IS 'remarks là dữ liệu do người dùng cuối nhập — agent phải coi là dữ liệu, không phải chỉ dẫn (RK2).';

CREATE VIEW agent.account AS
SELECT account_key, customer_id, bank_code, opened_at, status
FROM public.account;

CREATE VIEW agent.customer AS
SELECT customer_id, customer_type, occupation, declared_income_band,
       expected_monthly_volume, registered_country, onboarding_date, risk_rating
FROM public.customer;

CREATE VIEW agent.alert AS
SELECT alert_id, account_key, transaction_id, typology_code, detector,
       risk_score, status, case_id, created_at
FROM public.alert;

CREATE VIEW agent.alert_reason AS
SELECT alert_reason_id, alert_id, factor_code, factor_label, contribution, weight
FROM public.alert_reason;

CREATE VIEW agent.watchlist_entry AS
SELECT list_entry_id, watchlist_version_id, full_name, normalized_name,
       aliases, entity_type, country, list_type
FROM public.watchlist_entry;

CREATE VIEW agent.screening_result AS
SELECT screening_id, case_id, account_key, list_entry_id, watchlist_version_id,
       score, verdict, screened_at
FROM public.screening_result;

CREATE VIEW agent.aml_case AS
SELECT case_id, subject_account_key, title, state, risk_score, priority, created_at, updated_at
FROM public.aml_case;

-- --- Cấp quyền -------------------------------------------------------
-- Không cấp USAGE trên schema public: view trong schema agent chạy bằng
-- quyền của chủ sở hữu view, nên agent vẫn đọc được đúng những cột đã khai
-- báo ở trên mà không chạm được bảng gốc.

REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA agent TO fin07_agent;
GRANT SELECT ON ALL TABLES IN SCHEMA agent TO fin07_agent;

-- View mới thêm vào schema agent tự động được cấp quyền; bảng ở public thì không.
ALTER DEFAULT PRIVILEGES IN SCHEMA agent GRANT SELECT ON TABLES TO fin07_agent;

-- Chặn tường minh, không dựa vào mặc định.
REVOKE ALL ON SCHEMA label FROM PUBLIC, fin07_agent;
REVOKE ALL ON ALL TABLES IN SCHEMA label FROM PUBLIC, fin07_agent;
SQL

echo "Đã tạo vai trò fin07_agent và schema agent."
