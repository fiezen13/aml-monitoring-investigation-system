"""Test đường ống huấn luyện Multi-PNA+EU chạy end-to-end trên tập nhỏ (CPU).

Không kiểm chất lượng model — chỉ chứng minh: dữ liệu SAML-D → đồ thị → vòng
huấn luyện mega_pna → report + checkpoint, tất cả khớp hợp đồng.
"""

from __future__ import annotations

from pathlib import Path

from src.mega_pna.config import MegaPnaConfig
from src.samld.config import SamldConfig
from src.samld.data import load_samld
from src.samld.graph_builder import build_graph
from src.samld.split import temporal_split
from src.samld.training import train_seed


def test_train_one_epoch_end_to_end(raw_samld_csv: Path, tmp_path: Path) -> None:
    cfg = SamldConfig(raw_csv=raw_samld_csv)
    bundle = build_graph(temporal_split(load_samld(cfg), cfg))
    mega_config = MegaPnaConfig(
        hidden_channels=20,
        num_layers=2,
        num_neighbors=(10, 10),
        batch_size=64,
        epochs=1,
        patience=0,
        num_workers=0,
        edge_updates=True,
    )
    report = train_seed(bundle, mega_config, seed=42, out_dir=tmp_path / "run", device="cpu")

    # report có đủ khối kết quả chính
    for key in ("validation_at_best", "test_paper_protocol", "test_validation_threshold", "operational_budget"):
        assert key in report
    # checkpoint + predictions được ghi ra
    assert (tmp_path / "run" / "model_seed42.pt").exists()
    assert (tmp_path / "run" / "predictions_seed42.parquet").exists()
    # edge_updates thật sự bật trong config đã dùng
    assert report["config"]["edge_updates"] is True
