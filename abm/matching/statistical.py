"""Phase 9 — match synthetic Vietnamese KYC agents to IBM behavioral accounts.

This is the join, and it is the step where the two halves of the design either
meet honestly or quietly contaminate each other.

**No claim of identity is made.** An IBM account is not asserted to *be* a
Vietnamese person. A synthetic KYC agent is generated first, its expected
behavior is derived from its own attributes, and it is then paired with an IBM
account whose observed behavior is compatible. What transfers is the shape of
the activity; nothing transfers about who anyone is.

## Method

Two stages, both deliberately transparent — no learned embedding, no neural
matcher, nothing whose failure would be invisible.

1. **Archetype propensity.** Each agent's attributes imply expectations about
   direction of flow, counterparty breadth, activity rhythm, and international
   exposure. Those are scored against each archetype's centroid, softmaxed, and
   sampled. Sampling rather than taking the best match matters: an argmax would
   collapse every agent with the same attributes onto one archetype and destroy
   the within-segment variation that makes a dataset worth modelling.

2. **Rank matching within the archetype.** Entities and accounts are both sorted
   by expected turnover and paired in rank order, each account used once. This
   replaced a greedy nearest-unused search, which is quadratic once a pool fills
   and does not finish at two million entities; rank matching is O(n log n) and,
   for a monotone distance, is the optimal assignment rather than an
   approximation. Targets are jittered before sorting so identical entities do
   not land on adjacent accounts.

## The leakage the matcher has to avoid

The `MULTI_CURRENCY_SELF_CYCLING` archetype carries 6.67x the population's rate
of laundering-involved accounts, because IBM's CYCLE typology hops between
currencies. That is measured in `artifacts/source_profiles/ibm_archetype_leakage.json`.

If archetype assignment were driven by anything resembling a risk judgement —
routing high-income or internationally active customers into that archetype —
then income and international exposure would predict the AML label before a
single scenario is generated, and Phase 14 would be unfalsifiable.

Two defences. Propensity uses only behavioral expectations, never a risk score,
and never any field derived from the label. And `ASSUME_ARCHETYPE_TEMPERATURE`
keeps sampling soft, so every archetype draws from a broad mix of KYC attributes.
The residual association is measured after matching, not assumed away.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np

ACCOUNT_ID_FORMAT = "ACC-{:08d}"

# Softmax temperature for archetype propensity. Higher means softer, which means
# each archetype receives a wider mix of KYC attributes and less of any single
# attribute is predictable from the archetype. 0 would be argmax.
ASSUME_ARCHETYPE_TEMPERATURE = 1.35
ASSUME_ARCHETYPE_TEMPERATURE_SENSITIVITY = (0.8, 2.5)

# The comparison space. Each is scale-free and derivable on both sides: from KYC
# attributes for an agent, from observed behavior for an IBM account.
MATCH_DIMENSIONS = (
    "flow_direction",
    "counterparty_breadth",
    "activity_rhythm",
    "international_exposure",
    "instrument_concentration",
)


@dataclass(slots=True)
class MatchingConfig:
    seed: int = 20260807
    temperature: float = ASSUME_ARCHETYPE_TEMPERATURE


def _rng(seed: int, stream: str) -> np.random.Generator:
    digest = hashlib.sha256(f"{seed}:{stream}".encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "big"))


def expected_behavior_vector(entity: dict[str, Any]) -> np.ndarray:
    """Translate KYC attributes into expectations, on [-1, 1] per dimension.

    Every value here is a modelling judgement about what a kind of customer does,
    not a measured quantity, and the judgements are collected in this one
    function so they can be argued with rather than hunted for. None of them
    references risk, suspicion, or anything derived from the laundering label.
    """
    if entity.get("customer_type") == "INDIVIDUAL":
        employment = entity.get("employment_status")
        digital = entity.get("digital_usage_segment")
        income_band = entity.get("income_band") or "Q3"

        # A wage earner receives from one employer and pays out to many; an
        # own-account trader receives from many customers.
        flow = {
            "WAGE_WORKER": 0.55,
            "OWN_ACCOUNT": 0.15,
            "EMPLOYER": -0.10,
            "UNPAID_FAMILY": 0.40,
            "UNEMPLOYED": 0.30,
            "NOT_IN_LABOUR_FORCE": 0.45,
        }.get(employment, 0.2)

        breadth = {
            "WAGE_WORKER": -0.45,
            "OWN_ACCOUNT": 0.35,
            "EMPLOYER": 0.45,
            "UNPAID_FAMILY": -0.30,
            "UNEMPLOYED": -0.35,
            "NOT_IN_LABOUR_FORCE": -0.50,
        }.get(employment, 0.0)

        rhythm = {"HIGH": 0.60, "MEDIUM": 0.15, "LOW": -0.25, "NONE": -0.65}.get(digital, -0.2)

        # Individuals are overwhelmingly domestic; a mild gradient with income
        # only, since nothing in the acquired sources supports more.
        international = -0.75 + 0.30 * (["Q1", "Q2", "Q3", "Q4", "Q5"].index(income_band) / 4.0)
        concentration = 0.35 if digital in ("NONE", "LOW") else -0.15
    else:
        headcount = int(entity.get("employee_count") or 0)
        industry = entity.get("industry_group")
        cash = entity.get("cash_intensity_band")
        profile = entity.get("domestic_international_profile")

        # A business receives from customers and pays suppliers and staff, so it
        # sits nearer balance than a salaried individual, tipping outbound as it
        # grows a payroll.
        flow = 0.10 - min(headcount, 200) / 400.0
        breadth = 0.30 + min(headcount, 200) / 300.0
        rhythm = 0.25 + min(headcount, 200) / 400.0
        international = {
            "INTERNATIONAL_HEAVY": 0.75,
            "MIXED": 0.10,
            "DOMESTIC_ONLY": -0.60,
        }.get(profile, -0.4)
        concentration = {"HIGH": 0.45, "MEDIUM": 0.0, "LOW": -0.30}.get(cash, 0.0)
        if industry == "AGRICULTURE":
            concentration += 0.15

    return np.clip(np.array([flow, breadth, rhythm, international, concentration], dtype=float), -1.0, 1.0)


def archetype_vectors(archetypes: list[dict[str, Any]]) -> tuple[np.ndarray, list[str]]:
    """Place each archetype in the same comparison space.

    Built from the standardized centroids the clustering produced, squashed onto
    [-1, 1] so an archetype and an agent are directly comparable. `tanh` is used
    rather than a linear rescale because centroids reach beyond four standard
    deviations on some features and a linear map would let one extreme dimension
    dominate every distance.
    """
    rows = []
    names = []
    for archetype in archetypes:
        centroid = archetype["centroid_scaled"]
        rows.append(
            [
                np.tanh(centroid["flow_direction_balance"]),
                np.tanh((centroid["fan_in_ratio"] + centroid["fan_out_ratio"]) / 2.0),
                np.tanh((centroid["log_transactions_per_active_day"] + centroid["activity_density"]) / 2.0),
                np.tanh(centroid["log_distinct_currencies"]),
                np.tanh(centroid["dominant_format_share"]),
            ]
        )
        names.append(archetype["archetype"])
    return np.array(rows), names


def archetype_propensity(expected: np.ndarray, centroids: np.ndarray, temperature: float) -> np.ndarray:
    """Softmax over negative squared distance to each archetype centroid."""
    distances = ((centroids - expected) ** 2).sum(axis=1)
    logits = -distances / max(temperature, 1e-6)
    logits -= logits.max()
    weights = np.exp(logits)
    return weights / weights.sum()


def _standardize(values: np.ndarray) -> np.ndarray:
    spread = values.std()
    return (values - values.mean()) / spread if spread > 0 else np.zeros_like(values)


def match_entities(
    entities: list[dict[str, Any]],
    accounts: dict[str, list[dict[str, Any]]],
    archetypes: list[dict[str, Any]],
    config: MatchingConfig,
) -> list[dict[str, Any]]:
    """Pair every entity with one IBM account.

    `accounts` maps archetype name to its candidate accounts. Each account is
    consumed at most once, so an archetype can run out; when it does the entity
    falls back to its next-most-compatible archetype rather than being dropped or
    given a reused account.
    """
    centroids, names = archetype_vectors(archetypes)
    rng = _rng(config.seed, "matching.archetype")
    neighbour_rng = _rng(config.seed, "matching.neighbour")

    pools: dict[str, list[dict[str, Any]]] = {}
    ranks: dict[str, np.ndarray] = {}
    sorted_views: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for name in names:
        candidates = list(accounts.get(name, []))
        pools[name] = candidates
        if candidates:
            turnover = np.array([float(row.get("turnover_amount") or 0.0) for row in candidates])
            activity = np.array([float(row.get("transaction_count") or 0.0) for row in candidates])
            # Standardized turnover is the axis entities are matched along;
            # activity is standardized alongside it so the two stay comparable
            # if a later revision matches on both.
            ranks[name] = np.column_stack([_standardize(np.log1p(turnover)), _standardize(np.log1p(activity))])
            order = np.argsort(ranks[name][:, 0], kind="stable")
            sorted_views[name] = (order, ranks[name][order, 0])
        else:
            ranks[name] = np.zeros((0, 2))
            sorted_views[name] = (np.zeros(0, dtype=int), np.zeros(0))

    # ------------------------------------------------------ stage 1: archetype
    capacity = {name: len(pools[name]) for name in names}
    assigned: dict[str, list[int]] = {name: [] for name in names}
    propensities: list[float] = [0.0] * len(entities)
    chosen_names: list[str] = [""] * len(entities)

    for index, entity in enumerate(entities):
        expected = expected_behavior_vector(entity)
        propensity = archetype_propensity(expected, centroids, config.temperature)
        order = rng.choice(len(names), size=len(names), replace=False, p=propensity)

        chosen = None
        for candidate_index in order:
            name = names[candidate_index]
            if len(assigned[name]) < capacity[name]:
                chosen = name
                break
        if chosen is None:
            raise RuntimeError(
                "no IBM account capacity remains in any archetype; "
                "the candidate pool is smaller than the entity population"
            )
        assigned[chosen].append(index)
        chosen_names[index] = chosen
        propensities[index] = float(propensity[names.index(chosen)])

    # ------------------------------------------------- stage 2: rank matching
    #
    # Within an archetype, entities and accounts are both ordered by expected
    # turnover and paired in rank order.
    #
    # The earlier implementation searched greedily for the nearest unused
    # account per entity, which is fine while a pool is mostly empty and
    # quadratic once it fills: the outward scan has to step over every account
    # already taken. At two million entities it does not finish.
    #
    # Rank matching gets the same thing in O(n log n), and gets it better —
    # pairing sorted sequences is the optimal assignment for a monotone
    # distance, where greedy is only an approximation. Randomness is preserved
    # by jittering each entity's target before the sort, so identical entities
    # still land on different accounts.
    slot: list[int] = [0] * len(entities)
    scores: list[float] = [0.0] * len(entities)

    for name in names:
        members = assigned[name]
        if not members:
            continue
        order, values = sorted_views[name]

        targets = np.array([_entity_scale_target(entities[index]) for index in members])
        targets = targets + neighbour_rng.normal(0.0, 0.15, size=len(members))
        entity_order = np.argsort(targets, kind="stable")

        # Spread the entities evenly across the pool so a pool larger than the
        # entity group is sampled across its whole range rather than its head.
        picks = np.linspace(0, len(order) - 1, num=len(members)).astype(int)
        for rank, position in enumerate(entity_order):
            index = members[int(position)]
            pool_position = int(order[picks[rank]])
            slot[index] = pool_position
            scores[index] = round(1.0 / (1.0 + abs(float(values[picks[rank]]) - float(targets[position]))), 4)

    matches = []
    for index, entity in enumerate(entities):
        chosen = chosen_names[index]
        account = pools[chosen][slot[index]]
        matches.append(
            {
                "account_id": ACCOUNT_ID_FORMAT.format(index + 1),
                "entity_id": entity.get("customer_id") or entity.get("business_id"),
                "entity_type": "CUSTOMER" if entity.get("customer_type") else "BUSINESS",
                "entity": entity,
                "archetype": chosen,
                "archetype_propensity": propensities[index],
                "matching_method": "archetype_propensity_then_rank_matching",
                "matching_score": scores[index],
                "behavior": account,
                # Lineage is a hash, never the IBM identifier itself. The release
                # must not let anyone walk a P022 account back to a source row.
                "ibm_behavior_source_account_hash": hashlib.sha256(str(account["account_key"]).encode()).hexdigest()[
                    :16
                ],
            }
        )
    return matches


def _entity_scale_target(entity: dict[str, Any]) -> float:
    """Where this entity should sit on the standardized turnover axis.

    Expressed in standard deviations, so it lines up with the standardized
    account ranks. The mapping is coarse on purpose: the sources support an
    ordering of customers by expected turnover, not a precise placement.
    """
    if entity.get("customer_type") == "INDIVIDUAL":
        income_band = entity.get("income_band") or "Q3"
        return {"Q1": -1.2, "Q2": -0.6, "Q3": 0.0, "Q4": 0.6, "Q5": 1.2}[income_band]
    headcount = int(entity.get("employee_count") or 0)
    return float(np.clip(np.log1p(headcount) / 2.0 - 0.4, -1.5, 2.0))


def assumption_register() -> list[dict[str, Any]]:
    return [
        {
            "assumption_id": "ASSUME_ARCHETYPE_TEMPERATURE",
            "description": "Softmax temperature for archetype propensity sampling.",
            "value": ASSUME_ARCHETYPE_TEMPERATURE,
            "sensitivity_range": list(ASSUME_ARCHETYPE_TEMPERATURE_SENSITIVITY),
            "why_not_evidenced": (
                "Controls how tightly KYC attributes determine archetype. Lower "
                "values sharpen matching but increase the association between KYC "
                "attributes and the laundering label carried by archetypes."
            ),
            "confidence": "low",
        },
        {
            "assumption_id": "ASSUME_EXPECTED_BEHAVIOR_MAPPING",
            "description": (
                "The mapping from KYC attributes to expected flow direction, "
                "counterparty breadth, rhythm, international exposure, and "
                "instrument concentration."
            ),
            "why_not_evidenced": (
                "No acquired source relates Vietnamese customer attributes to "
                "transaction behavior. This is the largest judgement in the "
                "pipeline and the one most in need of bank data to replace it."
            ),
            "confidence": "low",
        },
    ]
