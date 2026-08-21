# SAML-D Model — Multi-PNA + Edge Updates (Multi-PNA+EU)

Tài liệu nguồn gốc & tái lập cho nhánh phát hiện AML trên SAML-D.

## Original source

- **IBM Multi-GNN** — <https://github.com/IBM/Multi-GNN>. Kiến trúc MEGA-PNA
  (Multi-Edge Graph Aggregation PNA) với cập nhật cạnh, phân loại **cạnh** trên
  đồ thị giao dịch AML.
- **Benchmark tham chiếu**: TransXion — *A High-Fidelity Graph Benchmark for
  Realistic Anti-Money Laundering*. Trên SAML-D, Multi-PNA+EU đạt (tham chiếu, **KHÔNG**
  phải kết quả repo này): ROC-AUC ≈ 0.999984, AP ≈ 0.994835, F1 ≈ 0.976988.
  Các số này chỉ để đối chiếu; kết quả reproduction của FIN-07 do chính pipeline
  này sinh ra (xem `artifacts/samld/benchmark_report.md`).

## Files reused / adapted

Kiến trúc và vòng huấn luyện **tái dùng nguyên** từ module MEGA-PNA có sẵn của
repo (`src/mega_pna/`) — vốn đã là một hiện thực Multi-PNA+EU bám sát IBM
Multi-GNN. Nhánh SAML-D **không** viết lại GNN; chỉ thêm tầng dữ liệu.

| Thành phần | Nguồn | Ghi chú |
|---|---|---|
| `MegaPna`, `MegaPnaLayer`, `PnaMultiEdgeAggregation` | `src/mega_pna/model.py` | PNA hai chiều (xuôi+ngược), gộp cạnh song song, **edge update MLP** (`edge_updates=True`) |
| Vòng huấn luyện, `LinkNeighborLoader`, ego-id, early-stop | `src/mega_pna/training.py` | `train_one_seed` dùng lại y nguyên |
| Metrics (best-F1 threshold, budget, PR-AUC) | `src/mega_pna/metrics.py` | mở rộng thêm F2/MCC/FPR/Brier ở `src/samld/evaluate.py` |
| `MegaPnaConfig` | `src/mega_pna/config.py` | tái dùng; SAML-D nạp từ YAML |

## Files added (nhánh SAML-D)

`src/samld/`: `schema.py` (canonical + hàng rào rò rỉ nhãn), `data.py` (loader +
dẫn xuất đặc trưng), `split.py` (chia thời gian nghiêm ngặt), `encoders.py`
(one-hot fit-trên-train), `graph_builder.py` (đồ thị → `MegaPnaDataBundle`),
`training.py`, `evaluate.py`, `baselines.py`, `ablation.py`, `plots.py`,
`config/*.yaml`. Script: `scripts/samld_benchmark.py`.

## Graph representation

- **Node = tài khoản**; **cạnh = giao dịch có hướng** (người gửi → người nhận).
- **Country KHÔNG phải node** — là thuộc tính categorical của cạnh (ngữ cảnh).
- Quan hệ xuôi `("node","to","node")` + ngược `("node","rev_to","node")` (đảo chiều)
  để truyền tin hai chiều, khớp `to_hetero` của bản gốc.
- Node feature = vector 1 (cấu trúc); ego-id thêm ở tầng loader.

## Input features (đặc trưng CẠNH) — không có nhãn

Số: `amount_log` (log1p), `hour`, `day_of_week`, `day_of_month`, `elapsed_days`.
Nhị phân: `cross_border` (sender_country≠receiver_country), `currency_mismatch`.
Categorical (one-hot, fit trên train): `payment_type`, `payment_currency`,
`received_currency`, `sender_country`, `receiver_country`.

**Chống rò rỉ**: `Is_laundering`/`Laundering_type` KHÔNG bao giờ là đặc trưng
(kiểm bằng `tests/test_samld/test_leakage.py`). Country **không** map sang bất kỳ
danh sách rủi ro FATF/sanctions cứng nào — chỉ là mã categorical.

## Loss / sampler / threshold

- **Loss**: `CrossEntropyLoss` với trọng số lớp `[1.0, 7.0]` (mất cân bằng ~0,1% dương).
  Hạ tầng hỗ trợ đổi sang focal/pos_weight qua config.
- **Sampler**: `LinkNeighborLoader`, `num_neighbors=[100,100]`, minibatch trên đồ thị
  toàn phần; validation/test giữ phân phối tự nhiên (không undersample).
- **Threshold**: chọn trên **validation** (chiến lược F1, có tuỳ chọn F2/recall-target),
  đóng băng, áp cho test đúng một lần. Không tune trên test.

## Hyperparameters (mặc định, `src/samld/config/default.yaml`)

`hidden_channels=20` (chia hết 5 tower PNA), `num_layers=2`, `dropout=0.28`,
`edge_updates=true`, `reverse_message_passing=true`, `ego_ids=true`,
`batch_size=8192`, `num_neighbors=[100,100]`, `learning_rate=0.0008`,
`epochs=80` (early-stop `patience=8`), `class_weight_laundering=7.0`.

## Split & reproducibility

Chia **theo thời gian** 70/15/15 với ràng buộc `max(train) < min(val) < min(test)`
(assert trong `src/samld/split.py`). Seed đặt cho Python/NumPy/PyTorch/CUDA qua
`set_seed`. Benchmark mặc định 3 seed `[42, 1337, 2026]`, báo cáo mean ± std.
