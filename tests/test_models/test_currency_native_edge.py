from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.dummy import DummyClassifier

from src.models.currency_native_edge import (
    ARTIFACT_FORMAT,
    CATEGORICAL_INDICES,
    FEATURE_COLUMNS,
    MODEL_VERSION,
    load_bundle,
    load_split,
    predict_prepared,
    prepare_feature_tables,
    runtime_metadata,
)


def _transactions(*, converted_multiplier: float = 1.0, late_multiplier: float = 1.0) -> pd.DataFrame:
    rows = []
    for index in range(90):
        payment_currency = "US Dollar" if index % 3 else "Bitcoin"
        receiving_currency = (
            payment_currency if index % 5 else ("Bitcoin" if payment_currency == "US Dollar" else "US Dollar")
        )
        amount_paid = float(10 + index) if payment_currency == "US Dollar" else 0.001 * (index + 1)
        if index >= 60:
            amount_paid *= late_multiplier
        if payment_currency == receiving_currency:
            amount_received = amount_paid * 1.01
        elif payment_currency == "US Dollar":
            amount_received = amount_paid * 0.00008
        else:
            amount_received = amount_paid * 12_000.0
        rows.append(
            {
                "transaction_id": f"tx-{index}",
                "occurred_at": datetime(2024, 1, 1, tzinfo=UTC) + timedelta(minutes=10 * index),
                "from_bank": f"bank-{index % 3}",
                "to_bank": f"bank-{(index + 1) % 3}",
                "from_account_key": f"account-{index % 11}",
                "to_account_key": f"account-{(index + 1) % 11}",
                "amount_paid_orig": amount_paid,
                "payment_currency": payment_currency,
                "amount_received_orig": amount_received,
                "receiving_currency": receiving_currency,
                "label_laundering": index % 13 == 0,
                # These legacy static-FX fields are deliberately present.  The
                # currency-native feature builder must never read either one.
                "amount": amount_paid * converted_multiplier,
                "amount_received": amount_received * converted_multiplier,
            }
        )
    return pd.DataFrame(rows)


def _connection(frame: pd.DataFrame) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect()
    connection.register("source_frame", frame)
    connection.execute("CREATE TABLE transaction AS SELECT * FROM source_frame")
    return connection


def _all_matrices(frame: pd.DataFrame) -> tuple[dict, list[np.ndarray]]:
    connection = _connection(frame)
    try:
        preprocessing, _ = prepare_feature_tables(connection)
        matrices = [load_split(connection, split)[0] for split in ("train", "val", "test")]
    finally:
        connection.close()
    return preprocessing, matrices


def _assert_preprocessing_close(reference: dict, changed: dict) -> None:
    assert reference.keys() == changed.keys()
    assert reference["method"] == changed["method"]
    assert reference["currency_vocabulary"] == changed["currency_vocabulary"]
    assert reference["unknown_currency_policy"] == changed["unknown_currency_policy"]
    assert reference["unknown_pair_policy"] == changed["unknown_pair_policy"]
    assert reference["uses_static_fx"] is changed["uses_static_fx"] is False
    for section in ("amount_stats", "global_amount_stats", "currency_pair_log_rate_stats"):
        assert reference[section].keys() == changed[section].keys()
        for key, reference_values in reference[section].items():
            changed_values = changed[section][key]
            if section == "amount_stats":
                assert reference_values.keys() == changed_values.keys()
                for currency, currency_values in reference_values.items():
                    np.testing.assert_allclose(
                        list(currency_values.values()),
                        list(changed_values[currency].values()),
                        rtol=1e-12,
                        atol=1e-12,
                    )
            else:
                np.testing.assert_allclose(
                    list(reference_values.values()),
                    list(changed_values.values()),
                    rtol=1e-12,
                    atol=1e-12,
                )


def test_legacy_static_fx_columns_cannot_change_model_features() -> None:
    reference_preprocessing, reference_matrices = _all_matrices(_transactions(converted_multiplier=1.0))
    changed_preprocessing, changed_matrices = _all_matrices(_transactions(converted_multiplier=1e30))

    _assert_preprocessing_close(reference_preprocessing, changed_preprocessing)
    for reference, changed in zip(reference_matrices, changed_matrices, strict=True):
        np.testing.assert_allclose(reference, changed, rtol=1e-6, atol=1e-6)


def test_validation_and_test_amounts_do_not_change_train_preprocessing() -> None:
    reference, _ = _all_matrices(_transactions(late_multiplier=1.0))
    changed, _ = _all_matrices(_transactions(late_multiplier=1e12))

    _assert_preprocessing_close(reference, changed)
    assert reference["method"] == "train_only_log1p_zscore_per_native_currency"
    assert reference["uses_static_fx"] is False


def test_joblib_bundle_scores_prepared_native_features(tmp_path: Path) -> None:
    connection = _connection(_transactions())
    try:
        preprocessing, _ = prepare_feature_tables(connection)
        x_train, y_train, _ = load_split(connection, "train")
        raw_test = connection.execute("SELECT * FROM raw_features WHERE split = 'test'").fetchdf()
    finally:
        connection.close()

    model = DummyClassifier(strategy="prior").fit(x_train, y_train)
    bundle = {
        "artifact_format": ARTIFACT_FORMAT,
        "model_version": MODEL_VERSION,
        "model": model,
        "threshold": 0.25,
        "feature_columns": list(FEATURE_COLUMNS),
        "categorical_indices": list(CATEGORICAL_INDICES),
        "preprocessing": preprocessing,
        "protocol": {"fx_policy": "no static FX"},
        "runtime": runtime_metadata(),
        "provenance": {"test": True},
    }
    artifact = tmp_path / "model.joblib"
    joblib.dump(bundle, artifact)

    loaded = load_bundle(artifact)
    predictions = predict_prepared(raw_test, loaded)

    assert list(predictions.columns) == ["score", "threshold", "triggered", "model_version"]
    assert len(predictions) == len(raw_test)
    assert predictions["score"].between(0.0, 1.0).all()
    assert predictions["model_version"].eq(MODEL_VERSION).all()

    raw_test.loc[raw_test.index[0], "payment_currency"] = "Unknown Coin"
    with pytest.raises(ValueError, match="retrain before scoring"):
        predict_prepared(raw_test, loaded)
