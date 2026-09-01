# Danh mục ca kiểm thử — FIN-07

Danh mục các nhóm ca kiểm thử, ánh xạ tới yêu cầu mà chúng bảo vệ và tới file
kiểm thử hiện thực chúng.

Tài liệu liên quan: [kế hoạch kiểm thử](test-plan.md) ·
[báo cáo kiểm thử](test-report.md) · [yêu cầu chức năng](../specification/functional-requirements.md).

Ký hiệu mã: `TC-<vùng>-<số>`. Cột *File* trỏ tới hiện thực; chạy một nhóm bằng
`pytest <đường dẫn file>`.

---

## 1. Phân quyền và kiểm soát truy cập

Bảo vệ: [yêu cầu chức năng §2, §3, §7](../specification/functional-requirements.md#2-ma-trận-quyền).

| Mã | Ca kiểm thử | Kỳ vọng | File |
|---|---|---|---|
| TC-AUTHZ-01 | **Mọi** route `/api/v1` đều có khai báo chính sách | Không route nào thiếu chính sách; route mới quên khai báo → đỏ | `test_api/test_authz.py` |
| TC-AUTHZ-02 | Route không khai báo chính sách | 403, không phải mở mặc định | `test_api/test_authz.py` |
| TC-AUTHZ-03 | Ma trận vai × quyền khớp `ROLE_PERMISSIONS` | Đúng từng ô, kiểm cả chiều dương và chiều âm | `test_api/test_permissions.py` |
| TC-AUTHZ-04 | Quản trị hệ thống gọi route nghiệp vụ AML | 403 trên mọi cảnh báo / vụ việc / phê duyệt / SAR | `test_api/test_permissions.py` |
| TC-AUTHZ-05 | Chuyên viên gọi route quyết định SAR | 403 — chỉ Quản lý có `decide_sar` | `test_api/test_permissions.py` |
| TC-AUTHZ-06 | Quản lý gọi route soạn SAR | 403 — Quản lý cố ý **không** có `prepare_sar` (nguyên tắc bốn mắt) | `test_api/test_permissions.py` |
| TC-AUTHZ-07 | Quản trị hệ thống gọi tab kỹ thuật | Qua cổng — chỉ vai này có `view_model_quality` | `test_api/test_permissions.py` |
| TC-SCOPE-01 | Phạm vi dữ liệu áp ở máy chủ, không nhận từ tham số client | Tham số client bị bỏ qua | `test_api/test_role_scope.py` |
| TC-SCOPE-02 | Đọc chi tiết vụ việc ngoài phạm vi | **404** (không phải 403) — không lộ sự tồn tại của bản ghi | `test_api/test_role_scope.py` |
| TC-SCOPE-03 | Phạm vi áp đồng nhất trên danh sách, chi tiết và đồ thị mạng lưới | Ba lối vào cùng một kết quả lọc | `test_api/test_role_scope.py` |
| TC-GUARD-01 | Hàng rào đầu vào của API | Đầu vào sai bị từ chối trước khi chạm CSDL | `test_api/test_guardrails.py` |

---

## 2. Tác tử điều tra

Bảo vệ: [thiết kế kỹ thuật §4](../specification/technical-design.md#4-tầng-tác-tử-điều-tra).

| Mã | Ca kiểm thử | Kỳ vọng | File |
|---|---|---|---|
| TC-AGENT-01 | Gọi công cụ ngoài allow-list | `ValueError`, lượt gọi bị ghi lại là bị từ chối | `test_investigation/test_schemas_and_tools.py` |
| TC-AGENT-02 | Tham số công cụ sai kiểu / ngoài ràng buộc | Bị Pydantic từ chối **trước** bước kiểm quyền | `test_investigation/test_schemas_and_tools.py` |
| TC-AGENT-03 | Mô hình cố phát SQL hoặc chạy mã tuỳ ý | Không có đường nào — cổng công cụ chỉ nhận tên + tham số | `test_investigation/test_schemas_and_tools.py` |
| TC-AGENT-04 | Chạm trần 5 vòng | Kết thúc `INSUFFICIENT_EVIDENCE`, lý do nêu rõ "hết vòng" | `test_investigation/test_workflow_integration.py` |
| TC-AGENT-05 | Chạm trần 16 lượt gọi công cụ | Kết thúc `INSUFFICIENT_EVIDENCE`, lý do nêu rõ số lượt đã dùng | `test_investigation/test_workflow_integration.py` |
| TC-AGENT-06 | Chuyển trạng thái hợp lệ của máy trạng thái | `INITIALIZED → COLLECTING_EVIDENCE → EXPLAINING → VALIDATING → COMPOSING_REPORT → COMPLETED` | `test_investigation/test_workflow_integration.py` |
| TC-AGENT-07 | Khẳng định không có `evidence_refs` | Nút Phản biện chặn, hồ sơ không sang bước phê duyệt | `test_investigation/test_consistency.py` |
| TC-AGENT-08 | Con số trong luận giải không có trong bằng chứng viện dẫn | `UNSUPPORTED_CLAIM` | `test_investigation/test_consistency.py` |
| TC-AGENT-09 | Mã bằng chứng viện dẫn không tồn tại | `MISSING_SOURCE_RECORD` | `test_investigation/test_consistency.py` |
| TC-AGENT-10 | Luận giải mâu thuẫn với bằng chứng | `CONTRADICTION` | `test_investigation/test_consistency.py` |
| TC-AGENT-11 | Chất lượng bản giải thích | Không có mã nội bộ / thuật ngữ kỹ thuật lọt ra bản dành cho chuyên viên | `test_investigation/test_explanation_quality.py` |
| TC-AGENT-12 | Ánh xạ typology từ bằng chứng | Khớp danh mục có phiên bản; không khớp → `T00`, không gán bừa | `test_investigation/test_typology_match.py` |
| TC-AGENT-13 | `LLM_MODE=mock` | Tác tử tất định, không gọi mạng | `test_investigation/test_gemini_service.py` |
| TC-AGENT-14 | Thuật lại đồ thị | Mô tả khớp motif có thật trong bằng chứng | `test_investigation/test_graph_narrative.py` |

---

## 3. Bất biến ở tầng cơ sở dữ liệu

Bảo vệ: [mô hình dữ liệu §2.2](../specification/data-model.md#22-ràng-buộc-cưỡng-chế-ở-tầng-cơ-sở-dữ-liệu).

| Mã | Ca kiểm thử | Kỳ vọng | File |
|---|---|---|---|
| TC-DB-01 | `UPDATE` trên `audit_log` | Trigger từ chối | `test_db/test_audit_immutability.py` |
| TC-DB-02 | `DELETE` trên `audit_log` | Trigger từ chối | `test_db/test_audit_immutability.py` |
| TC-DB-03 | Vai trò tác tử thử `INSERT`/`UPDATE`/`DELETE` | Bị CSDL từ chối — chỉ có `SELECT` | `test_db/test_agent_role_isolation.py` |
| TC-DB-04 | Chuyển trạng thái vụ việc hợp lệ | Đúng sáu trạng thái, đúng vai đẩy | `test_db/test_case_state_machine.py` |
| TC-DB-05 | Trạng thái vụ việc không hợp lệ | Ràng buộc `CHECK` từ chối | `test_db/test_case_state_machine.py` |
| TC-DB-06 | Kho dữ liệu lô hành vi | Ghi/đọc đúng, idempotent | `test_db/test_behavior_batch_repository.py` |

---

## 4. Hợp đồng dữ liệu

Bảo vệ: [mô hình dữ liệu §7](../specification/data-model.md#7-hợp-đồng-dữ-liệu).

| Mã | Ca kiểm thử | Kỳ vọng | File |
|---|---|---|---|
| TC-CONTRACT-01 | Mọi JSON Schema trong `contracts/` hợp lệ | Không schema nào hỏng cú pháp | `test_contracts/test_schemas_valid.py` |
| TC-CONTRACT-02 | Ví dụ **hợp lệ** phải được chấp nhận | Xác thực đạt | `test_contracts/test_schemas_valid.py` |
| TC-CONTRACT-03 | Ví dụ **không hợp lệ** phải bị từ chối | Xác thực trượt — một schema chấp nhận mọi thứ là schema vô dụng | `test_contracts/test_schemas_valid.py` |
| TC-CONTRACT-04 | Lược đồ typology khớp danh mục đang dùng | Không lệch giữa schema và dữ liệu | `test_data/test_typology_schema.py` |

---

## 5. Đường ống dữ liệu và detector

Bảo vệ: [thiết kế kỹ thuật §2](../specification/technical-design.md#2-nhánh-phát-hiện).

| Mã | Ca kiểm thử | Kỳ vọng | File |
|---|---|---|---|
| TC-ETL-01 | ETL Task 1 trên mẫu nhỏ | Chuẩn hoá đúng, chia tập theo thời gian đúng | `test_data/test_task1_etl.py` |
| TC-ETL-02 | Phân tích file pattern Task 2 | Ánh xạ đúng sang danh mục typology | `test_data/test_task2_typology.py` |
| TC-GRAPH-01 | 8 đặc trưng đồ thị trên cửa sổ nửa mở | Công thức khớp đặc tả; biên cửa sổ đúng | `test_data/test_graph_features.py` |
| TC-GRAPH-02 | Cờ khởi động nguội | `history_available=0` khi không có lịch sử; đặc trưng "mới lạ" không bắt buộc | `test_data/test_graph_features.py` |
| TC-GRAPH-03 | Detector CYCLE, độ dài 2–6 | Chỉ phát chu trình có nhân chứng nhất quán thời gian | `test_data/test_cycle_detector.py` |
| TC-GRAPH-04 | Detector FAN_IN / FAN_OUT (`v3_min`) | Phân biệt bùng phát đáng ngờ với hub bậc cao lành tính | `test_data/test_fan_detector.py` |
| TC-GRAPH-05 | Detector GATHER_SCATTER | Gom vào rồi toả ra trong cùng cửa sổ | `test_data/test_gather_scatter_detector.py` |
| TC-GRAPH-06 | Đánh giá detector đồ thị | Chỉ số tính đúng trên tập đã chia | `test_data/test_graph_detector_eval.py` |
| TC-RULE-01 | Luật nghiệp vụ | Mỗi lần bật cảnh báo đều kèm lý do | `test_detection/test_rules.py` |
| TC-BEH-01 | Cửa sổ đặc trưng hành vi | Nửa mở `[as_of_ts − 7d, as_of_ts)`, biên đúng | `test_behavior/test_feature_windows.py` |
| TC-BEH-02 | Lô chấm điểm hành vi | Chạy lại cho cùng kết quả | `test_behavior/test_batch.py` |
| TC-FUSION-01 | Hiệu chuẩn phân vị **chỉ fit trên train** | Không dùng dữ liệu val/test | `test_fusion/test_training.py` |
| TC-FUSION-02 | Đóng gói và nạp lại bundle hợp nhất | Nạp lại cho cùng điểm | `test_fusion/test_model.py` |
| TC-FUSION-03 | Nạp release vào PostgreSQL | Idempotent; mã băm mô hình khớp | `test_fusion/test_release_loader.py` |
| TC-BENCH-01 | Hợp đồng báo cáo benchmark | Chỉ khoá `headline` của `fin07.benchmark.v1` được trích dẫn | `test_benchmark/` |

---

## 6. API và console

| Mã | Ca kiểm thử | Kỳ vọng | File |
|---|---|---|---|
| TC-API-01 | Các endpoint console | Trả đúng hình dạng dữ liệu từng màn hình | `test_api/test_console_endpoints.py` |
| TC-API-02 | Luồng nghiệp vụ đầu–cuối | Cảnh báo → điều tra → hồ sơ → trình → chốt | `test_api/test_production_flow.py` |
| TC-API-03 | Giao việc và phân công | Người giao được ghi đúng; tự nhận là "tự nhận", không phải "giao trực tiếp" | `test_api/test_assignments.py`, `test_api/test_case_assignment.py` |
| TC-API-04 | Chính sách trợ lý AI | Chuyên viên không có công cụ điều phối nào | `test_api/test_copilot_policy.py` |
| TC-API-05 | Luồng trợ lý AI | Mô hình chỉ soạn đề xuất; máy chủ thực thi bằng mã tất định sau khi người dùng xác nhận | `test_api/test_copilot_flow.py` |
| TC-API-06 | Soạn SAR | Bản nháp gắn bằng chứng | `test_api/test_sar_drafter.py` |
| TC-API-07 | Kết xuất PDF SAR | Sinh được PDF, hiển thị đúng tiếng Việt (phông nhúng) | `test_api/test_sar_pdf.py` |
| TC-API-08 | Đồ thị giao dịch | Tách từng thành phần liên thông, không trộn mạng độc lập | `test_api/test_graph_transactions.py` |
| TC-API-09 | Địa lý thế giới | Hub và hành lang khớp dữ liệu nguồn | `test_api/test_world_geography.py` |
| TC-API-10 | Hàng đợi rà soát tài sản mã hoá | Trạng thái rà soát chuyển đúng | `test_api/test_crypto_review.py` |

---

## 7. Cấu hình, từ vựng và quan trắc

| Mã | Ca kiểm thử | Kỳ vọng | File |
|---|---|---|---|
| TC-CFG-01 | Mọi trường `Settings` và `AmlSettings` có trong `.env.example` | Thêm trường mà quên tài liệu → đỏ | `tests/test_config_documented.py` |
| TC-CFG-02 | Mọi `${BIEN}` trong `docker-compose.yml` có trong `.env.example` | Không biến nào thiếu tài liệu | `tests/test_config_documented.py` |
| TC-DOM-01 | Danh mục typology liệt kê đúng mã còn hiệu lực | `T08` đã gỡ và **không** tái xuất hiện | `tests/test_domain.py` |
| TC-DOM-02 | Nhãn trạng thái vụ việc | Đủ sáu trạng thái, không lọt mã thô ra giao diện | `tests/test_domain.py` |
| TC-OBS-01 | Cấu hình quan trắc | Mỗi cảnh báo Prometheus trỏ tới đúng một runbook | `tests/test_observability.py` |

---

## 8. Ca kiểm thử thủ công

Chi tiết kết quả ở [báo cáo kiểm thử](test-report.md).

| Mã | Ca kiểm thử | Cách chạy |
|---|---|---|
| TC-MAN-01 | Ma trận vai × route trên bản đang chạy | Token thật cho từng vai, 22 route GET + 7 route ghi |
| TC-MAN-02 | Gõ thẳng URL vượt qua menu | 12 lần nạp trực tiếp trên trình duyệt headless |
| TC-MAN-03 | Điều tra bằng Gemini thật | 5 ca Gate 2, phủ cả ba nhánh phát hiện |
| TC-MAN-04 | Rà soát chất lượng tác tử theo lô | 300 phiên lấy mẫu theo cặp (detector, nhóm hành vi) |
| TC-MAN-05 | Dựng từ máy trống | `docker compose up` trên máy sạch — cũng chạy tự động trong job `compose-smoke` |
