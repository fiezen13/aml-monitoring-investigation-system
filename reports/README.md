# Quy ước cho thư mục này

## Con số nào được trích dẫn

Chỉ báo cáo mang `"schema_version": "fin07.benchmark.v1"`, và chỉ khoá
**`headline`** trong đó.

Mọi giá trị khác — kể cả `f1` nằm ở `diagnostics` hay `selection` — **không được
đưa vào tài liệu, slide hay báo cáo**.

## Vì sao có quy ước này

Kiểm kê ngày 18/08/2026 tìm thấy **19 báo cáo với 4 đơn vị đánh giá khác nhau**:

| Đơn vị | Số báo cáo | Dải F1 |
|---|---|---|
| Giao dịch | 6 | 0,0318 – 0,1870 |
| Tài khoản-mốc | 9 | 0,0007 – 0,1469 |
| Tài khoản | 3 | 0,0197 – 0,0834 |
| Ring | 1 | — |

Không cái nào so được với cái nào, nhưng chúng vẫn bị đặt cạnh nhau.

Tệ hơn, **một file chứa chín giá trị `f1`** ở chín đường dẫn khác nhau:

```
selection.trials[0].validation.f1  = 0,1273
selection.trials[3].validation.f1  = 0,2054
test_primary_seed.f1               = 0,3022   ← con số đúng
test_over_seeds.runs[2].f1         = 0,2768
```

Không quy ước nào nói cái nào chính thức, nên bộ đọc tự động lấy nhầm **0,1273
thay vì 0,3022**.

## Bốn quy tắc

1. **Đơn vị chung là `account_window`** — đơn vị của bảng `alert`. Mô hình chấm
   cạnh phải chiếu lên tài khoản rồi mới đo. Được báo cáo thêm ở `transaction`
   để đối chiếu với bài báo, nhưng con số đem so sánh luôn là đơn vị chung.
2. **Đúng một chỗ chứa con số chính thức:** `headline`.
3. **Tự khai đủ ngữ cảnh** — bộ dữ liệu và mã băm, mốc chia tập kèm số dòng và
   số nhãn dương từng tập, quy tắc quyết định, ngưỡng và nơi chọn ngưỡng, mã băm
   mô hình, commit mã nguồn.
4. **Dãy ngân sách cố định** cho mọi mô hình: 100, 250, 500, 1.000, 2.500, 5.000,
   10.000, 25.000, 50.000. Đây mới là con số so sánh được thật, vì nó bỏ ngưỡng
   ra khỏi phép so: *rà N cảnh báo thì bắt được bao nhiêu?*

## Cách sinh báo cáo đúng chuẩn

```python
from src.benchmark.standard import build_report

report = build_report(
    component="mega_pna",
    unit="account_window",
    dataset={"name": "HI-Medium", "sha256": ..., "rows": ..., "positives": ...},
    split={"protocol": "...", "train": {...}, "validation": {...}, "test": {...}},
    decision_rule="threshold_from_validation",
    threshold_value=...,
    threshold_selected_on="validation",
    labels=..., scores=...,
    provenance={"model_sha256": ..., "git_commit": ...},
)
```

`build_report` tự kiểm trước khi trả về, nên không dựng được báo cáo sai chuẩn.

## Kiểm

```bash
python scripts/validate_benchmarks.py            # liệt kê, chấm đúng/sai
python scripts/validate_benchmarks.py --strict   # báo cáo cũ cũng tính là lỗi
```

`ci/lint.sh` gọi bản không `--strict`: báo cáo sai chuẩn làm CI đỏ, còn báo cáo
cũ chỉ bị liệt kê.

## Báo cáo cũ

**Không xoá** — chúng là dấu vết của những gì đã chạy. Chỉ là không được trích
dẫn. Chuyển dần sang chuẩn mới khi chạy lại từng nhánh.
