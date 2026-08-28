"""Đồ thị có hướng TĂNG DẦN trong bộ nhớ cho chấm streaming (Pha 2, bỏ rebuild).

Vì sao dùng được: mã hoá cạnh CỐ ĐỊNH (SAML-D EdgeEncoder fit-train; IBM z-norm
với thống kê CHỐT một lần) → thêm cạnh KHÔNG đổi điểm cạnh cũ. Mỗi lượt chỉ mã hoá
+ nối các cạnh MỚI (buffer nhân đôi dung lượng → append phân bổ O(1)), rồi chấm
chúng bằng neighbor-loader trên toàn đồ thị đã tích luỹ.

Trước đây `score_pending` đọc LẠI toàn bộ cạnh từ DB + mã hoá LẠI mỗi lượt (O(E)
mỗi lượt). Lớp này giữ đồ thị thường trú, chỉ động tới cạnh mới.
"""
from __future__ import annotations

import numpy as np
import torch
from torch_geometric.data import HeteroData

FORWARD = ("node", "to", "node")
REVERSE = ("node", "rev_to", "node")


class IncrementalGraph:
    def __init__(self, feature_dim: int, capacity: int = 4096):
        self.feature_dim = feature_dim
        self._n = 0  # số cạnh hiện có
        self._cap = capacity
        self._src = np.empty(capacity, dtype=np.int64)
        self._dst = np.empty(capacity, dtype=np.int64)
        self._attr = np.empty((capacity, feature_dim), dtype=np.float32)
        self._y = np.empty(capacity, dtype=np.int64)
        self._ts = np.empty(capacity, dtype=np.float32)
        self._key = np.empty(capacity, dtype=np.int64)  # stream id gốc
        self.node_index: dict[str, int] = {}
        self.deg: dict[int, int] = {}          # bậc (in+out) theo node idx cục bộ
        self.in_deg: dict[int, int] = {}       # bậc VÀO (nhận) — cho typology fan-in
        self.out_deg: dict[int, int] = {}      # bậc RA (gửi) — cho typology fan-out
        self._seen: set[int] = set()           # stream id đã nạp (idempotent)
        self._pos_of_key: dict[int, int] = {}  # stream id -> vị trí cạnh (để chấm lại)

    # ---- dung lượng ----
    def _grow(self, need: int) -> None:
        if self._n + need <= self._cap:
            return
        new_cap = self._cap
        while self._n + need > new_cap:
            new_cap *= 2
        def ext(a):
            b = np.empty((new_cap,) + a.shape[1:], dtype=a.dtype)
            b[: self._n] = a[: self._n]
            return b
        self._src, self._dst = ext(self._src), ext(self._dst)
        self._attr, self._y = ext(self._attr), ext(self._y)
        self._ts, self._key = ext(self._ts), ext(self._key)
        self._cap = new_cap

    def _node(self, key: str) -> int:
        idx = self.node_index.get(key)
        if idx is None:
            idx = len(self.node_index)
            self.node_index[key] = idx
            self.deg[idx] = 0
            self.in_deg[idx] = 0
            self.out_deg[idx] = 0
        return idx

    def degrees_of(self, key: str) -> tuple[int, int]:
        """(bậc vào, bậc ra) của tài khoản — cho typology. 0 nếu chưa thấy."""
        idx = self.node_index.get(key)
        if idx is None:
            return 0, 0
        return self.in_deg.get(idx, 0), self.out_deg.get(idx, 0)

    # ---- nạp cạnh mới ----
    def add(
        self,
        keys: np.ndarray,          # stream id gốc (để idempotent + trả về)
        src_keys: list[str],
        dst_keys: list[str],
        attr: np.ndarray,          # (m, F) đã mã hoá CỐ ĐỊNH
        labels: np.ndarray,
        ts: np.ndarray,
    ) -> np.ndarray:
        """Nối cạnh mới (bỏ trùng theo stream id). Trả VỊ TRÍ (index cạnh) của các
        cạnh vừa thêm trong đồ thị — để chấm đúng chúng."""
        positions = []
        for i in range(len(keys)):
            k = int(keys[i])
            if k in self._seen:
                continue
            self._seen.add(k)
            self._grow(1)
            s = self._node(src_keys[i]); d = self._node(dst_keys[i])
            p = self._n
            self._src[p] = s; self._dst[p] = d
            self._attr[p] = attr[i]
            self._y[p] = int(labels[i]); self._ts[p] = float(ts[i]); self._key[p] = k
            self.deg[s] += 1; self.deg[d] += 1
            self.out_deg[s] += 1; self.in_deg[d] += 1
            self._pos_of_key[k] = p
            self._n += 1
            positions.append(p)
        return np.asarray(positions, dtype=np.int64)

    def positions_of_keys(self, keys) -> np.ndarray:
        """Vị trí cạnh của các stream id đã có (bỏ id không thấy) — để CHẤM LẠI."""
        return np.asarray([self._pos_of_key[int(k)] for k in keys if int(k) in self._pos_of_key], dtype=np.int64)

    @property
    def num_edges(self) -> int:
        return self._n

    @property
    def num_nodes(self) -> int:
        return len(self.node_index)

    def keys_at(self, positions: np.ndarray) -> np.ndarray:
        return self._key[positions]

    def endpoint_min_degree(self, positions: np.ndarray) -> np.ndarray:
        """min(bậc nguồn, bậc đích) cho từng cạnh — tín hiệu NGỮ CẢNH cho warm-up.
        Bậc thấp = đồ thị quanh cạnh còn thưa → điểm model dễ lệch (cold)."""
        src = self._src[positions]; dst = self._dst[positions]
        ds = np.array([self.deg.get(int(s), 0) for s in src])
        dd = np.array([self.deg.get(int(d), 0) for d in dst])
        return np.minimum(ds, dd)

    def hetero(self) -> HeteroData:
        """Bọc phần đã lấp thành HeteroData (view zero-copy; node.x = ones)."""
        n = self._n
        index = torch.from_numpy(np.stack([self._src[:n], self._dst[:n]]))
        attrs = torch.from_numpy(self._attr[:n])
        y = torch.from_numpy(self._y[:n])
        ts = torch.from_numpy(self._ts[:n])
        eid = torch.arange(n, dtype=torch.long)
        data = HeteroData()
        data["node"].x = torch.ones((self.num_nodes, 1), dtype=torch.float32)
        data[FORWARD].edge_index = index
        data[FORWARD].edge_attr = attrs
        data[FORWARD].y = y
        data[FORWARD].edge_id = eid
        data[FORWARD].timestamps = ts
        data[REVERSE].edge_index = index.flip(0)
        data[REVERSE].edge_attr = attrs      # chia sẻ (model chỉ đọc)
        data[REVERSE].edge_id = eid
        data[REVERSE].timestamps = ts
        return data
