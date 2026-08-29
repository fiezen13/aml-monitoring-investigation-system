"""Pha 2/4 — chấm GNN cục bộ IBM MEGA-PNA (HI-Medium), kiến trúc medallion.

Raw ở BRONZE Parquet, đồ thị + điểm IN-MEMORY, chỉ cạnh gắn cờ → alert/aml_case (PG).

KHÁC SAML-D: z-norm của MEGA-PNA là GRAPH-RELATIVE (tính trên chính đồ thị) nên KHÔNG
mã hoá cố định được — mỗi lượt chấm dựng lại đồ thị từ đặc trưng THÔ và để `_graph`
z-norm trên cửa sổ hiện tại. Nút = TÀI KHOẢN thật (From Bank:Account, có trong bảng
`account`) nên IBM cũng bồi tụ được VỤ VIỆC như SAML-D.

Nguồn Bronze cho IBM: hàng đã format (EdgeID + 4 đặc trưng đã mã hoá, để khớp đúng
encoding checkpoint) + khoá tài khoản lấy từ CSV thô (căn theo EdgeID = số dòng).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np
import torch

from src.mega_pna.config import MegaPnaConfig
from src.mega_pna.data import PAPER_FEATURES, _graph
from src.mega_pna.model import MegaPna
from src.mega_pna.training import _loader, evaluate, resolve_device
from src.streaming.samld_score import ScoredEdge

logging.basicConfig(
    level=os.getenv("STREAM_LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger("fin07.streaming.ibm_score")

MODEL_VERSION = "ibm-mega-pna-hi-medium-v1"
DATASET = "ibm_hi_medium"
CKPT = Path(os.getenv("IBM_MEGA_CKPT", "models/mega-pna/Medium_HI/paper/seed_42.pt"))
FEATURES = list(PAPER_FEATURES)  # Timestamp, Amount Received, Received Currency, Payment Format
THRESHOLDS_FILE = Path(os.getenv("STREAM_THRESHOLDS", "artifacts/streaming/thresholds.json"))


def load_model() -> Any:
    ck = torch.load(CKPT, map_location="cpu", weights_only=False)
    cfg = MegaPnaConfig(**ck["config"])
    model = MegaPna(
        node_features=2 if cfg.ego_ids else 1,
        edge_features=len(FEATURES),
        hidden_channels=cfg.hidden_channels,
        num_layers=cfg.num_layers,
        dropout=cfg.dropout,
        node_degree_hist=ck["node_degree_hist"],
        edge_degree_hist=ck["edge_degree_hist"],
        edge_updates=cfg.edge_updates,
    )
    model.load_state_dict(ck["model_state_dict"])
    model.eval()
    score_cfg = MegaPnaConfig(**{**ck["config"], "num_workers": 0, "batch_size": 4096})
    return model, score_cfg, cfg.ego_ids


def _load_threshold() -> tuple[int, float]:
    wd = int(os.getenv("IBM_WARM_DEGREE", "0")) or None
    st = os.getenv("IBM_THRESHOLD")
    if wd and st:
        return wd, float(st)
    if THRESHOLDS_FILE.exists():
        cfg = json.loads(THRESHOLDS_FILE.read_text(encoding="utf-8")).get("ibm", {})
        return (wd or int(cfg.get("warm_degree", 2))), (float(st) if st else float(cfg.get("stream_threshold", 0.5)))
    return (wd or 2), (float(st) if st else 0.5)


class IBMStreamScorer:
    """Scorer in-memory cho IBM MEGA-PNA: giữ cạnh thô, z-norm graph-relative khi chấm."""

    def __init__(self):
        self.model, self.config, self.ego_ids = load_model()
        self.device = resolve_device("cpu")
        self.warm_degree, self.threshold = _load_threshold()
        # trạng thái đồ thị in-mem
        self.node_index: dict[str, int] = {}
        self.in_deg: dict[int, int] = {}
        self.out_deg: dict[int, int] = {}
        self._src: list[int] = []
        self._dst: list[int] = []
        self._attr: list[list[float]] = []  # 4 đặc trưng THÔ (chưa z-norm)
        self._y: list[int] = []
        self._meta: list[dict] = []  # source_id, from_key, to_key, occurred_at
        self._provisional: set[int] = set()
        logger.info(
            "IBM scorer in-mem · num_neighbors=%s · ngưỡng %.4f · warm_degree %d",
            self.config.num_neighbors,
            self.threshold,
            self.warm_degree,
        )

    def _node(self, key: str) -> int:
        idx = self.node_index.get(key)
        if idx is None:
            idx = len(self.node_index)
            self.node_index[key] = idx
            self.in_deg[idx] = 0
            self.out_deg[idx] = 0
        return idx

    def process_events(self, events: list[dict]) -> list[ScoredEdge]:
        """Nạp lô cạnh IBM (đã có khoá tài khoản + 4 đặc trưng mã hoá) + chấm."""
        positions = []
        for e in events:
            fk, tk = str(e["from_account_key"]), str(e["to_account_key"])
            if fk == tk:
                continue
            s, d = self._node(fk), self._node(tk)
            p = len(self._src)
            self._src.append(s)
            self._dst.append(d)
            self._attr.append(
                [
                    float(e["f_timestamp"]),
                    float(e["f_amount_received"]),
                    float(e["f_received_currency"]),
                    float(e["f_payment_format"]),
                ]
            )
            self._y.append(int(e.get("is_laundering", 0) or 0))
            self._meta.append(
                {"source_id": str(e["source_id"]), "from_key": fk, "to_key": tk, "occurred_at": e.get("occurred_at")}
            )
            self.out_deg[s] += 1
            self.in_deg[d] += 1
            positions.append(p)
        return self._score(np.array(positions, dtype=np.int64)) if positions else []

    @torch.no_grad()
    def _score(self, positions: np.ndarray) -> list[ScoredEdge]:
        n = len(self._src)
        edge_index = torch.tensor([self._src, self._dst], dtype=torch.long)
        edge_attr = torch.tensor(self._attr, dtype=torch.float32)  # _graph sẽ z-norm
        labels = torch.tensor(self._y, dtype=torch.long)
        ts = edge_attr[:, 0].clone()
        data = _graph(edge_index, edge_attr, labels, ts, end=n, num_nodes=len(self.node_index))
        pt = torch.as_tensor(positions, dtype=torch.long)
        out = evaluate(
            self.model,
            _loader(data, pt, self.config, shuffle=False),
            pt,
            self.device,
            ego_ids=self.ego_ids,
            threshold=self.threshold,
        )
        id2s = {int(i): float(s) for i, s in zip(out.edge_ids, out.scores)}
        result = []
        for p in positions:
            p = int(p)
            m = self._meta[p]
            fi, fo = self.in_deg[self._src[p]], self.out_deg[self._src[p]]
            ti, to = self.in_deg[self._dst[p]], self.out_deg[self._dst[p]]
            warm = min(fi + fo, ti + to) >= self.warm_degree
            (self._provisional.discard if warm else self._provisional.add)(p)
            sc = id2s.get(p, 0.0)
            result.append(
                ScoredEdge(
                    source_id=m["source_id"],
                    from_account=m["from_key"],
                    to_account=m["to_key"],
                    amount=float(self._attr[p][1]),
                    payment_currency="",
                    receiving_currency="",
                    payment_format="",
                    occurred_at=str(m["occurred_at"]),
                    is_laundering=int(self._y[p]),
                    score=sc,
                    triggered=bool(warm and sc >= self.threshold),
                    warm=warm,
                    from_in=fi,
                    from_out=fo,
                    to_in=ti,
                    to_out=to,
                )
            )
        return result

    @torch.no_grad()
    def rescore_warmed(self) -> list[ScoredEdge]:
        cand = np.array(
            [
                p
                for p in self._provisional
                if min(
                    self.in_deg[self._src[p]] + self.out_deg[self._src[p]],
                    self.in_deg[self._dst[p]] + self.out_deg[self._dst[p]],
                )
                >= self.warm_degree
            ],
            dtype=np.int64,
        )
        return self._score(cand) if len(cand) else []

    @property
    def num_edges(self) -> int:
        return len(self._src)

    @property
    def num_nodes(self) -> int:
        return len(self.node_index)
