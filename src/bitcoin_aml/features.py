"""Tinh gọn đặc trưng (feature refinement) cho nhánh Bitcoin AML.

Paper Elliptic++ phân tích độ quan trọng đặc trưng rồi tinh gọn tập đặc trưng.
Ở đây tái lập bằng cách xếp hạng theo độ quan trọng (impurity) của một rừng
huấn luyện trên TẬP TRAIN, rồi giữ lại số đặc trưng đủ phủ ``coverage`` tổng độ
quan trọng (có trần cứng ``max_features``). Đây là bản tái lập trung thực: không
bịa ngữ nghĩa cho đặc trưng ẩn danh, không dùng test để chọn đặc trưng.

Vì sao tính trên train, không trên toàn bộ
------------------------------------------
Chọn đặc trưng bằng dữ liệu test là rò rỉ — mô hình "biết trước" test qua khâu
chọn đặc trưng. Rừng dùng để xếp hạng chỉ nhìn train.
"""

from __future__ import annotations

import logging

from sklearn.ensemble import RandomForestClassifier

from src.bitcoin_aml.config import BitcoinAmlConfig
from src.bitcoin_aml.data import SplitData

logger = logging.getLogger("fin07.bitcoin_aml.features")


def _ranking_forest(config: BitcoinAmlConfig) -> RandomForestClassifier:
    """Rừng nhỏ để XẾP HẠNG đặc trưng — không phải mô hình cuối.

    Cùng siêu tham số với mô hình cuối để độ quan trọng phản ánh đúng thứ mô
    hình cuối sẽ dùng.
    """
    return RandomForestClassifier(
        n_estimators=config.n_estimators,
        max_depth=config.max_depth,
        max_features=config.max_features,
        min_samples_leaf=config.min_samples_leaf,
        class_weight=config.class_weight,
        random_state=config.random_seed,
        n_jobs=config.n_jobs,
    )


def refine_features(split: SplitData, config: BitcoinAmlConfig) -> tuple[list[str], list[dict[str, float]]]:
    """Chọn tập đặc trưng tinh gọn TỪ TẬP TRAIN.

    Trả về (danh sách đặc trưng đã chọn theo đúng thứ tự dùng khi suy luận, bảng
    xếp hạng độ quan trọng đầy đủ). Thứ tự đặc trưng chọn ra bám theo thứ tự cột
    gốc, không theo thứ hạng — để vector suy luận khớp cột một cách xác định.
    """
    forest = _ranking_forest(config)
    forest.fit(split.x_train, split.y_train)
    importances = forest.feature_importances_

    ranking = sorted(
        (
            {"feature": name, "importance": float(imp)}
            for name, imp in zip(split.feature_names, importances, strict=True)
        ),
        key=lambda row: row["importance"],
        reverse=True,
    )

    # Giữ đủ đặc trưng để phủ `coverage` tổng độ quan trọng, chặn trên bằng
    # `max_features`. Luôn giữ ít nhất một đặc trưng.
    total = float(importances.sum()) or 1.0
    cumulative = 0.0
    selected_set: set[str] = set()
    for row in ranking:
        selected_set.add(row["feature"])
        cumulative += row["importance"] / total
        if cumulative >= config.refinement_importance_coverage:
            break
        if len(selected_set) >= config.refinement_max_features:
            break

    # Thứ tự cuối = thứ tự cột gốc, lọc theo tập đã chọn. Xác định và ổn định.
    selected = [name for name in split.feature_names if name in selected_set]
    logger.info(
        "Tinh gọn đặc trưng: giữ %d / %d (phủ %.1f%% độ quan trọng)",
        len(selected),
        len(split.feature_names),
        min(cumulative, 1.0) * 100,
    )
    return selected, ranking


def apply_selection(split: SplitData, selected: list[str]) -> SplitData:
    """Thu hẹp cả ba tập về đúng các đặc trưng đã chọn, giữ nguyên thứ tự."""
    missing = [name for name in selected if name not in split.feature_names]
    if missing:
        raise ValueError(f"Đặc trưng đã chọn không có trong dữ liệu: {missing[:5]}")
    return SplitData(
        x_train=split.x_train[selected],
        y_train=split.y_train,
        x_val=split.x_val[selected],
        y_val=split.y_val,
        x_test=split.x_test[selected],
        y_test=split.y_test,
        feature_names=selected,
        time_column=split.time_column,
        train_timesteps=split.train_timesteps,
        test_timesteps=split.test_timesteps,
    )


def importance_lookup(ranking: list[dict[str, float]]) -> dict[str, float]:
    """Bảng tra {tên đặc trưng → độ quan trọng} để đính vào bằng chứng suy luận."""
    return {row["feature"]: float(row["importance"]) for row in ranking}


def top_importance(ranking: list[dict[str, float]], selected: set[str], k: int) -> list[str]:
    """k đặc trưng quan trọng nhất TRONG tập đã chọn — dùng cho phần bằng chứng."""
    return [row["feature"] for row in ranking if row["feature"] in selected][:k]
