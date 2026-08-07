"""Phase 12 — devices, merchants, and relationships.

IBM supplies transactions and a graph; it does not supply the context a
behavioral AML model needs. This adds three tables, and only three, because each
has a defensible basis:

- **Devices** — device sharing and sudden device change are standard AML
  signals, and Findex measures Vietnamese mobile phone ownership at 97.8%.
- **Merchants** — card and QR payments need an acceptance side, and the
  merchant-category mix follows the business population already generated.
- **Relationships** — ownership, device use, and beneficial ownership are the
  edges Hiển's graph work needs, and they are derivable from tables that exist.

Nothing else is added. An enrichment without a defensible basis is decoration
that later gets mistaken for evidence.

## The rule that shapes every distribution here

**Normal and suspicious customers must share overlapping device and merchant
distributions.** If laundering entities got distinctive devices, a model could
find them without learning anything about money movement, and the dataset would
measure its own tell rather than detection.

So nothing in this module reads the laundering label, reads scenario membership,
or takes any input derived from either. Device counts depend on digital segment
and entity type; merchant categories depend on industry. A test asserts device
distributions do not separate flagged from unflagged entities.
"""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np

DEVICE_ID_FORMAT = "DEV-{:08d}"
MERCHANT_ID_FORMAT = "MER-{:08d}"
RELATIONSHIP_ID_FORMAT = "REL-{:010d}"

DEVICE_TYPES = ("ANDROID", "IOS", "WEB")

# Android dominates the Vietnamese smartphone market. Registered as an
# assumption: no acquired source gives the split.
ASSUME_DEVICE_TYPE_MIX = {"ANDROID": 0.70, "IOS": 0.22, "WEB": 0.08}

# Devices per customer, by digital-usage segment. A heavier digital user has more
# registered devices; an unbanked or non-digital customer may have none.
ASSUME_DEVICE_COUNT = {
    "HIGH": {0: 0.02, 1: 0.55, 2: 0.33, 3: 0.10},
    "MEDIUM": {0: 0.06, 1: 0.68, 2: 0.22, 3: 0.04},
    "LOW": {0: 0.34, 1: 0.58, 2: 0.07, 3: 0.01},
    "NONE": {0: 0.72, 1: 0.26, 2: 0.02, 3: 0.00},
}

# A shared device is a legitimate everyday occurrence — a family phone, a shop
# tablet — and it must be common enough that sharing alone is not a tell.
ASSUME_DEVICE_SHARING_RATE = 0.06

MERCHANT_CATEGORIES = (
    "GROCERY",
    "FOOD_BEVERAGE",
    "FUEL",
    "TELECOM",
    "UTILITIES",
    "RETAIL_GENERAL",
    "HEALTHCARE",
    "EDUCATION",
    "TRANSPORT",
    "ECOMMERCE",
)

ASSUME_MERCHANT_CATEGORY_BY_INDUSTRY = {
    "AGRICULTURE": {"GROCERY": 0.42, "FOOD_BEVERAGE": 0.28, "RETAIL_GENERAL": 0.20, "TRANSPORT": 0.10},
    "INDUSTRY": {"RETAIL_GENERAL": 0.31, "FUEL": 0.22, "TRANSPORT": 0.20, "UTILITIES": 0.15, "TELECOM": 0.12},
    "SERVICES": {
        "FOOD_BEVERAGE": 0.24,
        "ECOMMERCE": 0.18,
        "RETAIL_GENERAL": 0.16,
        "HEALTHCARE": 0.12,
        "EDUCATION": 0.11,
        "TELECOM": 0.10,
        "TRANSPORT": 0.09,
    },
}

RELATIONSHIP_TYPES = ("OWNS", "USES_DEVICE", "SHARES_DEVICE", "BUSINESS_OWNER", "BENEFICIARY")


def _rng(seed: int, stream: str) -> np.random.Generator:
    digest = hashlib.sha256(f"{seed}:{stream}".encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "big"))


def _weighted(rng: np.random.Generator, weights: dict[Any, float]) -> Any:
    keys = list(weights)
    probabilities = np.array([weights[key] for key in keys], dtype=float)
    probabilities /= probabilities.sum()
    return keys[int(rng.choice(len(keys), p=probabilities))]


def build_devices(
    customers: list[dict[str, Any]],
    window_start: str,
    window_end: str,
    seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Devices and the customer links that use them.

    Returns the device table and the `USES_DEVICE` / `SHARES_DEVICE`
    relationship rows. Sharing is created by assigning an existing device to a
    second customer, which is what makes a device a graph node worth having.
    """
    rng = _rng(seed, "enrichment.devices")
    devices: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    shareable: list[tuple[str, str]] = []

    for customer in customers:
        segment = customer.get("digital_usage_segment") or "NONE"
        count = int(_weighted(rng, ASSUME_DEVICE_COUNT.get(segment, ASSUME_DEVICE_COUNT["NONE"])))
        for _ in range(count):
            device_id = DEVICE_ID_FORMAT.format(len(devices) + 1)
            devices.append(
                {
                    "device_id": device_id,
                    "customer_id": customer["customer_id"],
                    "device_type": _weighted(rng, ASSUME_DEVICE_TYPE_MIX),
                    "first_seen": window_start,
                    "last_seen": window_end,
                }
            )
            links.append(
                {
                    "source_entity_id": customer["customer_id"],
                    "source_entity_type": "CUSTOMER",
                    "destination_entity_id": device_id,
                    "destination_entity_type": "DEVICE",
                    "relationship_type": "USES_DEVICE",
                    "valid_from": window_start,
                    "valid_to": None,
                }
            )
            shareable.append((device_id, customer["customer_id"]))

    # A second customer on an existing device. Drawn without reference to any
    # label, so sharing carries no information about suspicion by construction.
    if shareable and customers:
        share_count = int(len(customers) * ASSUME_DEVICE_SHARING_RATE)
        for _ in range(share_count):
            device_id, owner_id = shareable[int(rng.integers(0, len(shareable)))]
            other = customers[int(rng.integers(0, len(customers)))]
            if other["customer_id"] == owner_id:
                continue
            links.append(
                {
                    "source_entity_id": other["customer_id"],
                    "source_entity_type": "CUSTOMER",
                    "destination_entity_id": device_id,
                    "destination_entity_type": "DEVICE",
                    "relationship_type": "SHARES_DEVICE",
                    "valid_from": window_start,
                    "valid_to": None,
                }
            )
    return devices, links


def build_merchants(businesses: list[dict[str, Any]], seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Merchants operated by generated businesses.

    Only businesses whose industry plausibly accepts consumer payments become
    merchants, so the merchant population is a subset of the business population
    rather than a parallel invention.
    """
    rng = _rng(seed, "enrichment.merchants")
    merchants: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []

    for business in businesses:
        industry = business.get("industry_group") or "SERVICES"
        # Household businesses in services and agriculture are the retail face of
        # the economy; large industrial firms mostly are not merchants.
        acceptance = 0.62 if industry in ("SERVICES", "AGRICULTURE") else 0.18
        if rng.random() >= acceptance:
            continue
        merchant_id = MERCHANT_ID_FORMAT.format(len(merchants) + 1)
        merchants.append(
            {
                "merchant_id": merchant_id,
                "merchant_category": _weighted(
                    rng,
                    ASSUME_MERCHANT_CATEGORY_BY_INDUSTRY.get(
                        industry, ASSUME_MERCHANT_CATEGORY_BY_INDUSTRY["SERVICES"]
                    ),
                ),
                "urban_rural": business.get("urban_rural"),
                "operated_by_business_id": business["business_id"],
            }
        )
        links.append(
            {
                "source_entity_id": business["business_id"],
                "source_entity_type": "BUSINESS",
                "destination_entity_id": merchant_id,
                "destination_entity_type": "MERCHANT",
                "relationship_type": "OWNS",
                "valid_from": None,
                "valid_to": None,
            }
        )
    return merchants, links


def build_ownership_relationships(accounts: list[dict[str, Any]], window_start: str) -> list[dict[str, Any]]:
    """`OWNS` edges from each entity to its account."""
    return [
        {
            "source_entity_id": account["owner_id"],
            "source_entity_type": account["owner_type"],
            "destination_entity_id": account["account_id"],
            "destination_entity_type": "ACCOUNT",
            "relationship_type": "OWNS",
            "valid_from": account.get("open_date") or window_start,
            "valid_to": None,
        }
        for account in accounts
    ]


def build_business_owner_relationships(
    customers: list[dict[str, Any]], businesses: list[dict[str, Any]], seed: int
) -> list[dict[str, Any]]:
    """Link each business to a natural person who owns it.

    Beneficial ownership is the edge type that makes a graph useful for AML, and
    it is drawn from the employer and own-account customers already generated
    rather than from a separate invented population — those are precisely the
    people the labour statistics say run businesses.
    """
    rng = _rng(seed, "enrichment.business_owner")
    candidates = [
        customer for customer in customers if customer.get("employment_status") in ("EMPLOYER", "OWN_ACCOUNT")
    ]
    if not candidates:
        return []

    links = []
    for business in businesses:
        owner = candidates[int(rng.integers(0, len(candidates)))]
        links.append(
            {
                "source_entity_id": owner["customer_id"],
                "source_entity_type": "CUSTOMER",
                "destination_entity_id": business["business_id"],
                "destination_entity_type": "BUSINESS",
                "relationship_type": "BUSINESS_OWNER",
                "valid_from": None,
                "valid_to": None,
            }
        )
    return links


def finalize_relationships(groups: list[list[dict[str, Any]]], window_start: str) -> list[dict[str, Any]]:
    """Assign stable ids and fill missing validity bounds."""
    rows = []
    for group in groups:
        for entry in group:
            rows.append(
                {
                    "relationship_id": RELATIONSHIP_ID_FORMAT.format(len(rows) + 1),
                    **entry,
                    "valid_from": entry.get("valid_from") or window_start,
                }
            )
    return rows


def assumption_register() -> list[dict[str, Any]]:
    return [
        {
            "assumption_id": "ASSUME_DEVICE_COUNT",
            "description": "Registered devices per customer by digital-usage segment.",
            "why_not_evidenced": "Findex measures phone ownership, not devices registered with a bank.",
            "confidence": "low",
        },
        {
            "assumption_id": "ASSUME_DEVICE_TYPE_MIX",
            "description": "Android / iOS / web split.",
            "why_not_evidenced": "No acquired source gives the Vietnamese split.",
            "confidence": "low",
        },
        {
            "assumption_id": "ASSUME_DEVICE_SHARING_RATE",
            "description": "Share of customers who use a device registered to someone else.",
            "why_not_evidenced": (
                "Not measured anywhere. Set high enough that device sharing cannot "
                "by itself identify a suspicious entity."
            ),
            "confidence": "low",
        },
        {
            "assumption_id": "ASSUME_MERCHANT_ACCEPTANCE",
            "description": "Which businesses become card- and QR-accepting merchants.",
            "why_not_evidenced": "Acceptance rates by industry are not published in the acquired sources.",
            "confidence": "low",
        },
    ]
