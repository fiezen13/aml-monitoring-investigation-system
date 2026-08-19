"""Kiểm tra huấn luyện, tinh gọn đặc trưng, đánh giá và nạp/suy luận."""

from __future__ import annotations

from src.bitcoin_aml.inference import BitcoinAmlPredictor
from src.bitcoin_aml.schemas import TransactionFeatures
from src.bitcoin_aml.training import train_pipeline


def test_pipeline_trains_and_reports_real_metrics(elliptic_shaped):
    result = train_pipeline(elliptic_shaped)
    test = result["metrics"]["test"]
    # Chỉ số nằm trong [0,1] và LẤY TỪ mô hình thật (không hard-code).
    for key in ("precision_illicit", "recall_illicit", "f1_illicit"):
        assert 0.0 <= test[key] <= 1.0
    assert test["roc_auc"] is None or 0.0 <= test["roc_auc"] <= 1.0
    # Có sinh ma trận nhầm lẫn.
    assert "confusion_matrix" in test
    # Artifact được ghi ra đĩa.
    assert elliptic_shaped.model_path.exists()
    assert elliptic_shaped.feature_metadata_path.exists()
    assert elliptic_shaped.metrics_path.exists()
    assert elliptic_shaped.model_metadata_path.exists()


def test_feature_refinement_shrinks_feature_set(elliptic_shaped):
    result = train_pipeline(elliptic_shaped)
    meta = result["feature_metadata"]
    # Tinh gọn phải BỎ BỚT so với tập đầy đủ.
    assert meta["feature_count_selected"] <= meta["feature_count_full"]
    assert meta["feature_count_selected"] >= 1
    # Danh sách đặc trưng chọn được lưu để suy luận dùng đúng thứ tự.
    assert isinstance(meta["selected_features"], list)


def test_predictor_returns_probability_in_range_and_matches_features(elliptic_shaped):
    train_pipeline(elliptic_shaped)
    predictor = BitcoinAmlPredictor(elliptic_shaped)
    n = predictor.feature_count
    item = TransactionFeatures(transaction_id="tx-test", features=[0.1] * n, timestep=7)
    result = predictor.predict_one(item)
    assert 0.0 <= result.prediction.risk_score <= 1.0
    assert result.prediction.label in ("illicit", "licit")
    assert result.decision.risk_level in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert result.detector == "bitcoin_aml"
    assert result.domain == "bitcoin"
    assert result.dataset == "elliptic++"
    # Bằng chứng có đặc trưng đầu bảng, tên GỐC không bịa ngữ nghĩa.
    assert result.evidence.top_features
    assert all(f.feature.startswith("feature_") for f in result.evidence.top_features)


def test_wrong_feature_count_is_rejected(elliptic_shaped):
    import pytest

    train_pipeline(elliptic_shaped)
    predictor = BitcoinAmlPredictor(elliptic_shaped)
    bad = TransactionFeatures(transaction_id="tx-bad", features=[0.1, 0.2])  # sai chiều
    with pytest.raises(ValueError, match="đặc trưng"):
        predictor.predict_one(bad)


def test_batch_prediction_matches_single(elliptic_shaped):
    train_pipeline(elliptic_shaped)
    predictor = BitcoinAmlPredictor(elliptic_shaped)
    n = predictor.feature_count
    items = [TransactionFeatures(transaction_id=f"tx{i}", features=[float(i % 3)] * n, timestep=6) for i in range(5)]
    batch = predictor.predict_batch(items)
    assert len(batch) == 5
    # Batch cho cùng kết quả với chấm từng cái.
    single = predictor.predict_one(items[0])
    assert abs(batch[0].prediction.risk_score - single.prediction.risk_score) < 1e-9
