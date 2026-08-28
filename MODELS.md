# Bản đồ Model — FIN-07

> Repo có model rải ở vài nơi (`models/`, `data/models/`, `if_handoff/`, `graph_handoff/`,
> `models/mega-pna/`). Đây **không phải lộn xộn cần xoá** — mà là **lineage ML có tài liệu**
> (bàn giao, runbook, provenance nạp dữ liệu). File này chỉ rõ **3 model đang phục vụ** và
> đánh dấu phần **legacy** (giữ lại có lý do). Cập nhật: 22/08/2026.

## Điều quan trọng nhất

**Trên production, API/web/worker KHÔNG nạp file model lúc chạy.** Chúng đọc **điểm đã tính
sẵn** trong Cloud SQL (`transaction_model_score`, `bitcoin_scored_tx`, `edge_model_release`).
File model chỉ cần cho **script chấm/huấn luyện OFFLINE** (khi muốn tạo lại release). Vì vậy
xoá nhầm file model không làm sập site đang chạy — nhưng **sẽ phá runbook tạo lại dữ liệu**.

---

## ✅ 3 model ĐANG PHỤC VỤ (3 nhánh)

### 1. Bitcoin — Random Forest (Elliptic)
| | |
|---|---|
| File | `data/models/bitcoin_elliptic/elliptic_rf.joblib` (+ `selected_features.json`, `feature_distribution.json`, `feature_registry.json`) |
| Loại | Random Forest, chấm độc lập từng giao dịch |
| Code nạp | `src/bitcoin_aml/scoring.py` (streaming, local), `scripts/build_elliptic_scored.py` (batch) |
| Ghi vào | bảng `bitcoin_scored_tx` · release `REL-BTC-ELLIPTIC-ORIG-V1` (status `reference`) · version `bitcoin-elliptic-rf-v1` |
| Console | trang **Truy vết tài sản mã hoá** (`/crypto`) |

### 2. IBM AML — Currency-native Edge (đang phục vụ hàng đợi chính)
| | |
|---|---|
| File | `models/fin07_currency_native_policy_edge_li_small_v1.joblib` |
| Loại | Edge model chấm từng giao dịch (đặc trưng nhân-quả theo tiền tệ) |
| Code nạp | `src/models/currency_native_edge.py`, `scripts/{train,score,load_currency_native_edge_release}.py` |
| Ghi vào | bảng `transaction_model_score` · release **active** `REL-EDGE-…` (dataset "IBM AML LI-Small currency-native") |
| Console | **Tổng quan / Tra cứu giao dịch / Cảnh báo** sống nhờ bảng này |

### 3. SAML-D — MEGA-PNA (mạng đồ thị chấm cạnh)
| | |
|---|---|
| File | `data/models/samld/runs/seed{42,1337,2026}/model_seed*.pt` + `data/models/samld/encoder/` |
| Loại | GNN MEGA-PNA (Multi-PNA+EU), chấm cạnh trên đồ thị |
| Code nạp | `src/samld/inference.py` (`SamlDetector`), `scripts/samld_benchmark.py` |
| Release | `REL-GRAPH-SAMLD-V1` (status `reference`) · version `samld-multi-pna-eu-v1` |
| ⚠️ Lưu ý | `SamlDetector` hiện hard-code `node_features=1` nhưng checkpoint train `ego_ids=True` (cần 2) → **nạp checkpoint bị lỗi**. Bản đúng có ở `src/mega_pna/inference.py:46`. Cần sửa trước khi chấm lại. |

> `data/models/*` và `data/processed/*` bị `.gitignore` chặn (`data/*`) — **không** nằm trong
> git, chỉ có trên máy/Drive. `models/*` (gồm model IBM active) **có** track trong git.

---

## 🗄️ LEGACY — giữ lại, KHÔNG xoá (có lý do)

Các phần dưới đây **không còn phục vụ** nhưng **không phải rác**: chúng bị runbook/bàn giao/chuỗi
nạp dữ liệu tham chiếu. Xoá sẽ gãy runbook hoặc đụng phần của đồng đội.

| Thư mục / file | Là gì | Vì sao GIỮ |
|---|---|---|
| `src/fusion/` + `models/fin07_if_graph_fusion_v1/v2.joblib`, `fin07_if_7d_v2.joblib`, `fin07_graph_7d_v2.joblib`, `configs/fusion/`, `reports/fusion*`, `scripts/{train_fusion_v2,build_fusion_release,load_fusion_release,…}` | Nhánh **IF + Graph fusion CŨ** (tiền thân của IBM edge) | `scripts/load_edge_scores.py`, `load_graph_evidence.py`, `services/typology_assignment.py` **đều tham chiếu `load_fusion_release.py`** → nằm trong **chuỗi nạp dữ liệu prod**. Xoá = phá runbook nạp lại DB. |
| `graph_handoff/graph_histgb_v1.joblib` | Model graph bàn giao | `src/detection/graph_loader.py` dùng — **phần detection của đồng đội**, không tự đụng. |
| `if_handoff/` | Model Isolation Forest bàn giao cũ | Runbook (`LI_SMALL_E2E_RUNBOOK.md`) đánh dấu "đừng đọc model cũ từ đây" — mốc lịch sử có tài liệu. |
| `models/mega-pna/…/seed_42.pt` | Checkpoint **bàn giao MEGA-PNA** (paper) | Tài liệu ở `docs/MEGA_PNA_BAN_GIAO.md`, `docs/ml/MEGA_PNA_RUNBOOK.md`; `build_mega_pna_release.py` dùng đường dẫn này. MEGA-PNA là kiến trúc SAML-D dùng. |
| `data/processed/behavior-7d/` | Isolation Forest rolling 7 ngày (nhánh behavior cũ) | Không track git; `make behavior-train` tái tạo. |

**Muốn dọn thật sự** các phần legacy: phải (1) xác nhận prod đã nạp dữ liệu qua đường nào
(`load_fusion_release` hay `load_currency_native_edge_release` from-scratch), (2) hỏi đồng đội
về `graph_handoff`/detection, rồi mới xoá theo từng cụm — không xoá loạt.

---

## 📦 Requirements — KHÔNG lộn xộn (tách có chủ đích)

| File | Dùng cho |
|---|---|
| `requirements.txt` | Chạy production — **Docker chỉ cài file này** |
| `requirements-dev.txt` | Công cụ dev/test (`-r requirements.txt`) |
| `requirements-mega-pna.txt` | Huấn luyện MEGA-PNA offline (CPU) |
| `requirements-mega-pna-sampler.txt` | `torch-scatter`… (cài sau mega-pna) |
| `requirements-mega-pna-cuda118.txt` | Bản GPU CUDA 11.8 |

Gộp lại sẽ **hỏng image prod** (không thể nhét torch-scatter/CUDA vào runtime). Giữ nguyên.
