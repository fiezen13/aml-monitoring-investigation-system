"""Pha 2 — chấm GNN cục bộ SAML-D, kiến trúc medallion: raw ở BRONZE (Parquet),
đồ thị + điểm IN-MEMORY, CHỈ cạnh gắn cờ mới thành alert/case xuống Postgres.

Trước đây scorer đọc/ghi Postgres cho cả raw lẫn điểm (sai kiến trúc: PG chỉ nên
giữ output). Bản này:
  * dựng `IncrementalGraph` in-memory (encoder fit-train cố định → thêm cạnh không
    đổi điểm cũ), num_neighbors=[25,25] đúng cơ chế train;
  * ngưỡng streaming THEO NGỮ CẢNH (warm_degree) từ artifacts/streaming/thresholds.json;
  * warm-up: cạnh cold → provisional, chấm lại khi endpoint đủ dày (in-mem);
  * trả `ScoredEdge` cho tầng bồi tụ vụ việc — KHÔNG tự ghi Postgres.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from src.mega_pna.config import MegaPnaConfig
from src.mega_pna.model import MegaPna
from src.mega_pna.training import _loader, evaluate, resolve_device
from src.samld.config import get_samld_config
from src.samld.encoders import EdgeEncoder
from src.samld.schema import COLS
from src.streaming.incremental_graph import IncrementalGraph

logging.basicConfig(level=os.getenv("STREAM_LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("fin07.streaming.samld_score")

MODEL_VERSION = "samld-multi-pna-eu-v1"
ORIGIN_ENV = os.getenv("SAMLD_ORIGIN", "2022-10-07T10:35:19")
THRESHOLDS_FILE = Path(os.getenv("STREAM_THRESHOLDS", "artifacts/streaming/thresholds.json"))


@dataclass
class ModelCtx:
    model: MegaPna
    encoder: EdgeEncoder
    config: MegaPnaConfig
    threshold: float
    ego_ids: bool
    device: Any


@dataclass
class ScoredEdge:
    """Kết quả chấm một cạnh — đủ để tầng bồi tụ dựng alert/case (không cần DB raw)."""
    source_id: str
    from_account: str
    to_account: str
    amount: float
    payment_currency: str
    receiving_currency: str
    payment_format: str
    occurred_at: str
    is_laundering: int
    score: float
    triggered: bool
    warm: bool
    from_in: int
    from_out: int
    to_in: int
    to_out: int


def load_model(seed: int | None = None) -> ModelCtx:
    cfg = get_samld_config()
    runs = cfg.model_dir / "runs"
    ckpts = sorted(runs.glob("seed*/model_seed*.pt"))
    if not ckpts:
        raise RuntimeError(f"Không thấy checkpoint SAML-D tại {runs}")
    ckpt_path = ckpts[0] if seed is None else runs / f"seed{seed}" / f"model_seed{seed}.pt"
    ck = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    mc = MegaPnaConfig(**ck["config"])
    fn = list(ck["feature_names"])
    model = MegaPna(
        node_features=2 if mc.ego_ids else 1,
        edge_features=len(fn),
        hidden_channels=mc.hidden_channels,
        num_layers=mc.num_layers,
        dropout=mc.dropout,
        node_degree_hist=ck["node_degree_hist"],
        edge_degree_hist=ck["edge_degree_hist"],
        edge_updates=mc.edge_updates,
    )
    model.load_state_dict(ck["model_state_dict"])
    model.eval()
    enc = EdgeEncoder.load(cfg.model_dir / "encoder")
    thr = 0.5
    overall = cfg.artifact_dir / "overall_metrics.json"
    if overall.exists():
        thr = float(json.loads(overall.read_text(encoding="utf-8"))["operational_threshold"])
    score_cfg = MegaPnaConfig(**{**ck["config"], "num_workers": 0, "batch_size": 4096})
    logger.info("Nạp SAML-D %s · ngưỡng batch %.4f", ckpt_path.name, thr)
    return ModelCtx(model, enc, score_cfg, thr, mc.ego_ids, resolve_device("cpu"))


def load_thresholds(batch_default: float) -> tuple[int, float]:
    """(warm_degree, stream_threshold) đã hiệu chỉnh. Env ghi đè."""
    wd = int(os.getenv("SAMLD_WARM_DEGREE", "0")) or None
    st = os.getenv("SAMLD_STREAM_THRESHOLD")
    if wd and st:
        return wd, float(st)
    if THRESHOLDS_FILE.exists():
        cfg = json.loads(THRESHOLDS_FILE.read_text(encoding="utf-8")).get("samld", {})
        return (wd or int(cfg.get("warm_degree", 2))), (float(st) if st else float(cfg.get("stream_threshold", batch_default)))
    logger.warning("Chưa có %s — dùng ngưỡng batch %.4f.", THRESHOLDS_FILE, batch_default)
    return (wd or 2), batch_default


def _rows_from_events(events: list[dict], base_key: int) -> pd.DataFrame:
    """Sự kiện canonical → khung cột mà reconstruct_samld_df cần (bỏ self-loop)."""
    df = pd.DataFrame({
        "stream_txn_id": np.arange(base_key, base_key + len(events)),
        "source_transaction_id": [e.get("transaction_id") or e.get("source_transaction_id") for e in events],
        "from_account_key": [f"{e['from_bank']}:{e['from_account']}" for e in events],
        "to_account_key": [f"{e['to_bank']}:{e['to_account']}" for e in events],
        "occurred_at": [e.get("event_time") for e in events],
        "amount_paid": [float(e.get("amount_paid", 0) or 0) for e in events],
        "payment_currency": [e.get("payment_currency", "") for e in events],
        "amount_received": [float(e.get("amount_received", 0) or 0) for e in events],
        "receiving_currency": [e.get("receiving_currency", "") for e in events],
        "payment_format": [e.get("payment_format", "") for e in events],
        "is_laundering": [int(e.get("is_laundering", 0) or 0) for e in events],
    })
    return df[df["from_account_key"] != df["to_account_key"]].reset_index(drop=True)


def reconstruct_samld_df(rows: pd.DataFrame, origin: datetime) -> pd.DataFrame:
    """rows canonical → df + đặc trưng dẫn xuất cho encoder."""
    df = pd.DataFrame()
    fk = rows["from_account_key"].astype(str).str.split(":", n=1, expand=True)
    tk = rows["to_account_key"].astype(str).str.split(":", n=1, expand=True)
    df["transaction_id"] = np.arange(len(rows))
    df["stream_txn_id"] = rows["stream_txn_id"].to_numpy()
    df[COLS.sender_country] = fk[0]
    df[COLS.sender_account] = fk[1]
    df[COLS.receiver_country] = tk[0]
    df[COLS.receiver_account] = tk[1]
    df[COLS.amount] = pd.to_numeric(rows["amount_paid"], errors="coerce").fillna(0.0)
    df[COLS.payment_currency] = rows["payment_currency"].astype(str)
    df[COLS.received_currency] = rows["receiving_currency"].astype(str)
    df[COLS.payment_type] = rows["payment_format"].astype(str)
    ts = pd.to_datetime(rows["occurred_at"], utc=True, errors="coerce").dt.tz_localize(None)
    df[COLS.timestamp] = ts.to_numpy()
    df["amount_log"] = np.log1p(df[COLS.amount].clip(lower=0))
    df["hour"] = ts.dt.hour.fillna(0).astype("float32").to_numpy()
    df["day_of_week"] = ts.dt.dayofweek.fillna(0).astype("float32").to_numpy()
    df["day_of_month"] = ts.dt.day.fillna(1).astype("float32").to_numpy()
    df["elapsed_days"] = ((ts - pd.Timestamp(origin)).dt.total_seconds() / 86400.0).fillna(0).astype("float32").to_numpy()
    df["cross_border"] = (df[COLS.sender_country] != df[COLS.receiver_country]).astype("float32")
    df["currency_mismatch"] = (df[COLS.payment_currency] != df[COLS.received_currency]).astype("float32")
    return df


class BronzeStreamScorer:
    """Scorer in-memory: nạp cạnh từ Bronze, chấm, trả ScoredEdge (không đụng PG)."""

    def __init__(self, ctx: ModelCtx | None = None):
        self.ctx = ctx or load_model()
        self.origin = pd.Timestamp(ORIGIN_ENV)
        self.warm_degree, self.stream_threshold = load_thresholds(self.ctx.threshold)
        self.G = IncrementalGraph(feature_dim=self.ctx.encoder.num_features)
        self._next = 0
        self._meta: dict[int, dict] = {}     # position -> raw fields (cho re-score)
        self._provisional: set[int] = set()  # position cold, chờ warm
        logger.info("Scorer in-mem · ngưỡng streaming %.5f · warm_degree %d", self.stream_threshold, self.warm_degree)

    def _add(self, rows: pd.DataFrame) -> np.ndarray:
        df = reconstruct_samld_df(rows, self.origin)
        attr = self.ctx.encoder.transform(df).astype(np.float32)
        keys = rows["stream_txn_id"].to_numpy()
        pos = self.G.add(keys, rows["from_account_key"].tolist(), rows["to_account_key"].tolist(),
                         attr, rows["is_laundering"].to_numpy(), df["elapsed_days"].to_numpy())
        # lưu raw theo position để bồi tụ + re-score
        for p, (_, r) in zip(pos, rows.iterrows()):
            self._meta[int(p)] = r.to_dict()
        return pos

    def _score(self, positions: np.ndarray) -> dict[int, float]:
        if len(positions) == 0:
            return {}
        data = self.G.hetero()
        pt = torch.as_tensor(positions, dtype=torch.long)
        out = evaluate(self.ctx.model, _loader(data, pt, self.ctx.config, shuffle=False), pt,
                       self.ctx.device, ego_ids=self.ctx.ego_ids, threshold=self.stream_threshold)
        return {int(i): float(s) for i, s in zip(out.edge_ids, out.scores)}

    def _to_scored(self, positions: np.ndarray, id2s: dict[int, float]) -> list[ScoredEdge]:
        out: list[ScoredEdge] = []
        for p in positions:
            p = int(p)
            m = self._meta[p]
            sc = id2s.get(p, 0.0)
            fi, fo = self.G.degrees_of(m["from_account_key"])
            ti, to = self.G.degrees_of(m["to_account_key"])
            warm = min(fi + fo, ti + to) >= self.warm_degree
            if not warm:
                self._provisional.add(p)
            else:
                self._provisional.discard(p)
            out.append(ScoredEdge(
                source_id=str(m.get("source_transaction_id") or m["stream_txn_id"]),
                from_account=m["from_account_key"], to_account=m["to_account_key"],
                amount=float(m["amount_paid"]), payment_currency=str(m["payment_currency"]),
                receiving_currency=str(m["receiving_currency"]), payment_format=str(m["payment_format"]),
                occurred_at=str(m["occurred_at"]), is_laundering=int(m["is_laundering"]),
                score=sc, triggered=bool(warm and sc >= self.stream_threshold), warm=warm,
                from_in=fi, from_out=fo, to_in=ti, to_out=to))
        return out

    @torch.no_grad()
    def process_events(self, events: list[dict]) -> list[ScoredEdge]:
        """Nạp lô cạnh mới vào đồ thị in-mem + chấm. Trả ScoredEdge."""
        if not events:
            return []
        rows = _rows_from_events(events, self._next)
        self._next += len(events)
        if len(rows) == 0:
            return []
        positions = self._add(rows)
        return self._to_scored(positions, self._score(positions))

    @torch.no_grad()
    def rescore_warmed(self) -> list[ScoredEdge]:
        """Chấm lại cạnh provisional mà endpoint nay đã warm (đồ thị dày thêm)."""
        cand = np.array([p for p in self._provisional
                         if min(sum(self.G.degrees_of(self._meta[p]["from_account_key"])),
                                sum(self.G.degrees_of(self._meta[p]["to_account_key"]))) >= self.warm_degree],
                        dtype=np.int64)
        if len(cand) == 0:
            return []
        return self._to_scored(cand, self._score(cand))
