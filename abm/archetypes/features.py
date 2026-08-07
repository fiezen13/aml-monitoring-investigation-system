"""Scale-free behavioral features for archetype derivation.

Every feature here answers a question about *shape*, never about size in
currency units. That is deliberate and it is the whole design constraint:

- IBM mixes fifteen currencies across eighteen orders of magnitude, so an
  absolute amount carries no comparable meaning between two accounts.
- Phase 8 rescales money onto Vietnamese income and revenue anyway, so any
  absolute level learned here would be discarded.
- An archetype is meant to say "this account behaves like a collection hub"
  and have that stay true whether the hub moves thousands or billions.

Two feature families are excluded on evidence rather than taste:

- **Time of day and weekday.** IBM assigns times uniformly at random; every hour
  from 01:00 to 23:00 holds 3.88-3.90 percent of transactions (Finding B2).
  Clustering on noise manufactures clusters.
- **Absolute amounts.** See above.

Ratios are written as bounded symmetric contrasts, `(a - b) / (a + b)`, instead
of the quotient `a / b`. The quotient is undefined when an account only ever
receives, explodes when it almost only receives, and gives a heavy tail that
dominates any distance metric. The contrast is defined everywhere on [-1, 1]
and treats "only in" and "only out" as equally far from balanced.
"""

from __future__ import annotations

import numpy as np
import pyarrow as pa

# The columns read from the behavior profile CSV.
SOURCE_COLUMNS = (
    "account_key",
    "entity_kind",
    "transaction_count",
    "incoming_transaction_count",
    "outgoing_transaction_count",
    "total_incoming_amount",
    "total_outgoing_amount",
    "median_incoming_amount",
    "median_outgoing_amount",
    "mean_incoming_amount",
    "mean_outgoing_amount",
    "unique_inbound_counterparties",
    "unique_outbound_counterparties",
    "self_transfer_count",
    "active_days",
    "observed_span_days",
    "activity_density",
    "transactions_per_active_day",
    "turnover_amount",
    "fan_in_ratio",
    "fan_out_ratio",
    "counterparty_diversity",
    "distinct_currencies",
    "dominant_payment_format_share",
)

FEATURE_NAMES = (
    "log_transactions_per_active_day",
    "activity_density",
    "fan_in_ratio",
    "fan_out_ratio",
    "flow_direction_balance",
    "value_direction_balance",
    "log_turnover_multiple",
    "self_transfer_share",
    "dominant_format_share",
    "log_distinct_currencies",
)

FEATURE_DESCRIPTIONS = {
    "log_transactions_per_active_day": "Burstiness: how many events on a day the account is active at all.",
    "activity_density": "Fraction of the account's own lifespan on which it did anything.",
    "fan_in_ratio": "Distinct senders per inbound transaction. 1.0 = every receipt from a new party.",
    "fan_out_ratio": "Distinct recipients per outbound transaction.",
    "flow_direction_balance": "(in - out) / (in + out) by count. +1 = only receives, -1 = only pays.",
    "value_direction_balance": "(in - out) / (in + out) by amount. Detects pass-through when near 0.",
    "log_turnover_multiple": "Turnover divided by a typical single transaction. High = conduit.",
    "self_transfer_share": "Share of activity the account sends to itself.",
    "dominant_format_share": "Concentration on one payment instrument. Not which instrument.",
    "log_distinct_currencies": "Currency spread; the international-activity signal.",
}


def _balance(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    """Bounded symmetric contrast on [-1, 1], zero when both sides are zero."""
    total = first + second
    return np.divide(first - second, total, out=np.zeros_like(total, dtype=float), where=total > 0)


def _typical_transaction(table: pa.Table) -> np.ndarray:
    """A representative single-transaction size for the account.

    Prefers the median of whichever direction the account actually uses, and
    falls back to the mean when a median is missing or zero. Accounts for which
    no positive value can be found are handled by the caller; silently treating
    them as 1.0 would put them at whatever turnover multiple their turnover
    happens to equal, which is meaningless.
    """
    candidates = np.vstack(
        [
            _column(table, "median_incoming_amount"),
            _column(table, "median_outgoing_amount"),
            _column(table, "mean_incoming_amount"),
            _column(table, "mean_outgoing_amount"),
        ]
    )
    candidates = np.where(candidates > 0, candidates, np.nan)
    # An all-NaN column is an account with no positive amount anywhere. That is a
    # real state, not an error, and the caller excludes those rows — so the
    # warning numpy would raise here is noise about an outcome we handle.
    all_nan = np.isnan(candidates).all(axis=0)
    result = np.full(candidates.shape[1], np.nan)
    if (~all_nan).any():
        result[~all_nan] = np.nanmedian(candidates[:, ~all_nan], axis=0)
    return result


def _column(table: pa.Table, name: str) -> np.ndarray:
    return table.column(name).to_numpy(zero_copy_only=False).astype(float)


def build_feature_matrix(table: pa.Table) -> tuple[np.ndarray, np.ndarray]:
    """Return the feature matrix and a boolean mask of usable rows.

    The mask excludes accounts whose typical transaction size cannot be
    determined. Those rows are reported rather than imputed.
    """
    in_count = _column(table, "incoming_transaction_count")
    out_count = _column(table, "outgoing_transaction_count")
    in_value = _column(table, "total_incoming_amount")
    out_value = _column(table, "total_outgoing_amount")
    total_count = _column(table, "transaction_count")
    turnover = _column(table, "turnover_amount")

    typical = _typical_transaction(table)
    usable = np.isfinite(typical) & (typical > 0) & (total_count > 0)

    turnover_multiple = np.divide(turnover, typical, out=np.zeros_like(turnover), where=usable & (typical > 0))

    features = np.column_stack(
        [
            np.log1p(_column(table, "transactions_per_active_day")),
            _column(table, "activity_density"),
            np.nan_to_num(_column(table, "fan_in_ratio")),
            np.nan_to_num(_column(table, "fan_out_ratio")),
            _balance(in_count, out_count),
            _balance(in_value, out_value),
            np.log1p(np.clip(turnover_multiple, 0, None)),
            np.divide(
                _column(table, "self_transfer_count"),
                total_count,
                out=np.zeros_like(total_count),
                where=total_count > 0,
            ),
            np.nan_to_num(_column(table, "dominant_payment_format_share")),
            np.log1p(np.nan_to_num(_column(table, "distinct_currencies"))),
        ]
    )
    return features, usable
