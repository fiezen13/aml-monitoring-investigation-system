"""Dựng đồ thị SAML-D cho MEGA-PNA (Multi-PNA+EU).

Node = TÀI KHOẢN, cạnh = giao dịch (có hướng người gửi → người nhận). Country là
thuộc tính ngữ cảnh của cạnh, KHÔNG phải node — đúng §7.

HeteroData khớp hợp đồng của ``src.mega_pna.model.MegaPna``:
  * ``data["node"].x`` = ones (đặc trưng cấu trúc; ego-id thêm ở tầng training)
  * quan hệ xuôi ``("node","to","node")`` và ngược ``("node","rev_to","node")``
  * mỗi cạnh mang ``edge_attr`` (đã mã hoá + chuẩn hoá bằng thống kê TRAIN), ``y``,
    ``edge_id``, ``timestamps``.

Lát cắt tích luỹ theo thời gian: đồ thị val gồm cạnh train làm ngữ cảnh truyền
tin, giám sát trên phần val; tương tự test. Không rò rỉ tương lai vì thứ tự cạnh
đã sắp theo thời gian và ngưỡng cắt là ranh giới thời gian.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
import torch
from torch_geometric.data import HeteroData

from src.mega_pna.data import MegaPnaDataBundle
from src.mega_pna.data import TemporalSplit as MegaTemporalSplit
from src.samld.encoders import EdgeEncoder, fit_edge_encoder
from src.samld.schema import COLS
from src.samld.split import TemporalSplit

logger = logging.getLogger("fin07.samld.graph")

FORWARD = ("node", "to", "node")
REVERSE = ("node", "rev_to", "node")


@dataclass
class SamldGraphBundle:
    train: HeteroData
    validation: HeteroData
    test: HeteroData
    num_nodes: int
    edge_features: int
    feature_names: list[str]
    encoder: EdgeEncoder
    #: mã giao dịch gốc theo thứ tự cạnh (để đối chiếu evidence sau này).
    source_ids: np.ndarray
    train_end: int
    val_end: int
    #: Bundle đúng hợp đồng của ``src.mega_pna.training.train_one_seed`` — cho phép
    #: tái dùng NGUYÊN VẸN vòng huấn luyện MEGA-PNA (Multi-PNA+EU) cho SAML-D.
    mega_bundle: MegaPnaDataBundle


def _slice_graph(
    edge_index: torch.Tensor,
    edge_attr: torch.Tensor,
    labels: torch.Tensor,
    timestamps: torch.Tensor,
    *,
    end: int,
    num_nodes: int,
) -> HeteroData:
    data = HeteroData()
    data["node"].x = torch.ones((num_nodes, 1), dtype=torch.float32)
    index = edge_index[:, :end]
    attrs = edge_attr[:end]
    edge_ids = torch.arange(end, dtype=torch.long)
    data[FORWARD].edge_index = index
    data[FORWARD].edge_attr = attrs
    data[FORWARD].y = labels[:end]
    data[FORWARD].edge_id = edge_ids
    data[FORWARD].timestamps = timestamps[:end]
    data[REVERSE].edge_index = index.flip(0)
    # CHIA SẺ tensor đặc trưng/thời gian với chiều xuôi thay vì clone: model chỉ
    # ĐỌC chúng (embedding tạo tensor mới), nên không cần bản sao. Trên đồ thị
    # 9,5 triệu cạnh, clone làm tốn thêm ~7GB RAM và gây OOM khi có worker fork.
    data[REVERSE].edge_attr = attrs
    data[REVERSE].edge_id = edge_ids
    data[REVERSE].timestamps = timestamps[:end]
    return data


def build_inference_graph(df: pd.DataFrame, encoder: EdgeEncoder) -> tuple[HeteroData, np.ndarray]:
    """Dựng MỘT đồ thị để chấm (không chia) từ một lô giao dịch + encoder đã fit.

    Trả về (HeteroData xuôi+ngược, mã giao dịch theo thứ tự cạnh). Ngữ cảnh đồ thị
    là chính lô giao dịch này — production đầy đủ nên nạp thêm đồ thị tham chiếu,
    nhưng lô-đồ-thị đã cho model chạy đúng hợp đồng.
    """
    accounts = pd.concat([df[COLS.sender_account], df[COLS.receiver_account]]).astype(str)
    codes, _ = pd.factorize(accounts, sort=False)
    num_nodes = int(codes.max()) + 1
    n = len(df)
    edge_index = torch.from_numpy(np.stack([codes[:n], codes[n:]]).astype(np.int64))
    edge_attr = torch.from_numpy(encoder.transform(df))
    labels = torch.zeros(n, dtype=torch.int64)  # inference: nhãn giả, không dùng
    timestamps = (
        torch.from_numpy(df["elapsed_days"].to_numpy(dtype=np.float32)) if "elapsed_days" in df else torch.zeros(n)
    )
    graph = _slice_graph(edge_index, edge_attr, labels, timestamps, end=n, num_nodes=num_nodes)
    return graph, df["transaction_id"].to_numpy() if "transaction_id" in df else np.arange(n)


def build_graph(split: TemporalSplit, encoder: EdgeEncoder | None = None) -> SamldGraphBundle:
    """Từ split thời gian → bundle đồ thị. Encoder fit trên TRAIN nếu chưa có."""
    encoder = encoder or fit_edge_encoder(split.train)

    # Thứ tự thời gian: train ++ val ++ test (mỗi phần đã sắp theo thời gian).
    ordered = pd.concat([split.train, split.val, split.test], ignore_index=True)
    train_end = len(split.train)
    val_end = len(split.train) + len(split.val)

    # Ánh xạ tài khoản (chuỗi) → id node liên tục, trên TOÀN BỘ tài khoản.
    accounts = pd.concat([ordered[COLS.sender_account], ordered[COLS.receiver_account]]).astype(str)
    codes, _ = pd.factorize(accounts, sort=False)
    num_nodes = int(codes.max()) + 1
    n_edges = len(ordered)
    from_id = codes[:n_edges]
    to_id = codes[n_edges:]

    edge_index = torch.from_numpy(np.stack([from_id, to_id]).astype(np.int64))
    edge_attr = torch.from_numpy(encoder.transform(ordered))
    labels = torch.from_numpy(ordered[COLS.label].to_numpy(dtype=np.int64).copy())
    # Mốc thời gian dạng số (ngày trôi) cho neighbour-loader/tham chiếu.
    timestamps = torch.from_numpy(ordered["elapsed_days"].to_numpy(dtype=np.float32))
    source_ids = ordered["transaction_id"].to_numpy()
    source_edge_ids = torch.from_numpy(ordered["transaction_id"].to_numpy(dtype=np.int64))

    train_g = _slice_graph(edge_index, edge_attr, labels, timestamps, end=train_end, num_nodes=num_nodes)
    val_g = _slice_graph(edge_index, edge_attr, labels, timestamps, end=val_end, num_nodes=num_nodes)
    test_g = _slice_graph(edge_index, edge_attr, labels, timestamps, end=n_edges, num_nodes=num_nodes)

    # Split theo hợp đồng mega_pna: positions("validation") = dải cạnh val trong
    # đồ thị tích luỹ; *_days chỉ là metadata nên để rỗng.
    mega_split = MegaTemporalSplit(
        train_end=train_end,
        validation_end=val_end,
        total=n_edges,
        train_days=(),
        validation_days=(),
        test_days=(),
    )
    mega_bundle = MegaPnaDataBundle(
        train=train_g,
        validation=val_g,
        test=test_g,
        split=mega_split,
        feature_names=tuple(encoder.feature_names),
        labels=labels,
        source_edge_ids=source_edge_ids,
    )

    bundle = SamldGraphBundle(
        train=train_g,
        validation=val_g,
        test=test_g,
        num_nodes=num_nodes,
        edge_features=encoder.num_features,
        feature_names=encoder.feature_names,
        encoder=encoder,
        source_ids=source_ids,
        train_end=train_end,
        val_end=val_end,
        mega_bundle=mega_bundle,
    )
    logger.info(
        "Đồ thị SAML-D: %d node, %d cạnh (train %d / val %d / test %d), %d đặc trưng cạnh.",
        num_nodes,
        n_edges,
        train_end,
        val_end - train_end,
        n_edges - val_end,
        encoder.num_features,
    )
    return bundle
