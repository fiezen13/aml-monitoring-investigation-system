"""Phase 11 — rebuild transactions on the IBM backbone.

Four things change; everything else is preserved exactly.

| Changed | Preserved |
|---|---|
| Amount → VND, per-account scale | Which account paid which, and in what order |
| Payment format → Vietnamese taxonomy | Date of every transaction |
| Time of day → Vietnamese diurnal curve | Relative size of payments within an account |
| Identifiers → `ACC-*`, `CPY-*`, `TXN-*` | Fan-in / fan-out structure and cycles |

## Payment format, and why it is redrawn

IBM's format predicts its own laundering label at 7.2x lift, and two of its
values — Wire and Reinvestment — never co-occur with a positive across 3.07
million transactions. Carrying the column across would hand any model a feature
that does most of the work, and Phase 14 would fail on arrival.

Its distribution is also not Vietnamese: 38.5% Cheque and 27.5% Credit Card
describe no retail bank in Viet Nam.

So format is redrawn from a Vietnamese taxonomy, conditioned on the *customer's*
digital-usage segment (which is Findex-derived), the transaction's direction, and
its size. **The label is not an input.** The redraw both removes the leak and
fixes the realism problem, which is why it was preferred to dropping the column.

## Time of day, and why ordering survives

IBM assigns times uniformly at random — every hour from 01:00 to 23:00 holds
3.88-3.90% of transactions. Night-activity features computed on that are noise.

The redraw keeps each transaction's **date** and its **position in the global
ordering**. New times are drawn from a diurnal curve, sorted within each day, and
assigned to that day's transactions in their original order. A chain of hops that
ran A→B→C on the same day still runs A→B→C afterwards, so cycles, stacks, and
every temporal AML structure survive intact.

## Amounts on internal edges

Each account has its own scale factor from Phase 8. A transaction between two
internal accounts has two, and they disagree. The geometric mean is used: it is
symmetric, so neither side is privileged, and it keeps both accounts near their
target inflow instead of putting one exactly on target and the other far off. The
residual deviation is measured in validation rather than asserted away.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np

TRANSACTION_ID_FORMAT = "TXN-{:012d}"
COUNTERPARTY_ID_FORMAT = "CPY-{:08d}"

SCHEMA_VERSION = "1.0"

# Bank View timestamps are Indochina Time. IBM declares no timezone; adopting one
# explicitly is better than leaving every consumer to guess.
TIMEZONE_OFFSET = timedelta(hours=7)
TIMEZONE_LABEL = "+07:00"

# Vietnamese payment taxonomy. NAPAS is the domestic interbank switch.
PAYMENT_FORMATS = (
    "INTRABANK_TRANSFER",
    "INTERBANK_TRANSFER",
    "QR_PAYMENT",
    "CARD_PAYMENT",
    "CASH_DEPOSIT",
    "CASH_WITHDRAWAL",
    "DIRECT_DEBIT",
    "INTERNATIONAL_WIRE",
)

CHANNELS = ("MOBILE", "INTERNET", "ATM", "BRANCH", "POS", "QR")

TRANSACTION_TYPES = ("TRANSFER", "DEPOSIT", "WITHDRAWAL", "PURCHASE", "SALARY", "FEE")

# Share of each payment format by the customer's digital-usage segment. Not
# sourced: SBV publishes system-wide payment aggregates, not a per-customer mix.
# Registered as ASSUME_CHANNEL_MIX. The gradient — digital customers transfer
# electronically, non-digital customers use cash and branches — is the part worth
# defending; the exact numbers are not.
ASSUME_CHANNEL_MIX: dict[str, dict[str, float]] = {
    "HIGH": {
        "INTRABANK_TRANSFER": 0.26,
        "INTERBANK_TRANSFER": 0.34,
        "QR_PAYMENT": 0.18,
        "CARD_PAYMENT": 0.13,
        "CASH_DEPOSIT": 0.03,
        "CASH_WITHDRAWAL": 0.04,
        "DIRECT_DEBIT": 0.02,
    },
    "MEDIUM": {
        "INTRABANK_TRANSFER": 0.24,
        "INTERBANK_TRANSFER": 0.27,
        "QR_PAYMENT": 0.10,
        "CARD_PAYMENT": 0.13,
        "CASH_DEPOSIT": 0.10,
        "CASH_WITHDRAWAL": 0.13,
        "DIRECT_DEBIT": 0.03,
    },
    "LOW": {
        "INTRABANK_TRANSFER": 0.16,
        "INTERBANK_TRANSFER": 0.16,
        "QR_PAYMENT": 0.03,
        "CARD_PAYMENT": 0.06,
        "CASH_DEPOSIT": 0.28,
        "CASH_WITHDRAWAL": 0.29,
        "DIRECT_DEBIT": 0.02,
    },
    "NONE": {
        "INTRABANK_TRANSFER": 0.09,
        "INTERBANK_TRANSFER": 0.08,
        "QR_PAYMENT": 0.01,
        "CARD_PAYMENT": 0.02,
        "CASH_DEPOSIT": 0.39,
        "CASH_WITHDRAWAL": 0.40,
        "DIRECT_DEBIT": 0.01,
    },
}

# Channel follows from the instrument, not independently of it: a QR payment
# happens on a phone, a cash withdrawal at an ATM or a counter.
ASSUME_CHANNEL_BY_FORMAT: dict[str, dict[str, float]] = {
    "INTRABANK_TRANSFER": {"MOBILE": 0.62, "INTERNET": 0.26, "BRANCH": 0.09, "ATM": 0.03},
    "INTERBANK_TRANSFER": {"MOBILE": 0.58, "INTERNET": 0.29, "BRANCH": 0.11, "ATM": 0.02},
    "QR_PAYMENT": {"QR": 0.94, "MOBILE": 0.06},
    "CARD_PAYMENT": {"POS": 0.71, "INTERNET": 0.29},
    "CASH_DEPOSIT": {"BRANCH": 0.58, "ATM": 0.42},
    "CASH_WITHDRAWAL": {"ATM": 0.79, "BRANCH": 0.21},
    "DIRECT_DEBIT": {"INTERNET": 0.65, "MOBILE": 0.35},
    "INTERNATIONAL_WIRE": {"BRANCH": 0.74, "INTERNET": 0.26},
}

# Hour-of-day weights for Vietnamese retail banking activity. Registered as
# ASSUME_DIURNAL_PROFILE: no acquired source publishes an intraday curve. The
# shape — quiet overnight, a morning rise, a lunch dip, an evening mobile peak —
# is the claim; the exact weights are not.
ASSUME_DIURNAL_PROFILE = np.array(
    [
        0.006,
        0.004,
        0.003,
        0.003,
        0.004,
        0.010,  # 00-05
        0.022,
        0.040,
        0.062,
        0.075,
        0.078,
        0.070,  # 06-11
        0.052,
        0.058,
        0.070,
        0.072,
        0.068,
        0.062,  # 12-17
        0.058,
        0.052,
        0.048,
        0.040,
        0.026,
        0.017,  # 18-23
    ]
)


@dataclass(slots=True)
class RebuildConfig:
    seed: int = 20260807
    # Share of an internationally exposed customer's outbound traffic that leaves
    # the country. Only such customers are eligible, and the flag is set from the
    # entity, never from the label.
    #
    # Set to land international wires near 1.5% of all transactions. Cross-border
    # payments are a large share of Vietnamese payment *value* and a small share
    # of payment *count*; an earlier 0.35 put them at 6% of rows, which no retail
    # bank in Viet Nam would show.
    international_wire_share: float = 0.09


def _rng(seed: int, stream: str) -> np.random.Generator:
    digest = hashlib.sha256(f"{seed}:{stream}".encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "big"))


def redraw_times(timestamps: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Replace time-of-day while preserving date and global ordering.

    Returns epoch seconds. The algorithm is: bucket by date, draw one time per
    transaction from the diurnal curve, sort those times, and hand them out in
    the order the original transactions occurred on that day. Order is preserved
    by construction, so no downstream temporal structure can be inverted.
    """
    days = (timestamps // 86_400).astype(np.int64)
    rebuilt = np.empty_like(timestamps)

    hour_probabilities = ASSUME_DIURNAL_PROFILE / ASSUME_DIURNAL_PROFILE.sum()
    for day in np.unique(days):
        mask = days == day
        count = int(mask.sum())
        hours = rng.choice(24, size=count, p=hour_probabilities)
        seconds = hours * 3600 + rng.integers(0, 3600, size=count)
        seconds.sort()
        # argsort of the originals gives their within-day order; assigning sorted
        # new times along it keeps every pair in the same relative position.
        order = np.argsort(timestamps[mask], kind="stable")
        slot = np.empty(count, dtype=np.int64)
        slot[order] = seconds
        rebuilt[mask] = day * 86_400 + slot
    return rebuilt


def _weighted_choice(rng: np.random.Generator, weights: dict[str, float], size: int) -> np.ndarray:
    keys = list(weights)
    probabilities = np.array([weights[key] for key in keys], dtype=float)
    probabilities /= probabilities.sum()
    return np.array(keys, dtype=object)[rng.choice(len(keys), size=size, p=probabilities)]


def assign_payment_format(
    digital_segments: list[str],
    internationally_exposed: np.ndarray,
    is_external: np.ndarray,
    rng: np.random.Generator,
    config: RebuildConfig,
) -> np.ndarray:
    """Draw a Vietnamese payment format per transaction.

    Inputs are the customer's digital segment, whether the entity has
    international exposure, and whether the counterparty is outside the bank.
    The laundering label is not among them, by construction.
    """
    count = len(digital_segments)
    formats = np.empty(count, dtype=object)

    for segment in ASSUME_CHANNEL_MIX:
        mask = np.array([value == segment for value in digital_segments])
        if not mask.any():
            continue
        formats[mask] = _weighted_choice(rng, ASSUME_CHANNEL_MIX[segment], int(mask.sum()))

    # Unknown segments fall back to the least digital mix rather than crashing.
    missing = formats == None  # noqa: E711 - object array comparison
    if missing.any():
        formats[missing] = _weighted_choice(rng, ASSUME_CHANNEL_MIX["NONE"], int(missing.sum()))

    # International wires only for internationally exposed entities paying out of
    # the bank, and only for a share of those.
    eligible = internationally_exposed & is_external
    if eligible.any():
        draw = rng.random(count) < config.international_wire_share
        formats[eligible & draw] = "INTERNATIONAL_WIRE"
    return formats


def assign_channel(formats: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    channels = np.empty(len(formats), dtype=object)
    for payment_format, weights in ASSUME_CHANNEL_BY_FORMAT.items():
        mask = formats == payment_format
        if mask.any():
            channels[mask] = _weighted_choice(rng, weights, int(mask.sum()))
    return channels


def assign_transaction_type(formats: np.ndarray, is_salary: np.ndarray, merchant_present: np.ndarray) -> np.ndarray:
    """Transaction type follows from instrument and context, deterministically."""
    types = np.full(len(formats), "TRANSFER", dtype=object)
    types[formats == "CASH_DEPOSIT"] = "DEPOSIT"
    types[formats == "CASH_WITHDRAWAL"] = "WITHDRAWAL"
    types[merchant_present] = "PURCHASE"
    types[is_salary] = "SALARY"
    return types


def combined_scale(from_scale: float | None, to_scale: float | None) -> float | None:
    """Geometric mean of the two endpoint scales, or whichever one exists.

    Symmetric on purpose. Using the sender's scale would put the sender exactly on
    its inflow target and leave the receiver arbitrarily far from its own; the
    geometric mean leaves both close and neither privileged.
    """
    scales = [scale for scale in (from_scale, to_scale) if scale is not None and scale > 0]
    if not scales:
        return None
    if len(scales) == 1:
        return scales[0]
    return float(np.sqrt(scales[0] * scales[1]))


def to_epoch(naive: datetime) -> int:
    """Epoch seconds for a naive IBM timestamp, read as UTC.

    IBM declares no timezone and PyArrow hands back naive `datetime` objects.
    Calling `.timestamp()` on one silently applies the *machine's* local zone, so
    the same file would produce different epochs on two developers' laptops — and
    joining a value converted one way against a value converted the other way
    fails completely rather than approximately. Every naive timestamp in this
    pipeline goes through here.
    """
    return int(naive.replace(tzinfo=UTC).timestamp())


def format_timestamp(epoch_seconds: int) -> str:
    """ISO-8601 stamped with the Indochina offset.

    The wall-clock reading is preserved and simply *labelled* `+07:00`, rather
    than shifted into it. IBM's clock has no timezone, so the release adopts one
    by declaration; adding seven hours as well would move every transaction a
    day earlier at the start of the window and claim a precision the source
    never had.
    """
    moment = datetime.fromtimestamp(int(epoch_seconds), UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S") + TIMEZONE_LABEL


def event_id(transaction_id: str, source: str, destination: str, epoch_seconds: int, amount: str) -> str:
    """Deterministic event identifier for Kafka de-duplication.

    Derived from the canonical fields rather than a random UUID, so replaying the
    release produces the same identifiers and a restarted producer cannot create
    duplicates downstream.
    """
    material = "\x1f".join((transaction_id, source, destination, str(epoch_seconds), amount))
    return hashlib.sha256(material.encode()).hexdigest()[:32]


def assumption_register() -> list[dict[str, Any]]:
    return [
        {
            "assumption_id": "ASSUME_CHANNEL_MIX",
            "description": "Payment format shares by customer digital-usage segment.",
            "why_not_evidenced": (
                "SBV publishes system-wide payment aggregates, not a per-customer "
                "instrument mix. The gradient is defensible; the numbers are not "
                "measured."
            ),
            "confidence": "low",
        },
        {
            "assumption_id": "ASSUME_CHANNEL_BY_FORMAT",
            "description": "Access channel conditional on payment instrument.",
            "why_not_evidenced": "Largely mechanical, but the split within each instrument is assumed.",
            "confidence": "medium",
        },
        {
            "assumption_id": "ASSUME_DIURNAL_PROFILE",
            "description": "Hour-of-day activity weights for Vietnamese retail banking.",
            "why_not_evidenced": (
                "No acquired source publishes an intraday curve. Replaces IBM's "
                "uniform-random times, which carry no signal at all."
            ),
            "confidence": "low",
        },
        {
            "assumption_id": "ASSUME_INDIVIDUAL_INTERNATIONAL_EXPOSURE",
            "description": (
                "Top-income-quintile individuals are treated as internationally "
                "exposed, so remittance-style wires exist in the release."
            ),
            "why_not_evidenced": (
                "No acquired source gives the share of Vietnamese bank customers "
                "who send or receive across borders. Without it the release "
                "contained zero international wires."
            ),
            "confidence": "low",
        },
        {
            "assumption_id": "ASSUME_GEOMETRIC_MEAN_SCALE",
            "description": "Internal-to-internal amounts use the geometric mean of endpoint scales.",
            "why_not_evidenced": (
                "A single transaction cannot satisfy two different per-account "
                "scale factors. Symmetric compromise; deviation is measured."
            ),
            "confidence": "medium",
        },
    ]
