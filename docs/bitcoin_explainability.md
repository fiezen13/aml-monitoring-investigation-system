# Bitcoin AML (Elliptic++) — Explainability Redesign · QA Report

Redesign trang giao dịch nhánh Bitcoin để đạt yêu cầu nghiệp vụ AML: tách **điểm
rủi ro** khỏi **chất lượng giải thích**, không bịa nghĩa đặc trưng ẩn danh, phân
biệt **ground-truth** với **model-predicted**, và thu gọn SHAP kỹ thuật.

## 1. Files changed

**Backend**
- `src/bitcoin_aml/explain.py` — thêm `interpretable_ratio` (|SHAP| đọc được),
  `explanation_quality` (HIGH/MEDIUM/LIMITED, tất định), `contribution_breakdown`.
- `scripts/build_bitcoin_scored.py` — dựng tập **known-illicit** (nhãn thật) toàn
  Elliptic++; `_graph_evidence` tách known vs predicted + gắn `known_illicit` cho
  từng láng giềng; tính + lưu `interpretable_ratio`, `explanation_quality`,
  `graph_known_illicit_neighbours`.
- `db/init/027_bitcoin_explanation_quality.sql` — 3 cột mới.
- `src/models/fc_schemas.py`, `src/api/fc_routes.py` — expose các trường mới +
  `neighbour.known_illicit`.

**Frontend**
- `web/src/pages/CryptoPage.tsx` — redesign: hàng đợi gọn → mở ra hồ sơ 6 mục
  A–F; đồ thị thượng-nguồn/mục-tiêu/hạ-nguồn có chú giải; SHAP thu gọn.
- `web/src/api/client.ts` — kiểu `FcBitcoinRow`/`FcBitcoinNeighbour` mới.

**Tests**: `tests/test_bitcoin_aml/test_explain.py` (+6 test).

## 2. Backend explanation schema (structured — nguồn sự thật)

Mỗi giao dịch trong `bitcoin_scored_tx` / `BitcoinScoredRowOut`:

| Trường | Ý nghĩa |
|---|---|
| `illicit_prob`, `risk_level` | ĐIỂM RỦI RO (P(illicit) từ RF). |
| `interpretable_ratio` | Tỷ phần \|SHAP\| từ 7 đặc trưng có nghĩa — "phần giải thích được". |
| `explanation_quality` | HIGH/MEDIUM/LIMITED — tất định, TÁCH khỏi rủi ro. |
| `drivers[]` | Đóng góp Saabas theo từng đặc trưng (ẩn danh → `label=null`). |
| `graph_flagged_neighbours` | Láng giềng **model dự đoán** illicit. |
| `graph_known_illicit_neighbours` | Láng giềng **nhãn thật** illicit (ground truth). |
| `graph_neighbours[].flag` / `.known_illicit` | Dự đoán vs sự thật, tách bạch. |
| `reasons[]`, `caveat` | Câu diễn giải + giới hạn (tất định). |

Giao diện + gợi ý điều tra sinh TỪ các trường này (presentation layer), không
parse ngược từ văn bản.

## 3. How SHAP is calculated

`src/bitcoin_aml/attribution.py::illicit_contributions` — **Saabas** (phân rã
đóng góp chính xác theo cây, cộng dồn trên rừng), cho lớp `illicit`. Đây là đóng
góp per-instance THẬT (không phải feature importance toàn cục). Tổng đóng góp +
bias = P(illicit) của model. UI gọi nó là **"phần giải thích của mô hình"**,
KHÔNG phải "phần trăm nguyên nhân/xác suất phạm tội".

## 4. How explanation quality is calculated (deterministic — không dùng LLM)

`explanation_quality(interpretable, known_illicit_nb, flagged_nb)`:
- **HIGH**: `interpretable ≥ 0.50` **và** có bằng chứng đồ thị.
- **MEDIUM**: `interpretable ≥ 0.35` **hoặc** có ≥1 láng giềng **nhãn thật** illicit.
- **LIMITED**: còn lại (phần lớn ẩn danh, ít bằng chứng đọc được).

Ngưỡng ở `explain.py` (hằng số, chỉnh được). Trên tập cần rà soát: **485 LIMITED
/ 63 MEDIUM / 0 HIGH** — phản ánh trung thực rằng Elliptic++ quá ẩn danh để đạt
HIGH. Chỉ láng giềng *model-dự-đoán* KHÔNG đủ nâng chất lượng (tránh đánh đồng
dự đoán với sự thật).

## 5. Which Elliptic++ features have verified semantics

Model dùng 60 đặc trưng; **7 có nghĩa công bố** (dùng làm nhãn, phần còn lại
tuyệt đối không đặt tên):

`fees`, `size` (byte), `num_input_addresses`, `num_output_addresses`,
`in_BTC_min`, `in_BTC_median`, `out_BTC_min`.

## 6. Which features remain anonymous

**53/60**: `Local_feature_N`, `Aggregate_feature_N` — Elliptic++ KHÔNG công bố ý
nghĩa. UI hiển thị đúng mã kỹ thuật ở phần SHAP thu gọn; ở phần nghiệp vụ gộp
thành một thẻ "tín hiệu mô hình từ đặc trưng ẩn danh" + đếm số lượng. **Không**
suy diễn thành mixer/layering/darknet.

## 7. Known-illicit vs predicted-risk — cách phân biệt

- **Known-illicit**: `tx_id ∈` tập nhãn thật `label==1` của toàn Elliptic++
  (`txs_classes`). Màu đỏ + viền + nhãn "Đã biết bất hợp pháp".
- **Model-predicted**: `predicted==illicit` trên tập test đã chấm. Màu cam + nhãn
  "Model dự đoán rủi ro cao". Đếm riêng (`known` 63 vs `predicted` 27 trên tập
  rà soát). Hai trạng thái KHÔNG bao giờ hiển thị giống nhau.

## 8. Before / after UX

| | Trước | Sau |
|---|---|---|
| Mở đầu | Đoạn văn AI + 5 dòng "đặc trưng ẩn danh" | Hồ sơ 6 mục A–F, tóm tắt trước |
| Rủi ro vs giải thích | Gộp làm một (100/100) | **Hai chỉ số riêng**: rủi ro + chất lượng giải thích |
| Đặc trưng ẩn danh | 5 "reason" ẩn danh | Gộp 1 thẻ "model-only signal" + đếm |
| SHAP | Bày sẵn, lẫn nghiệp vụ | **Thu gọn** sau nút "Xem chi tiết kỹ thuật" |
| Láng giềng | "cũng bị gắn cờ" (mập mờ) | Known (đỏ) vs predicted (cam), có chú giải |
| Đồ thị | Vài chấm | Thượng nguồn → **GIAO DỊCH NÀY** → hạ nguồn + legend |
| "18% lực đẩy nghi ngờ" | Sai hàm ý | "% phần giải thích được của mô hình" |
| Cần kiểm tra tiếp | Không có | Mục F sinh từ bằng chứng thật |

## 9. Screens manually tested (headless browser)

- `/crypto` hàng đợi + mở hồ sơ tx **30204549** (MEDIUM, có láng giềng
  known-illicit — CASE 3): 6 mục A–F render, đồ thị + legend đúng, SHAP thu gọn,
  không lỗi console.
- Xác minh CASE 2 (LIMITED): tx prob 0.99 nhưng quality **Hạn chế** — không bịa lý do.

## 10. Tests executed

- `tests/test_bitcoin_aml`: **26 passed** (+6 mới: interpretable_ratio,
  explanation_quality tách khỏi rủi ro, predicted-only không nâng quality…).
- Regression `bitcoin + api`: **101 passed, 9 skipped**. Web `tsc` sạch.

## 11. Acceptance criteria

AC1 hiểu-không-cần-SHAP ✓ · AC2 ẩn-danh-không-giả-làm-lý-do ✓ · AC3 known≠predicted
✓ · AC4 rủi-ro≠chất-lượng ✓ · AC5 upstream/target/downstream ✓ · AC6 số-liệu-đồ-thị
✓ · AC7 SHAP-thu-gọn ✓ · AC8 không-khẳng-định-rửa-tiền ✓ · AC9 không-bịa-mẫu-hình ✓
· AC10 narrative-từ-structured (tất định, không LLM) ✓ · AC11 chạy-khi-thiếu-đồ-thị
✓ · AC12 responsive/dark-theme ✓.

## 12. Remaining explainability limitations (nói thẳng)

- **Đến từ chính Elliptic++**: 53/60 đặc trưng ẩn danh → chất lượng giải thích
  của phần lớn cảnh báo tối đa là **MEDIUM/LIMITED**, không thể HIGH. Đây là giới
  hạn dữ liệu, không phải lỗi — UI thừa nhận thay vì che.
- *(Đã bổ sung ở lớp Evidence — xem §49 bên dưới)*: multi-hop (BFS ≤3, có trần
  nút) + hop-distance + rule-based topology detector (fan-in/out/gather-scatter/
  chain) — đều đóng khung "cấu trúc quan sát được", không suy diễn tội phạm.
- **Agent narrative**: hiện là template tất định (không gọi LLM) — đúng tinh thần
  "structured evidence là nguồn sự thật"; nếu sau này gắn LLM thì phải theo
  §22–23 (chỉ diễn đạt lại structured evidence, cấm bịa).

---

# Interpretable Investigation Evidence Layer — Deliverables (§49)

Lớp bằng chứng điều tra chạy SONG SONG Random Forest (không thay, không retrain,
không bịa semantic). Ba lớp giữ riêng: **Model risk** · **Investigation evidence**
· **Explainability**.

## A. Files changed
- **Thêm**: `src/bitcoin_aml/evidence.py` (Graph Evidence Engine), `db/init/028_bitcoin_investigation_evidence.sql`, `tests/test_bitcoin_aml/test_evidence.py` (16 test).
- **Sửa**: `scripts/build_bitcoin_scored.py` (precompute evidence), `src/models/fc_schemas.py` + `src/api/fc_routes.py` (expose), `web/src/api/client.ts` + `web/src/pages/CryptoPage.tsx` (3-dim header, badge, multi-hop, topology).

## B. Graph evidence metrics
direct upstream/downstream count · direct/2-hop known-illicit (ground truth) · direct/2-hop model-high-risk (prediction) · nearest_known_illicit_hop & nearest_model_high_risk_hop (BFS ≤3, null nếu ngoài phạm vi) · neighborhood 1/2-hop breakdown (known_illicit/known_licit/model_high_risk/unknown) · mean/max neighbour model-risk · in/out/total degree · max_linear_chain.

## C. Pattern rules (observed structure, KHÔNG phải nhãn tội phạm)
FAN_IN (in≥5 và in>2·out) · FAN_OUT (out≥5 và out>2·in) · GATHER_SCATTER (in≥5 và out≥5) · LINEAR_CHAIN (≥4 giao dịch in≈out≈1). Ngưỡng ở hằng số module (chỉnh được). Toàn tập: LINEAR_CHAIN 1258 · FAN_IN 798 · FAN_OUT 423 · GATHER_SCATTER 37.

## D. Label-leakage protections
- Bằng chứng đồ thị tính **SAU** suy luận, ở module RIÊNG (`evidence.py`) — không chạm predictor.
- Nhãn thật láng giềng chỉ để HIỂN THỊ; KHÔNG là đặc trưng RF.
- Test `test_ground_truth_labels_khong_ro_vao_dac_trung_random_forest`: 60 đặc trưng RF không chứa `neighbor/illicit/label/known/hop/graph_`.

## E. Evidence schema
`graph_evidence` (jsonb): `direct_context` · `ground_truth_exposure` · `model_risk_context` · `neighborhood{one_hop,two_hop}` · `topology{...,observed_patterns}` · `strength`. Kèm `evidence_strength` (NONE/WEAK/MODERATE/STRONG), `evidence_reasons` (badge nguồn), `recommended_steps`.

## F. Agent
Reason builder **tất định** (`evidence_reasons`) là nguồn sự thật, ưu tiên bằng chứng mạnh trước tín hiệu ẩn danh; mỗi lý do mang badge GROUND_TRUTH/GRAPH/MODEL/PREDICTION. Chưa gắn LLM — đúng tinh thần "structured evidence là source of truth"; nếu gắn sau này phải theo §37 (chỉ diễn đạt lại, cấm bịa).

## G. UI before/after
Trước: header 1 chiều (100/100), "5 đặc trưng ẩn danh", đồ thị vài chấm. Sau: **header 3 chiều** (Model risk | Bằng chứng điều tra | Chất lượng giải thích) độc lập; "Vì sao" từ evidence_reasons có **badge nguồn**, ưu tiên phơi nhiễm illicit trước tín hiệu ẩn danh; bằng chứng đồ thị có multi-hop + hop-distance + cấu trúc quan sát; SHAP thu gọn; gợi ý điều tra sinh từ bằng chứng thật.

## H. Performance / caching
Chỉ mục kề dựng **MỘT LẦN** từ txs_edgelist; BFS có trần hop (≤3) + trần nút (600). Precompute toàn bộ vào `bitcoin_scored_tx` bằng script — API chỉ đọc, **không** duyệt đồ thị mỗi request. Chấm lại 16.670 giao dịch: **~12,5s**.

## I. Tests
`test_evidence.py` 16 test (label-leakage, hướng up/down, known≠predicted, hop-distance + null, fan-in/out/gather-scatter/chain, strength, **CASE C** model-thấp-evidence-mạnh, null graph, node-budget cap). Regression bitcoin+api: **117 passed, 9 skipped**. Web `tsc` sạch. Browser: header 3-chiều + badge + multi-hop render, không lỗi console.

## J. Known limitations
- **Model risk ⟂ evidence**: kiểm chứng trên dữ liệu — avg model risk ~0.88 ở CẢ ba mức strength (NONE/MODERATE/STRONG); 441 giao dịch model-thấp vẫn có known-illicit láng giềng (CASE C). Hai lớp thực sự độc lập.
- Chất lượng giải thích tối đa **MEDIUM** (Elliptic++ 53/60 đặc trưng ẩn danh) — giới hạn dữ liệu, UI thừa nhận.
- **Temporal (rapid movement, §17)**: Elliptic++ chỉ có timestep thô nên CHƯA làm — không quy đổi timestep thành "phút".
- **Path-to-illicit highlight & expand-graph control (1/2/3 hop tương tác, §31-32)**: dữ liệu hop-distance + multi-hop đã có ở backend; phần tương tác đồ thị động chưa dựng (đồ thị hiện là 1-hop tĩnh + số liệu multi-hop).
