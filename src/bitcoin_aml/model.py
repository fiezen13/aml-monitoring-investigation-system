"""Xây, huấn luyện và tuần tự hoá Random Forest cho nhánh Bitcoin AML.

Mô hình cố định là ``RandomForestClassifier`` — đây là task TÁI LẬP một phương
pháp đã công bố, không phải đi dò SOTA. Không thử GCN/GAT/PNA ở đây.
"""

from __future__ import annotations

import logging

from sklearn.ensemble import RandomForestClassifier

from src.bitcoin_aml.config import BitcoinAmlConfig

logger = logging.getLogger("fin07.bitcoin_aml.model")

#: Cột xác suất illicit trong ``predict_proba``. classes_ được sắp [0, 1] = [licit,
#: illicit] vì nhãn nội bộ LICIT=0, ILLICIT=1; ta vẫn tra động qua ``classes_``
#: để không phụ thuộc thứ tự.
ILLICIT_LABEL = 1


def build_model(config: BitcoinAmlConfig) -> RandomForestClassifier:
    """Dựng Random Forest theo siêu tham số trong config (bám Weber et al./Elliptic++)."""
    return RandomForestClassifier(
        n_estimators=config.n_estimators,
        max_depth=config.max_depth,
        max_features=config.max_features,
        min_samples_leaf=config.min_samples_leaf,
        class_weight=config.class_weight,
        random_state=config.random_seed,
        n_jobs=config.n_jobs,
    )


def train_model(model: RandomForestClassifier, x_train, y_train) -> RandomForestClassifier:  # noqa: ANN001
    """Huấn luyện tại chỗ; xác định nhờ ``random_state`` đã đặt."""
    logger.info("Huấn luyện Random Forest trên %d mẫu, %d đặc trưng", len(x_train), x_train.shape[1])
    model.fit(x_train, y_train)
    return model


def illicit_probability(model: RandomForestClassifier, x) -> list[float]:  # noqa: ANN001
    """Trả P(illicit) cho từng hàng — tra qua ``classes_``, không giả định thứ tự."""
    classes = list(model.classes_)
    if ILLICIT_LABEL not in classes:
        raise ValueError(f"Mô hình không có lớp illicit ({ILLICIT_LABEL}) trong classes_={classes}")
    index = classes.index(ILLICIT_LABEL)
    proba = model.predict_proba(x)
    return [float(row[index]) for row in proba]
