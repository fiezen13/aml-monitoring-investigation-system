# FIN-07 — Báo cáo hoàn thiện hệ thống theo sơ đồ kiến trúc

**Bộ dữ liệu:** IBM AML **LI-Small** — 6.119.572 giao dịch, 576.781 tài khoản
**Ngày:** 2026-08-15
**Phạm vi:** đưa toàn bộ sáu hộp trong sơ đồ kiến trúc từ *bản vẽ* thành *hệ thống chạy được*

---

## 1. Tóm tắt cho người nghe vội

Sơ đồ kiến trúc vẽ ba nhánh phát hiện, một tầng hợp nhất điểm và một vòng phản
hồi. Trước đợt này, cơ sở dữ liệu có **một** nhánh, **một** nhóm hành vi và
**không** bằng chứng đồ thị nào.

| | Trước | Sau |
|---|---|---|
| Nhánh phát hiện có dữ liệu | 1 / 3 | **3 / 3** |
| Nhóm hành vi phân biệt được | 1 (T02, đóng dấu cứng) | **6** |
| Bằng chứng đồ thị | 0 | **613** bản ghi, 0 cạnh lệch |
| Hợp nhất điểm | `fusion_available: false` | **`true`**, ba thành phần |
| Độ phủ chấm điểm giao dịch | 0 % | **100 %** (6.119.572/6.119.572) |
| Vòng phản hồi | ghi rồi bỏ đó | có kho nhãn + endpoint + script hiệu chỉnh |
| Kiểm thử tự động | 606 | **641** |

Kết quả mô hình trên LI-Small thấp hơn hẳn số liệu cũ. **Đó là bản chất bộ dữ
liệu, không phải lỗi** — mục 5 giải thích.

---

## 2. Đối chiếu từng hộp trong sơ đồ

| Hộp | Trạng thái | Bằng chứng |
|---|---|---|
| 1. Dữ liệu | ✅ | 6.119.572 giao dịch LI-Small trong PostgreSQL |
| 2. Tiền xử lý | ✅ | chuẩn hoá `account_key`, chia thời gian 60/20/20 |
| 3. Feature + Graph | ✅ | 200.944 ảnh chụp đặc trưng, 37 đặc trưng cạnh |
| 4a. Rule Engine | ✅ **mới** | 19.704 cảnh báo |
| 4b. Isolation Forest | ✅ | 500 cảnh báo |
| 4c. Graph Detectors | ✅ **mới nối** | 830 cảnh báo, 613 bằng chứng mẫu hình |
| 5. Score Fusion | ✅ **mới** | hợp nhất 3 nhánh, `fusion_available: true` |
| 6. High-risk alert | ✅ | 21.034 cảnh báo, 6 nhóm hành vi |
| Tầng 3 tác tử | ✅ | supervisor / explanation / critic |
| 8 công cụ | ✅ | `GetGraphEvidence` lần đầu trả dữ liệu thật |
| Feedback loop | ⚠️ khép ở mức dữ liệu | bảng nhãn + endpoint + script khuyến nghị ngưỡng |

---

## 3. Nhánh Rule — xây mới

`src/detection/rules.py` + `src/detection/rule_engine.py`.

Bốn luật, mỗi luật khai tín hiệu riêng để nối thẳng vào danh mục nhóm hành vi:

| Mã | Nội dung | Nhóm hành vi | Kích hoạt |
|---|---|---|---|
| R01_STRUCTURING | Nhiều giao dịch sát dưới ngưỡng báo cáo | T01 | 7.129 |
| R02_RAPID_MOVEMENT | Tiền ra trong 2 giờ sau khi nhận | T05 | 1.998 |
| R03_VASP_EXPOSURE | Giá trị đi qua đối tác VASP | T08 | 11.191 |
| R04_CROSS_BORDER_FLOW | Ngân hàng hai đầu khác quốc gia | *(phụ)* | 4.853 |

**Quét:** 298.780 tài khoản → 19.704 cảnh báo (6,6 %).

### Hai quyết định thiết kế đáng nói khi thuyết trình

**Luật chính và luật phụ.** Bản đầu tiên cho R04 tự mở cảnh báo → **31,9 %** tài
khoản bị gắn cờ. Giao dịch xuyên biên giới là chuyện bình thường ở dữ liệu đa
ngân hàng, không phải vi phạm; trong danh mục nó cũng chỉ là tín hiệu *hỗ trợ*.
Chuyển R04 thành luật phụ → còn 6,6 %, và nó vẫn làm giàu ngữ cảnh cho cảnh báo
do luật chính mở.

**Hai luật cố ý không viết.**
- *T10 lệch hồ sơ khách hàng* — bảng `customer` có 1.461.697 dòng nhưng đúng
  **một** giá trị `expected_monthly_volume` và **một** `registered_country`. Đó
  là dữ liệu lấp chỗ; luật trên đó sinh ra cảnh báo trông có lý mà không có căn cứ.
- *T06 quốc gia rủi ro cao* — cần danh sách được chỉ định (FATF hoặc nội bộ),
  repo chỉ có toạ độ. R04 vì thế chỉ nêu dữ kiện "khác quốc gia".

---

## 4. Nhánh Graph — nối vào hệ thống

Ba detector FAN / GATHER_SCATTER / CYCLE đã chạy từ trước và để lại 117.288 bản
ghi. **Phần thiếu là cầu nối vào PostgreSQL, không phải bản thân detector.**

Khó nhất là dịch mã: bằng chứng dùng `source_transaction_id` (băm), PostgreSQL
đánh số bằng `bigint`. Bộ phản biện đối chiếu **từng cạnh** với bảng giao dịch —
lệch một cạnh là cả phiên điều tra bị đánh trượt.

```
staged 613 · loaded 613 · dropped 0
```

Một truy vấn đi ngược lại đúng phép kiểm đó trên toàn bộ dữ liệu: **0 cạnh lệch**.

| Mẫu hình | Số bản ghi |
|---|---|
| FAN_IN | 472 |
| CYCLE | 72 |
| FAN_OUT | 69 |

---

## 5. Hộp 5 — hợp nhất ba nhánh

`src/fusion/tri.py`. Giữ nguyên phép toán của bản hai nhánh:

```
contribution_i = weight_i × percentile_i
fusion_score   = Σ contribution_i
```

Giữ nguyên là có chủ đích: `get_risk_breakdown` suy ngược trọng số bằng
`contribution / percentile` để giải thích điểm cho chuyên viên. Đổi công thức sẽ
làm phần giải thích nói sai.

Mảnh chưa từng tồn tại là **điểm rule ở dạng lưới** — `scripts/compute_rule_grid.py`
tính trên đúng lưới 4.841.824 dòng × 10 mốc mà fusion dùng.

### Kết quả (trọng số chọn trên tập kiểm định, tập kiểm tra chạm đúng một lần)

Trọng số thắng: **rule 0,55 · anomaly 0,00 · graph 0,45** · ngưỡng 0,984252

| | val F1 | test F1 | test PR-AUC |
|---|---|---|---|
| rule đơn | 0,0188 | 0,0130 | 0,0051 |
| anomaly đơn | 0,0303 | 0,0159 | 0,0153 |
| graph đơn | 0,1466 | 0,1338 | **0,0841** |
| **hợp nhất 3 nhánh** | **0,1485** | **0,1365** | 0,0789 |

Tập kiểm tra: 1.678.763 dòng, 6.029 nhãn dương, 6.628 cảnh báo.

### Hai điều phải nói thật khi thuyết trình

**Hợp nhất chỉ nhỉnh hơn graph đơn rất ít** — F1 0,1365 so với 0,1338, và PR-AUC
còn *thấp hơn* (0,0789 so với 0,0841). Giá trị của hợp nhất ở đây nằm ở khả
năng **giải thích** (chuyên viên thấy nhánh nào đóng góp bao nhiêu), không nằm ở
độ chính xác.

**Bộ tối ưu loại hẳn Isolation Forest** — trọng số 0,00. Trên LI-Small, nhánh
bất thường không đóng góp gì cho tổ hợp. Hệ thống báo trung thực
`available: false` kèm câu *"được cân nhắc rồi bị loại ở bước kiểm định"* — khác
hẳn với "không chạy được".

Ví dụ thật từ một cảnh báo:

```
rule     score 0,9968  weight 0,55  contrib 0,5482
anomaly  score 0,9810  weight 0,00  contrib 0,0000
graph    score 0,9987  weight 0,45  contrib 0,4494
                              final = 0,9976  ✓
```

---

## 6. Kết quả mô hình cạnh (currency-native edge)

Huấn luyện lại hoàn toàn trên LI-Small, 5 seed.

| | HI-Medium (cũ) | **LI-Small (mới)** |
|---|---|---|
| F1 trung bình 5 seed | 0,713 | **0,297** (độ lệch chuẩn 0,013) |
| PR-AUC | 0,713 | **0,237** |
| Precision / Recall | 0,914 / 0,592 | 0,435 / 0,232 |
| Tỷ lệ nhãn dương | 0,17 % | **0,058 %** |

### Vì sao thấp hơn — đây là điểm dễ bị hỏi nhất

Chênh lệch **nằm trong bản chất bộ dữ liệu**, không phải mô hình hỏng. Tên bộ dữ
liệu IBM AML mã hoá đúng điều đó:

- **HI** = *higher illicit ratio*
- **LI** = *lower illicit ratio*

LI-Small loãng gấp ba lần: 1 giao dịch rửa tiền trên 1.460 giao dịch ở tập kiểm
tra. Phát hiện khó hơn hẳn.

> **Cảnh báo khi trình bày:** mọi con số F1 quanh 0,7 trong tài liệu cũ là của
> HI-Medium. Đưa chúng cạnh sơ đồ ghi "IBM AML LI-Small" là hai thứ không thuộc
> về nhau.

---

## 7. Nhóm hành vi — từ 1 mã lên 6

Trước đây cả ba nơi sinh cảnh báo đều đóng dấu cứng `T02`: **6.541/6.541** cảnh
báo cùng một nhóm. Trong khi đó `typologies.json` đã mô tả sẵn điều kiện của cả
mười nhóm — luật đã có, chỉ chưa ai chạy.

`src/investigation/typology_match.py` đối chiếu tín hiệu quan sát được với danh
mục. **Luật nằm trong danh mục, không nằm trong code.**

| Mã | Tên | Số cảnh báo |
|---|---|---|
| T08 | Dòng tiền gắn tài sản ảo | 10.663 |
| T01 | Chia nhỏ giao dịch | 7.129 |
| T05 | Chuyển tiền nhanh | 2.024 |
| T02 | Tài khoản trung chuyển | 1.024 |
| T03 | Vòng tiền | 192 |
| T04 | Gom vào / toả ra | 2 |

**20.010 mã suy từ tín hiệu, 1.024 dùng mặc định** (95,1 % có căn cứ).

Điểm quan trọng: khi không tín hiệu nào đủ điều kiện, mã vẫn là T02 **nhưng tự
khai `is_fallback = true`**. Tác tử phản biện đọc cờ này để biết có được coi
nhóm hành vi như một dữ kiện hay không — đó chính là khoảng trống khiến nó liên
tục phản đối trước đây.

---

## 8. Vòng phản hồi

Trước: quyết định rà soát ghi vào một trường JSON bị ghi đè mỗi lần, cộng một
dòng nhật ký. Không truy vấn được theo lô, và **không giữ điểm số tại thời điểm
ra quyết định** — mà thiếu điểm thì nhãn không hiệu chỉnh được cho cái gì.

Sau:

1. Bảng `review_feedback` — mỗi nhãn kèm ảnh chụp điểm, nhánh, nhóm hành vi lúc
   chuyên viên quyết định.
2. `GET /api/v1/feedback/labels` — xuất nhãn theo lô.
3. `scripts/calibrate_from_feedback.py` — quét ngưỡng trên nhãn, in khuyến nghị.

Quy đổi nhãn: `REQUEST_MORE_INFORMATION` và `CONTINUE_MONITORING` xếp
`INCONCLUSIVE`, **không** phải nhãn âm — gộp chúng vào nhóm âm sẽ dạy mô hình
rằng mọi việc chưa xử lý xong đều là báo động giả.

Script **không tự đổi ngưỡng** và từ chối khuyến nghị khi dưới 30 nhãn. Đổi
ngưỡng phát hiện là quyết định nghiệp vụ, không phải hệ quả tự động của một truy
vấn.

---

## 9. Lỗi phát hiện được khi chạy hệ thống thật

Những lỗi này chỉ lộ ra khi có dữ liệu thật ở cả ba nhánh — đáng đưa vào bài nói
vì chúng cho thấy giá trị của việc chạy end-to-end.

| Lỗi | Triệu chứng | Nguyên nhân |
|---|---|---|
| Regex số âm | Mọi cảnh báo có dòng tiền ròng âm đều bị đánh trượt | `-16.466031` bị cắt thành `466031` — một số không tồn tại |
| Index khoá ngoại thiếu | Xoá 19.704 cảnh báo treo >3 phút | `detection_result.alert_id` không có index → ~4 tỷ lượt duyệt. Sau khi thêm: **0,65 giây** |
| `/dashboard` trả 500 | Trang chủ hỏng | Bảng release rỗng → `NULL` vào trường `int` |
| Hàng đợi trắng | 20.608 cảnh báo mà `/alerts` trả rỗng | Truy vấn khoá theo edge release; nhánh rule và ml có `transaction_id` NULL nên bị loại sạch |
| Badge sidebar = 0 | Cùng nguyên nhân trên | |
| Đồ thị mạng lưới trống | 0 nút, 0 cạnh | Cùng nguyên nhân: truy vấn hạt giống nối `alert.transaction_id`, mà **0/21.034** cảnh báo có giá trị này |
| 191 cảnh báo điểm 0 | Nằm đáy hàng đợi như không có gì | Thang tuyến tính từ 0 → trường hợp đúng bằng ngưỡng nhận 0 |
| Sự kiện nhật ký sai tên | Dòng thời gian đọc thành PASS rồi FAIL | Việc *bác bỏ khiếu nại* bị ghi nhầm thành `VALIDATION_PASS` |

---

## 10. Thành phần mới trong repo

**Module:**
`src/detection/rules.py` · `src/detection/rule_engine.py` · `src/detection/graph_loader.py`
`src/fusion/tri.py` · `src/investigation/typology_match.py` · `src/services/typology_assignment.py`

**Script:**
`run_rule_engine.py` · `load_graph_evidence.py` · `compute_rule_grid.py` ·
`train_fusion_tri.py` · `load_fusion_tri.py` · `load_edge_scores.py` ·
`calibrate_from_feedback.py`

**Migration:** 015 (sự kiện phản biện) · 016 (dấu vết nhóm hành vi) ·
017 (kho nhãn) · 018 (bằng chứng đồ thị) · 019 (index khoá ngoại)

**Kiểm thử:** 606 → **641 qua** (40 test mới cho nhánh rule, ánh xạ nhóm hành vi
và bộ nạp đồ thị).

Một test đang đỏ: `test_scientific_edge_benchmark_report_is_current`. Nó render
báo cáo benchmark và so với bản đã lưu; bản benchmark tham chiếu LI-Small đang
được sinh lại sau khi xoá artifact HI-Medium. Không phải lỗi mã, là artifact
chưa kịp có.

---

## 11. Giới hạn — nói trước để không bị hỏi vặn

1. **F1 0,137 (hợp nhất) và 0,297 (mô hình cạnh)** là điểm xuất phát. LI-Small
   loãng nên khó; đây là kết quả trung thực, không phải kết quả tốt.
2. **Isolation Forest không đóng góp** vào tổ hợp trên bộ dữ liệu này.
3. **Ngưỡng luật chưa qua thẩm định nghiệp vụ** — `RULE_THRESHOLDS` do kỹ thuật
   đặt (ngưỡng báo cáo 10.000 theo chuẩn CTR quen thuộc).
4. **Nhãn phản hồi chưa có ai đọc lại** — script đã có, nhưng chưa đủ nhãn thật.
5. **Điều tra bằng AI thường dừng ở `INSUFFICIENT_EVIDENCE`** trong 3 vòng lặp.
   Đường ống đã đưa đủ bằng chứng; phần còn lại là chất lượng trích dẫn của mô
   hình ngôn ngữ, và bộ phản biện bắt được — đúng như thiết kế.

---

## 12. Hướng cải thiện đề xuất

Theo thứ tự đáng thử:

1. **Đưa đặc trưng đồ thị vào mô hình cạnh.** Hiện hai nhánh tách rời; graph là
   nhánh mạnh nhất (PR-AUC 0,084 so với 0,015 của anomaly).
2. **Dịch ngưỡng theo khẩu vị nghiệp vụ.** Ngưỡng hiện tại cho recall 0,23 —
   đổi ngưỡng đổi được cân bằng precision/recall mà không cần huấn luyện lại.
3. **Tích luỹ nhãn thật** rồi chạy `calibrate_from_feedback.py`.
4. **Bổ sung danh sách quốc gia rủi ro cao** để mở khoá nhóm hành vi T06.
