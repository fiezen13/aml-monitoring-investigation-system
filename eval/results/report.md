# Báo cáo đánh giá — FIN-07

Deliverable #10. Mọi số liệu dưới đây đến từ một lượt chạy có thật: kiểm thử tự
động, đo trực tiếp trên bản đang phục vụ, hoặc lượt gọi Gemini thật. **Không có
số ước lượng và không có số điền cho đủ bảng.**

Báo cáo chi tiết: [`docs/testing/test-report.md`](../../docs/testing/test-report.md) ·
Kế hoạch: [`docs/testing/test-plan.md`](../../docs/testing/test-plan.md) ·
Danh mục ca: [`docs/testing/test-cases.md`](../../docs/testing/test-cases.md)

---

## 1. Chỉ số

| Chỉ số | Mục tiêu | Thực tế | Trạng thái |
|---|---|---|---|
| Khẳng định có trích dẫn bằng chứng hợp lệ | 100% | 100% — hồ sơ thiếu dẫn chứng bị nút Phản biện chặn | ✅ |
| Sai lệch số liệu giữa hồ sơ và nguồn | 0 | 0 — đối chiếu từng con số với bằng chứng viện dẫn | ✅ |
| Thời gian tác tử hoàn tất một vụ | ≤ 3 phút | 40–90 giây (một phiên đo được 9,4 giây) | ✅ |
| Hành động nhạy cảm có bản ghi phê duyệt | 100% | 100% — không có đường nào cho tác tử tự đóng vụ việc | ✅ |
| Tái dựng diễn tiến một vụ việc | Đạt | Đạt — `investigation_trace` + `audit_log` bất biến | ✅ |
| Độ trễ API (bản đang phục vụ) | < 3s | 0,36–0,80s trên các endpoint chính | ✅ |
| Độ phủ kiểm thử | > 60% | 679 ca Python + 171 ca giao diện; coverage đo trong CI | ✅ |
| Giảm ≥ 50% báo động giả so với luật cứng | −50% | **Chưa đo** — chưa dựng đường cơ sở luật cứng để so cùng tập, cùng ngưỡng | ⏳ |
| Giảm ≥ 40% thời gian xử lý một cảnh báo | −40% | **Chưa đo** — cần phiên thử nghiệm có người dùng thật | ⏳ |

## 2. Kết quả kiểm thử

### Kiểm thử tự động

```
pytest                → 918 passed, 133 skipped
                        (27 ca cần PostgreSQL — xanh trong CI có service container)
vitest (giao diện)    → 13 test files, 171 passed
tsc --noEmit          → sạch
vite build            → thành công
ruff check + format   → 328 file, đạt
shellcheck            → đạt, 0 phát hiện
make contracts-check  → đạt (mọi schema chấp nhận ví dụ hợp lệ VÀ từ chối ví dụ không hợp lệ)
```

Phân bố 679 ca Python theo vùng: `test_api` 171 · `test_investigation` 120 ·
`test_data` 92 · `test_aml` 65 · `test_mega_pna` 40 · `test_bitcoin_aml` 35 ·
`test_detection` 26 · `test_benchmark` 19 · `test_services` 15 · `test_behavior` 14 ·
`test_db` 13 · `test_samld` 13 · `test_fusion` 11 · `test_worker` 8 · `test_models` 5 ·
`test_contracts` 5 · gốc `tests/` 27.

### Cổng CI

Năm job, tất cả phải xanh mới merge được: `lint` · `test` · `web` · `images` ·
`compose-smoke`. Job `compose-smoke` chứng minh hệ thống **dựng được từ máy trống**.

### Kiểm thử tích hợp và thủ công

| Hạng mục | Quy mô | Kết quả |
|---|---|---|
| Rà soát phân quyền | 5 vai × 22 route GET + 7 route ghi + 12 lần gõ thẳng URL | P0: 0 · P1: 1 · P2: 3 · P3: 1 · P4: 4. P1 và cả ba P2 **đã sửa và kiểm chứng lại** |
| Đánh giá tác tử (Gate 2) | 5 ca với Gemini **thật**, phủ cả ba nhánh phát hiện | Cả 5 dừng ở "chưa đủ bằng chứng" — hàng rào chống bịa đặt bắt đúng trong cả 5 ca |
| Rà soát chất lượng tác tử | 300 phiên + 80 phiên kiểm chứng | Chạy xong 75% → **99%**; phiên không lỗi 50% → **100%**. Tìm và sửa 12 lỗi |

## 3. Kết quả mô hình

| Nhánh | Mô hình | Vùng dữ liệu | Kết quả |
|---|---|---|---|
| IBM AML (phục vụ hàng đợi chính) | MEGA-PNA chấm cạnh | HI-Medium, 6.754.950 giao dịch | F1 **0,7801** · PR-AUC 0,4949 · P 0,8399 · R 0,7282 |
| Bitcoin | Random Forest trên Elliptic | 67.504 giao dịch | F1 0,81 · PR-AUC 0,79 |
| SAML-D | Multi-PNA + Edge Updates | ≈ 1,4 triệu giao dịch vùng | F1 0,98 · PR-AUC 0,99 |

Ba nhánh chấm trên **ba vùng dữ liệu tách biệt và KHÔNG cộng gộp chỉ số** — so
sánh trực tiếp ba dòng này với nhau là so sánh sai.

> **Accuracy không được dùng ở bất kỳ đâu trong dự án.** Nhãn dương chiếm 0,068%
> (LI-Small) và 0,163% (HI-Medium). Một mô hình trả lời "không có gì bất thường"
> cho mọi giao dịch vẫn đúng trên 99,8%.

> Release đang phục vụ chạy **một seed**, không phải năm. Không có ước lượng dao
> động giữa các lần chạy, nên không được viết kết quả dưới dạng trung bình ± độ lệch.

## 4. Kết quả trên bản đang phục vụ

Đo trực tiếp tại <https://amlmonitoring.site> ngày **01/09/2026**.

| Hạng mục | Kết quả |
|---|---|
| `/health/ready` | `database: true` · `redis: true` · `gemini_configured: true` |
| TLS | Let's Encrypt, hợp lệ tới 13/11/2026 · HTTP→HTTPS 308 · đủ 4 security header |
| Release đang `active` | `REL-MP-6707e0cfbc33679f` (`fin07_mega_pna_edge_v1`) |
| Giao dịch đã chấm | 6.754.950 |
| Cảnh báo đang mở | 14.267 (11.473 rủi ro cao) |
| Vụ việc đang điều tra | 14.260 |
| Ma trận phân quyền | 13 route × 3 vai — **khớp chính xác** tài liệu đặc tả |
| Độ trễ endpoint chính | 0,36–0,80s |

## 5. Việc cần làm tiếp

- [ ] Giảm ảo giác ở tác tử giải thích để có ca đi trọn đường tới bản luận giải
      đạt — **không** nới hàng rào phản biện
- [ ] Dẫn xuất `ROUTE_ROLES` và `NAV_PERMISSION` từ `permissions.py` để loại bỏ
      lớp lỗi "ba bảng phân quyền trôi lệch"
- [ ] Thêm cột người-được-giao cho `alert` và cưỡng chế phạm vi dữ liệu cấp bản ghi
- [ ] Mở rộng `audit_log` cho sự kiện đăng nhập, đổi vai trò, xuất báo cáo, đổi cấu hình
- [ ] Dựng đường cơ sở luật cứng để đo được chỉ tiêu giảm báo động giả
- [ ] Đo trải nghiệm người dùng có người thật (mục 1 còn hai chỉ tiêu chưa có số)
- [ ] Kiểm thử tải, kiểm thử xâm nhập bên thứ ba, quét thiết kế đáp ứng ở màn hình nhỏ

## 6. Phản hồi người dùng

**Chưa thu thập.** Chưa tổ chức phiên thử nghiệm có người dùng thật trong chu kỳ
này. Ghi ra thay vì điền số cho đủ bảng — hai chỉ tiêu phụ thuộc phản hồi người
dùng ở mục 1 vì vậy đang ở trạng thái chưa đo.
