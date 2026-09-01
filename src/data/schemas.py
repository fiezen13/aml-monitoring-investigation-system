"""Column contracts and enums for FIN-07 transaction / account tables."""

from __future__ import annotations

from enum import Enum

# IBM LI-Small raw columns (Kaggle ealtman2019)
RAW_COLUMNS = [
    "Timestamp",
    "From Bank",
    "Account",
    "To Bank",
    "Account.1",
    "Amount Received",
    "Receiving Currency",
    "Amount Paid",
    "Payment Currency",
    "Payment Format",
    "Is Laundering",
]

LABEL_PREFIX = "label_"

LABEL_COLUMNS = (
    "label_laundering",
    "label_typology",
    "label_profile_mismatch",
    "label_watchlist_match",
)

TRANSACTION_FEATURE_COLUMNS = (
    "transaction_id",
    "occurred_at",
    "from_bank",
    "from_account_raw",
    "from_account_key",
    "to_bank",
    "to_account_raw",
    "to_account_key",
    "amount_paid_orig",
    "payment_currency",
    "amount_received_orig",
    "receiving_currency",
    "amount",
    "amount_received",
    "currency",
    "channel",
    "split",
)

TRANSACTION_ALL_COLUMNS = TRANSACTION_FEATURE_COLUMNS + ("label_laundering",)

ACCOUNT_COLUMNS = (
    "account_key",
    "bank_id",
    "account_raw",
    "first_seen_at",
    "last_seen_at",
    "tx_count_out",
    "tx_count_in",
)

COMMON_CURRENCY = "USD"

# Canonical counts for the checked-in LI-Small contract. Task 1 deliberately
# removes self-loop transactions before building model inputs, so raw and
# post-filter populations must remain separate in every DQ guard.
LI_SMALL_EXPECTED_RAW_TRANSACTIONS = 6_924_049
LI_SMALL_EXPECTED_ACTIVE_TRANSACTIONS = 6_119_572
LI_SMALL_TRANSACTION_TOLERANCE = 0.01
LI_SMALL_EXPECTED_RAW_ENDPOINT_ACCOUNTS = 705_907
LI_SMALL_EXPECTED_ACTIVE_ACCOUNTS = 576_781
LI_SMALL_ACCOUNT_TOLERANCE = 0.15
LI_SMALL_EXPECTED_LAUNDERING_RATE = 0.0005
LI_SMALL_LAUNDERING_RATE_MIN = 0.0001
LI_SMALL_LAUNDERING_RATE_MAX = 0.002


class PaymentChannel(str, Enum):  # noqa: UP042 — keep str Enum for Python 3.10
    ACH = "ACH"
    WIRE = "WIRE"
    CHEQUE = "CHEQUE"
    CREDIT_CARD = "CREDIT_CARD"
    CASH = "CASH"
    BITCOIN = "BITCOIN"
    REINVESTMENT = "REINVESTMENT"
    OTHER = "OTHER"


_CHANNEL_ALIASES: dict[str, PaymentChannel] = {
    "ACH": PaymentChannel.ACH,
    "WIRE": PaymentChannel.WIRE,
    "CHEQUE": PaymentChannel.CHEQUE,
    "CHECK": PaymentChannel.CHEQUE,
    "CREDIT CARD": PaymentChannel.CREDIT_CARD,
    "CREDIT_CARD": PaymentChannel.CREDIT_CARD,
    "CASH": PaymentChannel.CASH,
    "BITCOIN": PaymentChannel.BITCOIN,
    "REINVESTMENT": PaymentChannel.REINVESTMENT,
}


def normalize_channel(value: object) -> str:
    if value is None:
        return PaymentChannel.OTHER.value
    key = str(value).strip().upper()
    if key in {"", "NAN", "NONE"}:
        return PaymentChannel.OTHER.value
    return _CHANNEL_ALIASES.get(key, PaymentChannel.OTHER).value


def make_account_key(bank: object, account: object) -> str:
    """Build account_key; numeric bank IDs drop leading zeros (match pandas Int bank from Trans CSV)."""
    b = str(bank).strip()
    if b.isdigit():
        b = str(int(b))
    return f"{b}:{account}"


def feature_columns(columns: list[str] | tuple[str, ...]) -> list[str]:
    """Return columns safe for ML (no label_ prefix)."""
    return [c for c in columns if not str(c).startswith(LABEL_PREFIX)]


def assert_no_label_leakage(columns: list[str] | tuple[str, ...]) -> None:
    leaked = [c for c in columns if str(c).startswith(LABEL_PREFIX)]
    if leaked:
        raise AssertionError(f"Label leakage: {leaked}")
