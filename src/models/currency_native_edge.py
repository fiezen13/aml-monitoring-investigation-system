"""Currency-native, strictly-causal transaction scoring for FIN-07.

This module is intentionally independent from ``src.data.currency``.  The
model never converts transaction amounts with the repository's static FX
placeholder table.  Amount-derived features are log transformed and
standardised inside their native currency with statistics fitted on train.
"""

from __future__ import annotations

import hashlib
import math
import platform
import warnings
from pathlib import Path
from typing import Any

import duckdb
import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.exceptions import InconsistentVersionWarning

ARTIFACT_FORMAT = "fin07.currency_native_edge.joblib.v1"
MODEL_VERSION = "fin07_currency_native_policy_edge_v1"

# Each tuple is: output feature, raw feature, currency role.  Rolling amount
# fields are built only from events in the same native currency as the scored
# transaction, so no sum below mixes BTC, USD, EUR, etc.
AMOUNT_FEATURE_SPECS: tuple[tuple[str, str, str], ...] = (
    ("paid_log_z", "amount_paid_orig", "payment"),
    ("received_log_z", "amount_received_orig", "receiving"),
    ("a_out_sum_7d_log_z", "a_out_sum_7d_native", "payment"),
    ("a_out_max_7d_log_z", "a_out_max_7d_native", "payment"),
    ("a_in_sum_7d_log_z", "a_in_sum_7d_native", "payment"),
    ("a_in_max_7d_log_z", "a_in_max_7d_native", "payment"),
    ("a_in_sum_24h_log_z", "a_in_sum_24h_native", "payment"),
    ("a_max_in_24h_log_z", "a_max_in_24h_native", "payment"),
    ("b_in_sum_7d_log_z", "b_in_sum_7d_native", "receiving"),
    ("b_in_max_7d_log_z", "b_in_max_7d_native", "receiving"),
    ("b_out_sum_7d_log_z", "b_out_sum_7d_native", "receiving"),
)

CATEGORICAL_FEATURES = ("payment_currency_code", "receiving_currency_code")

NUMERIC_FEATURES = (
    "cross_bank",
    "cross_currency",
    "day_of_week",
    "currency_pair_log_rate_z",
    "currency_pair_seen_train",
    "a_out_cnt_7d",
    "a_in_cnt_7d",
    "b_in_cnt_7d",
    "b_out_cnt_7d",
    "a_in_cnt_24h",
    "a_mins_since_last_in",
    "b_out_cnt_24h",
    "fan_in_b",
    "fan_out_a",
    "is_new_pair",
    "n_2cycle",
    "n_3cycle",
    "gather_scatter_a",
    "gather_scatter_b",
    "log_passthrough_ratio_24h",
    "log_amount_match_24h",
    "log_balance_ratio_7d",
    "a_no_inflow_24h",
    "a_no_inflow_7d",
)

FEATURE_COLUMNS = tuple(spec[0] for spec in AMOUNT_FEATURE_SPECS) + CATEGORICAL_FEATURES + NUMERIC_FEATURES
CATEGORICAL_INDICES = tuple(FEATURE_COLUMNS.index(name) for name in CATEGORICAL_FEATURES)

AUDIT_COLUMNS = (
    "transaction_id",
    "occurred_at",
    "from_account_key",
    "to_account_key",
    "amount_paid_orig",
    "payment_currency",
    "amount_received_orig",
    "receiving_currency",
)

RAW_REQUIRED_COLUMNS = {
    "payment_currency",
    "receiving_currency",
    *(spec[1] for spec in AMOUNT_FEATURE_SPECS),
    *(name for name in NUMERIC_FEATURES if name not in {"currency_pair_log_rate_z", "currency_pair_seen_train"}),
}


def sha256_file(path: str | Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_std(value: float | None) -> float:
    if value is None or not math.isfinite(float(value)) or float(value) < 1e-12:
        return 1.0
    return float(value)


def _sql_number(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError(f"non-finite SQL literal: {value}")
    return repr(float(value))


def _fit_preprocessing(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    unions = []
    for _output, raw, role in AMOUNT_FEATURE_SPECS:
        currency = "payment_currency" if role == "payment" else "receiving_currency"
        unions.append(
            f"""
            SELECT '{role}' AS role, '{raw}' AS feature, {currency} AS currency,
                   avg(ln(1 + greatest({raw}, 0))) AS mean,
                   stddev_pop(ln(1 + greatest({raw}, 0))) AS std
            FROM raw_features WHERE split = 'train' GROUP BY {currency}
            """
        )
    stats_frame = con.execute(" UNION ALL ".join(unions)).fetchdf()

    global_unions = []
    for _output, raw, role in AMOUNT_FEATURE_SPECS:
        global_unions.append(
            f"""
            SELECT '{role}' AS role, '{raw}' AS feature,
                   avg(ln(1 + greatest({raw}, 0))) AS mean,
                   stddev_pop(ln(1 + greatest({raw}, 0))) AS std
            FROM raw_features WHERE split = 'train'
            """
        )
    global_frame = con.execute(" UNION ALL ".join(global_unions)).fetchdf()

    currency_rows = con.execute(
        """
        SELECT currency, row_number() OVER (ORDER BY currency) - 1 AS code
        FROM (
          SELECT payment_currency AS currency FROM raw_features WHERE split = 'train'
          UNION
          SELECT receiving_currency FROM raw_features WHERE split = 'train'
        ) ORDER BY currency
        """
    ).fetchall()
    pair_frame = con.execute(
        """
        SELECT payment_currency, receiving_currency,
               avg(ln(amount_received_orig) - ln(amount_paid_orig)) AS mean,
               stddev_pop(ln(amount_received_orig) - ln(amount_paid_orig)) AS std,
               count(*) AS rows
        FROM raw_features
        WHERE split = 'train' AND amount_paid_orig > 0 AND amount_received_orig > 0
        GROUP BY 1, 2
        """
    ).fetchdf()

    amount_stats: dict[str, dict[str, dict[str, float]]] = {}
    for row in stats_frame.itertuples(index=False):
        key = f"{row.role}:{row.feature}"
        amount_stats.setdefault(key, {})[str(row.currency)] = {
            "mean": float(row.mean),
            "std": _safe_std(row.std),
        }
    global_stats = {
        f"{row.role}:{row.feature}": {"mean": float(row.mean), "std": _safe_std(row.std)}
        for row in global_frame.itertuples(index=False)
    }
    pair_stats = {
        f"{row.payment_currency}\u0000{row.receiving_currency}": {
            "mean": float(row.mean),
            "std": _safe_std(row.std),
            "rows": int(row.rows),
        }
        for row in pair_frame.itertuples(index=False)
    }
    return {
        "method": "train_only_log1p_zscore_per_native_currency",
        "amount_stats": amount_stats,
        "global_amount_stats": global_stats,
        "currency_vocabulary": {str(currency): int(code) for currency, code in currency_rows},
        "currency_pair_log_rate_stats": pair_stats,
        "unknown_currency_policy": "reject_scoring_until_model_is_retrained",
        "unknown_pair_policy": "pair_log_rate_z=0; pair_seen_train=0",
        "uses_static_fx": False,
    }


def _register_preprocessing(con: duckdb.DuckDBPyConnection, preprocessing: dict[str, Any]) -> None:
    stats_rows = []
    for key, currencies in preprocessing["amount_stats"].items():
        role, feature = key.split(":", 1)
        for currency, values in currencies.items():
            stats_rows.append((role, feature, currency, values["mean"], values["std"]))
    stats = pd.DataFrame(stats_rows, columns=["role", "feature", "currency", "mean", "std"])
    vocab = pd.DataFrame(list(preprocessing["currency_vocabulary"].items()), columns=["currency", "code"])
    pair_rows = []
    for key, values in preprocessing["currency_pair_log_rate_stats"].items():
        payment, receiving = key.split("\u0000", 1)
        pair_rows.append((payment, receiving, values["mean"], values["std"], values["rows"]))
    pairs = pd.DataFrame(
        pair_rows,
        columns=["payment_currency", "receiving_currency", "mean", "std", "rows"],
    )
    con.register("normalization_stats_frame", stats)
    con.register("currency_vocab_frame", vocab)
    con.register("currency_pair_stats_frame", pairs)
    con.execute("CREATE OR REPLACE TEMP TABLE normalization_stats AS SELECT * FROM normalization_stats_frame")
    con.execute("CREATE OR REPLACE TEMP TABLE currency_vocab AS SELECT * FROM currency_vocab_frame")
    con.execute("CREATE OR REPLACE TEMP TABLE currency_pair_stats AS SELECT * FROM currency_pair_stats_frame")


def _create_model_features(
    con: duckdb.DuckDBPyConnection,
    preprocessing: dict[str, Any],
) -> None:
    _register_preprocessing(con, preprocessing)
    z_expressions = []
    joins = []
    for index, (output, raw, role) in enumerate(AMOUNT_FEATURE_SPECS):
        alias = f"ns{index}"
        currency = "r.payment_currency" if role == "payment" else "r.receiving_currency"
        key = f"{role}:{raw}"
        fallback = preprocessing["global_amount_stats"][key]
        joins.append(
            f"LEFT JOIN normalization_stats {alias} ON {alias}.role = '{role}' "
            f"AND {alias}.feature = '{raw}' AND {alias}.currency = {currency}"
        )
        z_expressions.append(
            "(ln(1 + greatest(r.{raw}, 0)) - coalesce({alias}.mean, {mean})) "
            "/ coalesce(nullif({alias}.std, 0), {std}) AS {output}".format(
                raw=raw,
                alias=alias,
                mean=_sql_number(fallback["mean"]),
                std=_sql_number(fallback["std"]),
                output=output,
            )
        )
    select_features = [
        *z_expressions,
        "coalesce(pcv.code, -1)::FLOAT AS payment_currency_code",
        "coalesce(rcv.code, -1)::FLOAT AS receiving_currency_code",
        "r.cross_bank",
        "r.cross_currency",
        "r.day_of_week",
        "CASE WHEN ps.mean IS NULL THEN 0.0 ELSE "
        "(ln(r.amount_received_orig) - ln(r.amount_paid_orig) - ps.mean) "
        "/ coalesce(nullif(ps.std, 0), 1.0) END AS currency_pair_log_rate_z",
        "(ps.mean IS NOT NULL)::TINYINT AS currency_pair_seen_train",
        *(
            f"r.{name}"
            for name in NUMERIC_FEATURES
            if name not in {"currency_pair_log_rate_z", "currency_pair_seen_train"}
        ),
    ]
    sql = f"""
        CREATE OR REPLACE TEMP TABLE model_features AS
        SELECT
            r.transaction_id, r.occurred_at, r.from_account_key, r.to_account_key,
            r.amount_paid_orig, r.payment_currency,
            r.amount_received_orig, r.receiving_currency,
            r.split, r.y,
            {", ".join(select_features)}
        FROM raw_features r
        {" ".join(joins)}
        LEFT JOIN currency_vocab pcv ON pcv.currency = r.payment_currency
        LEFT JOIN currency_vocab rcv ON rcv.currency = r.receiving_currency
        LEFT JOIN currency_pair_stats ps
          ON ps.payment_currency = r.payment_currency
         AND ps.receiving_currency = r.receiving_currency
    """
    con.execute(sql)


def prepare_feature_tables(
    con: duckdb.DuckDBPyConnection,
    *,
    window_days: int = 7,
    degree_cap: int = 200,
    preprocessing: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build causal native-currency features in the connected DuckDB database.

    The source ``transaction`` table must retain the four original IBM amount
    and currency columns.  Converted ``amount`` columns may exist, but are never
    referenced by this function.
    """
    required = {
        "transaction_id",
        "occurred_at",
        "from_bank",
        "to_bank",
        "from_account_key",
        "to_account_key",
        "amount_paid_orig",
        "payment_currency",
        "amount_received_orig",
        "receiving_currency",
        "label_laundering",
    }
    present = {row[0] for row in con.execute("DESCRIBE transaction").fetchall()}
    missing = required - present
    if missing:
        raise ValueError(f"transaction table is missing native columns: {sorted(missing)}")

    cut_60, cut_80 = con.execute(
        "SELECT quantile_disc(occurred_at, 0.6), quantile_disc(occurred_at, 0.8) FROM transaction"
    ).fetchone()
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE degrees AS
        SELECT acct, count(*) AS total FROM (
          SELECT to_account_key AS acct FROM transaction WHERE occurred_at <= $cut60
          UNION ALL
          SELECT from_account_key FROM transaction WHERE occurred_at <= $cut60
        ) GROUP BY 1
        """,
        {"cut60": cut_60},
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE pairs AS
        SELECT from_account_key AS s, to_account_key AS d, min(occurred_at) AS first_ts
        FROM transaction
        WHERE from_account_key IS NOT NULL AND to_account_key IS NOT NULL
        GROUP BY 1, 2
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE triangles AS
        SELECT p2.s AS b, p3.d AS a,
               greatest(p2.first_ts, p3.first_ts) AS ready_ts, count(*) AS n
        FROM pairs p2
        JOIN degrees dc ON dc.acct = p2.d AND dc.total <= {int(degree_cap)}
        JOIN pairs p3 ON p3.s = p2.d
        WHERE p3.d <> p2.s
        GROUP BY 1, 2, 3
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE rolled_counts AS
        WITH events AS (
          SELECT from_account_key AS acct, occurred_at AS ts, 0 AS in_cnt, 1 AS out_cnt
          FROM transaction
          UNION ALL
          SELECT to_account_key, occurred_at, 1, 0 FROM transaction
        ), per_minute AS (
          SELECT acct, ts, sum(in_cnt) AS in_cnt, sum(out_cnt) AS out_cnt
          FROM events GROUP BY 1, 2
        )
        SELECT acct, ts,
          coalesce(sum(in_cnt) OVER w_long, 0) AS in_cnt_7d,
          coalesce(sum(out_cnt) OVER w_long, 0) AS out_cnt_7d,
          coalesce(sum(in_cnt) OVER w_day, 0) AS in_cnt_24h,
          coalesce(sum(out_cnt) OVER w_day, 0) AS out_cnt_24h,
          max(CASE WHEN in_cnt > 0 THEN ts END) OVER w_long AS last_in_ts
        FROM per_minute
        WINDOW
          w_long AS (PARTITION BY acct ORDER BY ts RANGE BETWEEN INTERVAL {int(window_days)} DAY PRECEDING AND INTERVAL 1 MINUTE PRECEDING),
          w_day AS (PARTITION BY acct ORDER BY ts RANGE BETWEEN INTERVAL 24 HOUR PRECEDING AND INTERVAL 1 MINUTE PRECEDING)
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE rolled_amounts AS
        WITH events AS (
          SELECT from_account_key AS acct, occurred_at AS ts,
                 payment_currency AS currency, 0.0 AS in_amt, amount_paid_orig AS out_amt
          FROM transaction
          UNION ALL
          SELECT to_account_key, occurred_at, receiving_currency,
                 amount_received_orig, 0.0
          FROM transaction
        ), per_minute AS (
          SELECT acct, currency, ts,
                 sum(in_amt) AS in_sum, sum(out_amt) AS out_sum,
                 max(in_amt) AS in_max, max(out_amt) AS out_max
          FROM events GROUP BY 1, 2, 3
        )
        SELECT acct, currency, ts,
          coalesce(sum(in_sum) OVER w_long, 0.0) AS in_sum_7d,
          coalesce(max(in_max) OVER w_long, 0.0) AS in_max_7d,
          coalesce(sum(out_sum) OVER w_long, 0.0) AS out_sum_7d,
          coalesce(max(out_max) OVER w_long, 0.0) AS out_max_7d,
          coalesce(sum(in_sum) OVER w_day, 0.0) AS in_sum_24h,
          coalesce(max(in_max) OVER w_day, 0.0) AS in_max_24h
        FROM per_minute
        WINDOW
          w_long AS (PARTITION BY acct, currency ORDER BY ts RANGE BETWEEN INTERVAL {int(window_days)} DAY PRECEDING AND INTERVAL 1 MINUTE PRECEDING),
          w_day AS (PARTITION BY acct, currency ORDER BY ts RANGE BETWEEN INTERVAL 24 HOUR PRECEDING AND INTERVAL 1 MINUTE PRECEDING)
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE edge_base AS
        SELECT transaction_id, occurred_at, from_account_key, to_account_key,
               from_bank, to_bank, amount_paid_orig, payment_currency,
               amount_received_orig, receiving_currency, label_laundering,
               CASE WHEN occurred_at <= $cut60 THEN 'train'
                    WHEN occurred_at <= $cut80 THEN 'val' ELSE 'test' END AS split
        FROM transaction
        """,
        {"cut60": cut_60, "cut80": cut_80},
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE two_cycle AS
        SELECT t1.transaction_id AS tx, count(*) AS n
        FROM transaction t1
        JOIN transaction t2
          ON t2.from_account_key = t1.to_account_key
         AND t2.to_account_key = t1.from_account_key
         AND t2.occurred_at < t1.occurred_at
         AND t2.occurred_at >= t1.occurred_at - INTERVAL {int(window_days)} DAY
        GROUP BY 1
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE three_cycle AS
        SELECT o.transaction_id AS tx, coalesce(sum(tri.n), 0) AS n
        FROM edge_base o
        JOIN triangles tri ON tri.b = o.to_account_key AND tri.a = o.from_account_key
                          AND tri.ready_ts < o.occurred_at
        GROUP BY 1
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE raw_features AS
        SELECT
          o.transaction_id, o.occurred_at, o.from_account_key, o.to_account_key,
          o.split, o.label_laundering::TINYINT AS y,
          o.amount_paid_orig, o.payment_currency,
          o.amount_received_orig, o.receiving_currency,
          coalesce(ap.out_sum_7d, 0.0) AS a_out_sum_7d_native,
          coalesce(ap.out_max_7d, 0.0) AS a_out_max_7d_native,
          coalesce(ap.in_sum_7d, 0.0) AS a_in_sum_7d_native,
          coalesce(ap.in_max_7d, 0.0) AS a_in_max_7d_native,
          coalesce(ap.in_sum_24h, 0.0) AS a_in_sum_24h_native,
          coalesce(ap.in_max_24h, 0.0) AS a_max_in_24h_native,
          coalesce(br.in_sum_7d, 0.0) AS b_in_sum_7d_native,
          coalesce(br.in_max_7d, 0.0) AS b_in_max_7d_native,
          coalesce(br.out_sum_7d, 0.0) AS b_out_sum_7d_native,
          (o.from_bank <> o.to_bank)::TINYINT AS cross_bank,
          (o.payment_currency <> o.receiving_currency)::TINYINT AS cross_currency,
          extract(dow FROM o.occurred_at)::DOUBLE AS day_of_week,
          coalesce(ac.out_cnt_7d, 0)::DOUBLE AS a_out_cnt_7d,
          coalesce(ac.in_cnt_7d, 0)::DOUBLE AS a_in_cnt_7d,
          coalesce(bc.in_cnt_7d, 0)::DOUBLE AS b_in_cnt_7d,
          coalesce(bc.out_cnt_7d, 0)::DOUBLE AS b_out_cnt_7d,
          coalesce(ac.in_cnt_24h, 0)::DOUBLE AS a_in_cnt_24h,
          coalesce(date_diff('minute', ac.last_in_ts, o.occurred_at), 99999)::DOUBLE AS a_mins_since_last_in,
          coalesce(bc.out_cnt_24h, 0)::DOUBLE AS b_out_cnt_24h,
          coalesce(bc.in_cnt_7d, 0)::DOUBLE AS fan_in_b,
          coalesce(ac.out_cnt_7d, 0)::DOUBLE AS fan_out_a,
          (pr.first_ts = o.occurred_at)::TINYINT AS is_new_pair,
          coalesce(c2.n, 0)::DOUBLE AS n_2cycle,
          coalesce(c3.n, 0)::DOUBLE AS n_3cycle,
          coalesce(ac.in_cnt_7d, 0)::DOUBLE * coalesce(ac.out_cnt_7d, 0) AS gather_scatter_a,
          coalesce(bc.in_cnt_7d, 0)::DOUBLE * coalesce(bc.out_cnt_7d, 0) AS gather_scatter_b,
          CASE WHEN coalesce(ap.in_sum_24h, 0.0) > 0
               THEN ln(1 + least(o.amount_paid_orig / ap.in_sum_24h, 1e6)) ELSE 0.0 END AS log_passthrough_ratio_24h,
          CASE WHEN coalesce(ap.in_max_24h, 0.0) > 0
               THEN ln(1 + least(o.amount_paid_orig / ap.in_max_24h, 1e6)) ELSE 0.0 END AS log_amount_match_24h,
          CASE WHEN coalesce(ap.in_sum_7d, 0.0) > 0
               THEN ln(1 + least(ap.out_sum_7d / ap.in_sum_7d, 1e6)) ELSE 0.0 END AS log_balance_ratio_7d,
          (coalesce(ap.in_sum_24h, 0.0) = 0)::TINYINT AS a_no_inflow_24h,
          (coalesce(ap.in_sum_7d, 0.0) = 0)::TINYINT AS a_no_inflow_7d
        FROM edge_base o
        LEFT JOIN rolled_counts ac ON ac.acct = o.from_account_key AND ac.ts = o.occurred_at
        LEFT JOIN rolled_counts bc ON bc.acct = o.to_account_key AND bc.ts = o.occurred_at
        LEFT JOIN rolled_amounts ap ON ap.acct = o.from_account_key
                                   AND ap.currency = o.payment_currency
                                   AND ap.ts = o.occurred_at
        LEFT JOIN rolled_amounts br ON br.acct = o.to_account_key
                                   AND br.currency = o.receiving_currency
                                   AND br.ts = o.occurred_at
        LEFT JOIN two_cycle c2 ON c2.tx = o.transaction_id
        LEFT JOIN three_cycle c3 ON c3.tx = o.transaction_id
        LEFT JOIN pairs pr ON pr.s = o.from_account_key AND pr.d = o.to_account_key
        """
    )

    preprocessing = preprocessing or _fit_preprocessing(con)
    _create_model_features(con, preprocessing)
    rows = con.execute(
        """
        SELECT split, count(*) AS rows, sum(y) AS positives,
               min(occurred_at) AS start, max(occurred_at) AS "end"
        FROM model_features GROUP BY split ORDER BY split
        """
    ).fetchall()
    expected = int(con.execute("SELECT count(*) FROM transaction").fetchone()[0])
    actual = sum(int(row[1]) for row in rows)
    invalid = con.execute(
        """
        SELECT count(*) FILTER (WHERE amount_paid_orig <= 0 OR amount_received_orig <= 0),
               count(*) FILTER (WHERE payment_currency IS NULL OR receiving_currency IS NULL)
        FROM raw_features
        """
    ).fetchone()
    unknown_currencies = int(
        con.execute(
            """
            SELECT count(*)
            FROM raw_features r
            LEFT JOIN currency_vocab pcv ON pcv.currency = r.payment_currency
            LEFT JOIN currency_vocab rcv ON rcv.currency = r.receiving_currency
            WHERE pcv.currency IS NULL OR rcv.currency IS NULL
            """
        ).fetchone()[0]
    )
    non_finite = int(
        con.execute(
            "SELECT count(*) FROM model_features WHERE NOT isfinite(" + ") OR NOT isfinite(".join(FEATURE_COLUMNS) + ")"
        ).fetchone()[0]
    )
    checks = {
        "expected_rows": expected,
        "feature_rows": actual,
        "non_positive_amount_rows": int(invalid[0]),
        "missing_currency_rows": int(invalid[1]),
        "unknown_currency_rows": unknown_currencies,
        "non_finite_feature_rows": non_finite,
        "uses_static_fx": False,
        "degree_cap_fit_scope": "train_only",
    }
    if expected != actual or any((invalid[0], invalid[1], unknown_currencies, non_finite)):
        raise ValueError(f"currency-native data quality gate failed: {checks}")
    split_counts = {
        str(split): {
            "rows": int(n),
            "positives": int(positives),
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
        for split, n, positives, start, end in rows
    }
    return preprocessing, {"checks": checks, "split_counts": split_counts}


def load_split(
    con: duckdb.DuckDBPyConnection,
    split: str,
    *,
    include_metadata: bool = False,
) -> tuple[np.ndarray, np.ndarray, pd.DataFrame | None]:
    if split not in {"train", "val", "test"}:
        raise ValueError(split)
    columns = ", ".join(FEATURE_COLUMNS)
    metadata_columns = ", ".join(AUDIT_COLUMNS)
    frame = con.execute(
        f"""
        SELECT {columns}, y
        {f", {metadata_columns}" if include_metadata else ""}
        FROM model_features WHERE split = ?
        ORDER BY occurred_at, transaction_id
        """,
        [split],
    ).fetchdf()
    x = frame.loc[:, list(FEATURE_COLUMNS)].to_numpy(dtype=np.float32)
    y = frame.pop("y").to_numpy(dtype=np.uint8)
    metadata = None
    if include_metadata:
        metadata = frame.loc[:, list(AUDIT_COLUMNS)].copy()
    return x, y, metadata


def transform_prepared_frame(frame: pd.DataFrame, preprocessing: dict[str, Any]) -> np.ndarray:
    """Transform already-built native raw features using frozen train statistics."""
    missing = RAW_REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"prepared frame missing columns: {sorted(missing)}")
    known_currencies = set(preprocessing["currency_vocabulary"])
    observed_currencies = set(frame["payment_currency"].astype(str)) | set(frame["receiving_currency"].astype(str))
    unknown_currencies = observed_currencies - known_currencies
    if unknown_currencies:
        raise ValueError(
            "model has no train-fitted normalization for currencies: "
            f"{sorted(unknown_currencies)}; retrain before scoring"
        )
    out = pd.DataFrame(index=frame.index)
    for output, raw, role in AMOUNT_FEATURE_SPECS:
        currency_column = "payment_currency" if role == "payment" else "receiving_currency"
        key = f"{role}:{raw}"
        per_currency = preprocessing["amount_stats"][key]
        fallback = preprocessing["global_amount_stats"][key]
        means = frame[currency_column].map({name: values["mean"] for name, values in per_currency.items()})
        stds = frame[currency_column].map({name: values["std"] for name, values in per_currency.items()})
        values = np.log1p(np.maximum(pd.to_numeric(frame[raw]), 0.0))
        out[output] = (values - means.fillna(fallback["mean"])) / stds.fillna(fallback["std"])

    vocab = preprocessing["currency_vocabulary"]
    out["payment_currency_code"] = frame["payment_currency"].map(vocab).fillna(-1)
    out["receiving_currency_code"] = frame["receiving_currency"].map(vocab).fillna(-1)
    pair_stats = preprocessing["currency_pair_log_rate_stats"]
    pair_keys = frame["payment_currency"].astype(str) + "\u0000" + frame["receiving_currency"].astype(str)
    pair_means = pair_keys.map({key: values["mean"] for key, values in pair_stats.items()})
    pair_stds = pair_keys.map({key: values["std"] for key, values in pair_stats.items()})
    raw_rate = np.log(frame["amount_received_orig"].astype(float)) - np.log(frame["amount_paid_orig"].astype(float))
    out["currency_pair_log_rate_z"] = ((raw_rate - pair_means) / pair_stds).fillna(0.0)
    out["currency_pair_seen_train"] = pair_means.notna().astype(np.uint8)
    for name in NUMERIC_FEATURES:
        if name not in {"currency_pair_log_rate_z", "currency_pair_seen_train"}:
            out[name] = pd.to_numeric(frame[name], errors="raise")
    matrix = out.loc[:, list(FEATURE_COLUMNS)].to_numpy(dtype=np.float32)
    if not np.isfinite(matrix).all():
        raise ValueError("prepared feature transformation produced non-finite values")
    return matrix


def validate_bundle(bundle: dict[str, Any]) -> None:
    required = {
        "artifact_format",
        "model_version",
        "model",
        "threshold",
        "feature_columns",
        "categorical_indices",
        "preprocessing",
        "protocol",
        "runtime",
        "provenance",
    }
    missing = required - set(bundle)
    if missing:
        raise ValueError(f"bundle missing keys: {sorted(missing)}")
    if bundle["artifact_format"] != ARTIFACT_FORMAT:
        raise ValueError(f"unsupported artifact_format={bundle['artifact_format']!r}")
    if tuple(bundle["feature_columns"]) != FEATURE_COLUMNS:
        raise ValueError("bundle feature order does not match runtime contract")
    if tuple(bundle["categorical_indices"]) != CATEGORICAL_INDICES:
        raise ValueError("bundle categorical feature indices do not match runtime contract")
    if bundle["preprocessing"].get("uses_static_fx") is not False:
        raise ValueError("currency-native bundle must explicitly disable static FX")


def load_bundle(path: str | Path, *, require_runtime_match: bool = True) -> dict[str, Any]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", InconsistentVersionWarning)
        bundle = joblib.load(path)
    if not isinstance(bundle, dict):
        raise TypeError("currency-native artifact must be a dictionary bundle")
    validate_bundle(bundle)
    expected_sklearn = bundle["runtime"].get("scikit_learn")
    if require_runtime_match and expected_sklearn != sklearn.__version__:
        raise RuntimeError(f"bundle requires scikit-learn {expected_sklearn}; running {sklearn.__version__}")
    return bundle


def predict_prepared(frame: pd.DataFrame, bundle: dict[str, Any]) -> pd.DataFrame:
    validate_bundle(bundle)
    matrix = transform_prepared_frame(frame, bundle["preprocessing"])
    score = bundle["model"].predict_proba(matrix)[:, 1]
    return pd.DataFrame(
        {
            "score": score,
            "threshold": float(bundle["threshold"]),
            "triggered": score >= float(bundle["threshold"]),
            "model_version": bundle["model_version"],
        },
        index=frame.index,
    )


def runtime_metadata() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit_learn": sklearn.__version__,
        "duckdb": duckdb.__version__,
        "joblib": joblib.__version__,
    }
