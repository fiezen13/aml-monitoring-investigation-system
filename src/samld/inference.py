"""Suy luận nhánh SAML-D — nạp checkpoint MEGA-PNA + encoder, chấm lô giao dịch.

Model đồ thị cần NGỮ CẢNH đồ thị: ``predict_frame`` dựng đồ thị từ chính lô giao
dịch truyền vào rồi chấm mọi cạnh (§29 — không giả vờ chấm từng dòng rời). Đầu ra
CHỈ gồm xác suất AML + ngữ cảnh giao dịch; KHÔNG có FATF/sanctions/country risk.
"""

from __future__ import annotations

import json
import logging

import pandas as pd
import torch

from src.mega_pna.config import MegaPnaConfig
from src.mega_pna.model import MegaPna
from src.samld.config import SamldConfig, get_samld_config
from src.samld.encoders import EdgeEncoder
from src.samld.graph_builder import build_inference_graph
from src.samld.schemas import ModelSignal, SamldResult, TransactionContext

logger = logging.getLogger("fin07.samld.inference")


class SamldModelNotTrainedError(Exception):
    """Chưa có checkpoint SAML-D — cần chạy scripts.samld_benchmark trước."""


class SamlDetector:
    """Bộ chấm SAML-D đã nạp sẵn model + encoder + ngưỡng. Dựng một lần, tái dùng."""

    def __init__(self, config: SamldConfig | None = None, seed: int | None = None) -> None:
        self.config = config or get_samld_config()
        runs = self.config.model_dir / "runs"
        ckpts = sorted(runs.glob("seed*/model_seed*.pt")) if runs.exists() else []
        if not ckpts:
            raise SamldModelNotTrainedError(
                f"Không thấy checkpoint tại {runs}. Chạy: python -m scripts.samld_benchmark"
            )
        ckpt_path = ckpts[0] if seed is None else runs / f"seed{seed}" / f"model_seed{seed}.pt"
        checkpoint = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        mega_cfg = MegaPnaConfig(**checkpoint["config"])
        feature_names = list(checkpoint["feature_names"])
        self.model = MegaPna(
            # ego_ids=True (mặc định checkpoint): node feature = 1 (cấu trúc) + 1
            # (ego-id) = 2. Trước đây ghi cứng 1 → load_state_dict CRASH vì
            # node_embedding.weight của checkpoint là [hidden, 2]. Khớp đúng theo
            # cấu hình checkpoint (giống src/mega_pna/inference.py).
            node_features=2 if mega_cfg.ego_ids else 1,
            edge_features=len(feature_names),
            hidden_channels=mega_cfg.hidden_channels,
            num_layers=mega_cfg.num_layers,
            dropout=mega_cfg.dropout,
            node_degree_hist=checkpoint["node_degree_hist"],
            edge_degree_hist=checkpoint["edge_degree_hist"],
            edge_updates=mega_cfg.edge_updates,
        )
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.eval()
        self.encoder = EdgeEncoder.load(self.config.model_dir / "encoder")
        self.threshold = self._load_threshold()
        self.ego_ids = mega_cfg.ego_ids
        logger.info("Nạp SAML-D: %s, %d đặc trưng, ngưỡng %.4f", ckpt_path.name, len(feature_names), self.threshold)

    def _load_threshold(self) -> float:
        overall = self.config.artifact_dir / "overall_metrics.json"
        if overall.exists():
            return float(json.loads(overall.read_text(encoding="utf-8"))["operational_threshold"])
        return 0.5

    @torch.no_grad()
    def score_frame(self, df: pd.DataFrame) -> list[float]:
        """Chấm mọi giao dịch trong df (đã có cột canonical + đặc trưng dẫn xuất)."""
        graph, _ = build_inference_graph(df, self.encoder)
        if self.ego_ids:
            # node_features=2: cột cấu trúc + cột ego-id. Inference toàn đồ thị
            # không có "root" như lúc train qua loader, nên ego-id = 0 cho mọi
            # node (giữ đúng số chiều mà node_embedding kỳ vọng — KHÔNG cắt lại).
            ego = torch.zeros((graph["node"].num_nodes, 1))
            graph["node"].x = torch.cat([graph["node"].x, ego], dim=1)
        logits = self.model(graph)
        return torch.softmax(logits, dim=1)[:, 1].tolist()

    def predict_frame(self, df: pd.DataFrame) -> list[SamldResult]:
        """Trả kết quả có cấu trúc cho từng giao dịch (§26)."""
        scores = self.score_frame(df)
        results: list[SamldResult] = []
        for (_, row), prob in zip(df.iterrows(), scores, strict=True):
            xb = bool(row["cross_border"] > 0.5)
            cm = bool(row["currency_mismatch"] > 0.5)
            ctx = TransactionContext(
                sender_account=str(row["sender_account"]),
                receiver_account=str(row["receiver_account"]),
                amount=float(row["amount"]),
                sender_country=str(row["sender_country"]),
                receiver_country=str(row["receiver_country"]),
                cross_border=xb,
                payment_currency=str(row["payment_currency"]),
                received_currency=str(row["received_currency"]),
                currency_mismatch=cm,
                payment_type=str(row["payment_type"]),
            )
            evidence = [ModelSignal(type="network_anomaly", value=round(float(prob), 6))]
            if xb:
                evidence.append(ModelSignal(type="cross_border", value=True))
            if cm:
                evidence.append(ModelSignal(type="currency_mismatch", value=True))
            results.append(
                SamldResult(
                    transaction_id=str(row.get("transaction_id", "")),
                    aml_probability=round(float(prob), 6),
                    prediction="suspicious" if prob >= self.threshold else "normal",
                    threshold=round(self.threshold, 6),
                    transaction_context=ctx,
                    model_evidence=evidence,
                )
            )
        return results
