"""Quy kết đóng góp đặc trưng theo TỪNG giao dịch cho Random Forest.

Vì sao có module này
--------------------
Độ quan trọng đặc trưng của rừng (impurity) là con số TOÀN CỤC — giống nhau cho
mọi giao dịch, nên không trả lời được "vì sao CHÍNH giao dịch này bị chấm nghi
ngờ". Câu hỏi đó cần đóng góp theo từng mẫu.

Phương pháp
-----------
Phân rã Saabas (Saabas 2014, cũng là thứ ``treeinterpreter`` dùng): với mỗi cây,
dự đoán = giá trị tại gốc + tổng "thay đổi xác suất" tại mỗi lần rẽ dọc đường đi
của mẫu. Đóng góp của một đặc trưng = tổng các thay đổi ở những nút rẽ theo đặc
trưng đó. Trung bình trên toàn rừng thì:

    P(illicit) = bias + Σ_f  contribution_f

Đây là phân rã CHÍNH XÁC của ``predict_proba`` (không phải xấp xỉ), và không cần
thư viện ngoài — chỉ đọc cấu trúc cây của scikit-learn.
"""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import RandomForestClassifier


def illicit_contributions(
    model: RandomForestClassifier, x: np.ndarray, illicit_index: int
) -> tuple[np.ndarray, np.ndarray]:
    """Đóng góp của từng đặc trưng vào P(illicit) cho từng hàng của ``x``.

    Trả về ``(contributions, bias)`` với ``contributions`` hình dạng
    ``(n_mẫu, n_đặc_trưng)`` và ``bias`` hình dạng ``(n_mẫu,)``. Bất biến:
    ``contributions.sum(axis=1) + bias`` ≈ ``P(illicit)`` của rừng.
    """
    x = np.asarray(x, dtype=np.float32)
    n_samples, n_features = x.shape
    contributions = np.zeros((n_samples, n_features), dtype=np.float64)
    bias = np.zeros(n_samples, dtype=np.float64)
    n_trees = len(model.estimators_)

    for est in model.estimators_:
        tree = est.tree_
        # Xác suất illicit tại MỖI nút = tỉ lệ lớp illicit trong value của nút.
        # value hình dạng (n_nodes, 1, n_classes); chuẩn hoá theo tổng lớp.
        value = tree.value.reshape(tree.node_count, -1)
        totals = value.sum(axis=1)
        node_p = np.divide(value[:, illicit_index], totals, out=np.zeros(tree.node_count), where=totals > 0)

        left = tree.children_left
        right = tree.children_right
        feature = tree.feature

        # Đường đi của từng mẫu qua cây, dạng dày (n_mẫu, n_nút) để cắt cột nhanh
        # bằng numpy — nhanh hơn nhiều so với nhân thưa từng nút. Giải phóng sau
        # mỗi cây nên bộ nhớ chỉ giữ một cây tại một thời điểm.
        path = est.decision_path(x).toarray().astype(bool)

        bias += node_p[0] / n_trees  # gốc là như nhau cho mọi mẫu

        for node in range(tree.node_count):
            f = feature[node]
            if f < 0:
                continue  # nút lá, không rẽ
            in_node = path[:, node]
            lft, rgt = left[node], right[node]
            # Mẫu đi qua node RỒI qua con trái = đã rẽ trái tại node.
            went_left = in_node & path[:, lft]
            went_right = in_node & path[:, rgt]
            contributions[went_left, f] += (node_p[lft] - node_p[node]) / n_trees
            contributions[went_right, f] += (node_p[rgt] - node_p[node]) / n_trees

    return contributions, bias
