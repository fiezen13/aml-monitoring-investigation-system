"""Ngữ cảnh đồ thị giao dịch Elliptic++ (P2, mức MVP).

Chỉ đọc danh sách cạnh giao dịch→giao dịch để trả về láng giềng 1 chặng, bậc
vào/ra. KHÔNG dựng cả một hệ thống graph analytics — đủ để tác tử/giao diện sau
này lần theo quan hệ, không hơn.

Đây là tiện ích ngoại tuyến: nạp danh sách cạnh một lần, tra cứu nhiều lần.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

import pandas as pd

from src.bitcoin_aml.config import BitcoinAmlConfig

logger = logging.getLogger("fin07.bitcoin_aml.graph")


@dataclass(frozen=True)
class NeighbourContext:
    transaction_id: str
    in_degree: int
    out_degree: int
    predecessors: list[str]
    successors: list[str]


class TransactionGraph:
    """Đồ thị giao dịch→giao dịch, tra láng giềng 1 chặng.

    Xây từ ``txs_edgelist.csv``. Giữ hai chỉ mục kề (xuôi và ngược) để trả cả
    bên nhận lẫn bên gửi mà không quét lại danh sách cạnh.
    """

    def __init__(self, successors: dict[str, list[str]], predecessors: dict[str, list[str]]) -> None:
        self._succ = successors
        self._pred = predecessors

    @classmethod
    def from_config(cls, config: BitcoinAmlConfig) -> TransactionGraph:
        path = config.edgelist_path
        if not path.exists():
            raise FileNotFoundError(f"Không thấy danh sách cạnh {path}")
        edges = pd.read_csv(path)
        cols = list(edges.columns)
        if len(cols) < 2:
            raise ValueError("txs_edgelist.csv cần ít nhất hai cột (nguồn, đích).")
        src_col, dst_col = cols[0], cols[1]
        succ: dict[str, list[str]] = defaultdict(list)
        pred: dict[str, list[str]] = defaultdict(list)
        for source, target in zip(edges[src_col].astype(str), edges[dst_col].astype(str), strict=True):
            succ[source].append(target)
            pred[target].append(source)
        logger.info("Đồ thị giao dịch: %d cạnh", len(edges))
        return cls(dict(succ), dict(pred))

    def neighbours(self, transaction_id: str, *, limit: int = 25) -> NeighbourContext:
        """Láng giềng 1 chặng của một giao dịch, cắt bớt để không trả về quá dài."""
        succ = self._succ.get(transaction_id, [])
        pred = self._pred.get(transaction_id, [])
        return NeighbourContext(
            transaction_id=transaction_id,
            in_degree=len(pred),
            out_degree=len(succ),
            predecessors=pred[:limit],
            successors=succ[:limit],
        )
