"""Phase 16 — split by entity, by network, and by time.

Transaction rows are never split randomly. A random row split puts one leg of a
laundering chain in train and the next in test, so a model can memorise the
network instead of learning the pattern, and every reported score is inflated.

Three constraints, applied in this order because each can override the previous:

1. **Network integrity.** Every account in a criminal network, and every account
   in every network those accounts also belong to, lands in the same split. 219
   of IBM's pattern accounts appear in more than one instance, so this needs a
   connected-component pass over the network membership graph rather than a
   per-network loop.

2. **Entity coherence.** Accounts and devices inherit their owner's split. An
   entity's whole history sits on one side.

3. **Time.** A chronological holdout on top of the entity split, so a model is
   also tested on activity later than anything it trained on.

## The window problem, stated plainly

The source covers 27.67 days. A four-way chronological split gives roughly
17/6/3/3 days, and a three-day window cannot support the rolling-window features
Hường's track needs.

So the release splits **primarily by entity and network**, and records a
`time_partition` column marking each transaction's position in the window
instead of cutting on it. That keeps a temporal evaluation available to anyone
who wants it, without shipping four windows too short to use. The limitation is
recorded in the manifest rather than papered over.
"""

from __future__ import annotations

import hashlib
from typing import Any

SPLITS = ("TRAIN", "VALIDATION", "TEST", "HIDDEN_TEST")

# Entity allocation. Registered governance parameters, not estimates.
SPLIT_WEIGHTS = {"TRAIN": 0.70, "VALIDATION": 0.10, "TEST": 0.10, "HIDDEN_TEST": 0.10}

# Fractions of the observation window used to stamp `time_partition`.
TIME_PARTITIONS = (("EARLY", 0.60), ("MIDDLE", 0.20), ("LATE", 0.20))


def _hash_fraction(value: str, seed: int) -> float:
    """Deterministic value in [0, 1) for an identifier."""
    digest = hashlib.sha256(f"{seed}:split:{value}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


def _split_for(fraction: float) -> str:
    cumulative = 0.0
    for split in SPLITS:
        cumulative += SPLIT_WEIGHTS[split]
        if fraction < cumulative:
            return split
    return SPLITS[-1]


def network_components(networks: list[dict[str, Any]]) -> list[set[str]]:
    """Connected components over accounts that share a network.

    Two instances that share even one account must not be separated: an account
    in train whose other network is in hidden test leaks the second network into
    training through its own history. Union-find over the membership graph is the
    only way to catch chains of such overlaps.
    """
    parent: dict[str, str] = {}

    def find(node: str) -> str:
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(first: str, second: str) -> None:
        root_a, root_b = find(first), find(second)
        if root_a != root_b:
            parent[root_b] = root_a

    for network in networks:
        members = network["members"]
        for member in members:
            find(member)
        for member in members[1:]:
            union(members[0], member)

    components: dict[str, set[str]] = {}
    for node in parent:
        components.setdefault(find(node), set()).add(node)
    return list(components.values())


def assign_entity_splits(
    entity_ids: list[str],
    network_groups: list[set[str]],
    seed: int,
) -> dict[str, str]:
    """Split every entity, keeping each network component whole.

    Network components are assigned first and as a unit; everything else is
    assigned independently. Assignment is by hash rather than by shuffling, so
    adding an entity does not move any existing one.
    """
    assignment: dict[str, str] = {}

    for component in sorted(network_groups, key=lambda group: min(group)):
        anchor = min(component)
        split = _split_for(_hash_fraction(f"component:{anchor}", seed))
        for entity_id in component:
            assignment[entity_id] = split

    for entity_id in entity_ids:
        if entity_id not in assignment:
            assignment[entity_id] = _split_for(_hash_fraction(entity_id, seed))
    return assignment


def time_partition(day_index: int, first_day: int, last_day: int) -> str:
    """Where a transaction sits in the observation window."""
    span = max(last_day - first_day, 1)
    position = (day_index - first_day) / span
    cumulative = 0.0
    for name, fraction in TIME_PARTITIONS:
        cumulative += fraction
        if position < cumulative:
            return name
    return TIME_PARTITIONS[-1][0]


def verify_no_network_crosses_splits(
    networks: list[dict[str, Any]], assignment: dict[str, str]
) -> list[dict[str, Any]]:
    """Return every network whose members landed in more than one split."""
    violations = []
    for network in networks:
        splits = {assignment.get(member) for member in network["members"]}
        splits.discard(None)
        if len(splits) > 1:
            violations.append(
                {
                    "network_id": network.get("network_id"),
                    "splits": sorted(split for split in splits if split),
                    "members": len(network["members"]),
                }
            )
    return violations
