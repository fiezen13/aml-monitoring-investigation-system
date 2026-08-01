# Contract dữ liệu demo — FIN-07

Ba loại dữ liệu dùng chung giữa các nhóm.  
**Giao dịch** đã có trong pipeline hiện tại. **Cảnh báo** và **bằng chứng** là format đề xuất để backend sinh / frontend hiện — chưa có trong pipeline data.

---

## 1. Giao dịch (`transaction`) — dữ liệu bơm vào

| Trường | Kiểu | Bắt buộc | Ý nghĩa |
|--------|------|----------|---------|
| `transaction_id` | string | Có | Mã giao dịch (duy nhất) |
| `occurred_at` | datetime UTC | Có | Thời điểm giao dịch |
| `from_bank` | string | Có | Ngân hàng gửi |
| `from_account_raw` | string | Có | Tài khoản gửi (mã gốc) |
| `from_account_key` | string | Có | Khóa gửi: `{bank}:{account}` |
| `to_bank` | string | Có | Ngân hàng nhận |
| `to_account_raw` | string | Có | Tài khoản nhận (mã gốc) |
| `to_account_key` | string | Có | Khóa nhận: `{bank}:{account}` |
| `amount_paid_orig` | float | Có | Số tiền gửi (gốc) |
| `payment_currency` | string | Có | Loại tiền gửi |
| `amount_received_orig` | float | Có | Số tiền nhận (gốc) |
| `receiving_currency` | string | Có | Loại tiền nhận |
| `amount` | float | Có | Số tiền gửi quy đổi USD |
| `amount_received` | float | Có | Số tiền nhận quy đổi USD |
| `currency` | string | Có | Đơn vị chung (`USD`) |
| `channel` | string | Có | `ACH` \| `WIRE` \| `CHEQUE` \| `CREDIT_CARD` \| `CASH` \| `BITCOIN` \| `REINVESTMENT` \| `OTHER` |
| `split` | string | Có | `train` \| `val` \| `test` |
| `label_laundering` | 0 \| 1 | Có | Nhãn đánh giá dataset — không dùng làm kết luận trên UI |

```json
{
  "transaction_id": "a1b2c3d4e5f6789012345678abcdef01",
  "occurred_at": "2022-09-01T00:20:00+00:00",
  "from_bank": "1",
  "from_account_raw": "ACC001",
  "from_account_key": "1:ACC001",
  "to_bank": "2",
  "to_account_raw": "ACC002",
  "to_account_key": "2:ACC002",
  "amount_paid_orig": 9500.0,
  "payment_currency": "USD",
  "amount_received_orig": 9500.0,
  "receiving_currency": "USD",
  "amount": 9500.0,
  "amount_received": 9500.0,
  "currency": "USD",
  "channel": "WIRE",
  "split": "test",
  "label_laundering": 0
}
```

---

## 2. Cảnh báo (`alert`) — backend sinh ra

| Trường | Kiểu | Bắt buộc | Ý nghĩa |
|--------|------|----------|---------|
| `alert_id` | string | Có | Mã cảnh báo |
| `created_at` | datetime UTC | Có | Thời điểm tạo |
| `subject_account_key` | string | Có | Tài khoản bị nghi |
| `primary_typology` | string \| null | Có | `T01`…`T10` hoặc null |
| `secondary_typologies` | list[string] | Có | Mặc định `[]` |
| `risk_score` | float | Có | Điểm rủi ro **0–100** |
| `severity` | string | Có | `LOW` \| `MEDIUM` \| `HIGH` \| `CRITICAL` |
| `status` | string | Có | `OPEN` \| `IN_REVIEW` \| `ESCALATED` \| `CLOSED` |
| `title` | string | Có | Tiêu đề ngắn |
| `summary` | string | Có | Tóm tắt |
| `window_start` | datetime UTC | Có | Đầu cửa sổ xét |
| `window_end` | datetime UTC | Có | Cuối cửa sổ xét |
| `rule_or_model` | string | Có | Luật / mô hình đã bật |
| `score_breakdown` | list | Có | Các yếu tố đóng góp điểm |

Mỗi phần tử `score_breakdown`:

| Trường | Kiểu | Ý nghĩa |
|--------|------|---------|
| `factor` | string | Tên yếu tố |
| `contribution` | float | Điểm đóng góp |
| `detail` | string \| null | Giải thích ngắn |

```json
{
  "alert_id": "alt_demo_001",
  "created_at": "2026-08-01T10:00:00+00:00",
  "subject_account_key": "1:ACC001",
  "primary_typology": "T01",
  "secondary_typologies": [],
  "risk_score": 82.5,
  "severity": "HIGH",
  "status": "OPEN",
  "title": "Chia nhỏ giao dịch dưới ngưỡng — cửa sổ 24 giờ",
  "summary": "Nhiều khoản chuyển sát dưới ngưỡng; tổng trong 24 giờ vượt mức đáng chú ý.",
  "window_start": "2022-09-01T00:00:00+00:00",
  "window_end": "2022-09-02T00:00:00+00:00",
  "rule_or_model": "stub:demo_v1",
  "score_breakdown": [
    {"factor": "count_near_threshold", "contribution": 30.0, "detail": "8 giao dịch sát ngưỡng"},
    {"factor": "sum_amount_24h", "contribution": 35.0, "detail": "Tổng USD 78500"},
    {"factor": "amount_stddev_low", "contribution": 17.5, "detail": "Số tiền các khoản rất đều"}
  ]
}
```

---

## 3. Bằng chứng cảnh báo (`alert_evidence`)

| Trường | Kiểu | Bắt buộc | Ý nghĩa |
|--------|------|----------|---------|
| `evidence_id` | string | Có | Mã bằng chứng |
| `alert_id` | string | Có | Thuộc cảnh báo nào |
| `evidence_type` | string | Có | `TRANSACTION` \| `ACCOUNT_STAT` \| `GRAPH_PATTERN` \| `RULE_HIT` \| `MODEL_SCORE` |
| `ref_table` | string | Có | Nguồn (vd `transaction`) |
| `ref_id` | string | Có | Mã bản ghi gốc (vd `transaction_id`) |
| `occurred_at` | datetime UTC \| null | — | Thời điểm (nếu có) |
| `role` | string | Có | `TRIGGER` \| `SUPPORTING` \| `CONTEXT` |
| `snippet` | object | Có | Ảnh chụp các trường đã dùng |
| `weight` | float \| null | — | Trọng số (tuỳ chọn) |

```json
{
  "evidence_id": "ev_demo_001_01",
  "alert_id": "alt_demo_001",
  "evidence_type": "TRANSACTION",
  "ref_table": "transaction",
  "ref_id": "a1b2c3d4e5f6789012345678abcdef01",
  "occurred_at": "2022-09-01T00:20:00+00:00",
  "role": "TRIGGER",
  "snippet": {
    "from_account_key": "1:ACC001",
    "to_account_key": "2:ACC002",
    "amount": 9500.0,
    "currency": "USD",
    "channel": "WIRE"
  },
  "weight": 0.12
}
```

---

## Quan hệ ngắn

- Nhiều `transaction` → hệ thống sinh `alert`
- Mỗi `alert` có một hoặc nhiều `alert_evidence`
- `alert_evidence.ref_id` (khi loại `TRANSACTION`) trỏ về `transaction.transaction_id`
