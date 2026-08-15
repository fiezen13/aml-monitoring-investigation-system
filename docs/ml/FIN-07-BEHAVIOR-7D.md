# FIN-07 Behaviour Isolation Forest 7 ngày

Behaviour dùng duy nhất cửa sổ rolling 7 ngày cho baseline được review. Feature
được tính point-in-time trên lịch sử liên tục; split chỉ được gán sau khi tạo
snapshot. Model fit trên train, threshold chọn trên validation và test chỉ được
đánh giá một lượt sau khi threshold đã cố định.

## Huấn luyện lại từ LI-Small

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python3 scripts/run_task1_etl.py \
  --raw data/raw/ibm-aml/LI-Small_Trans.csv \
  --db data/processed/aml.duckdb \
  --seed 42 \
  --strict-li-small-stats

make behavior-train
```

Lệnh trực tiếp:

```bash
python3 scripts/train_behavior_7d.py \
  --db data/processed/aml.duckdb \
  --output-dir data/processed/behavior-7d \
  --reports-dir reports/behavior-7d \
  --target-recall 0.80 \
  --precision-at-k 50,100,500,1000 \
  --require-full-li-small
```

Artifact mới nằm trong `data/processed/behavior-7d/` và báo cáo nằm trong
`reports/behavior-7d/`; pipeline không ghi đè handoff gốc. Vì LI-Small có lịch
sử hiệu dụng rất ngắn, manifest sẽ ghi rõ nếu train chưa có snapshot tích lũy
đủ trọn cửa sổ 7 ngày. Đây vẫn là research baseline, không phải model đã được
kiểm định trên dữ liệu ngân hàng thật.
